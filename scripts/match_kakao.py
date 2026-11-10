"""서울미래유산 식음 항목과 미쉐린 서울 항목을 카카오 장소 ID에 매칭한다.

사용법:
    python scripts/match_kakao.py

입력:
    data/processed/seoul_heritage_food.csv
    data/processed/michelin_seoul.csv
    data/aliases/michelin.csv   (선택, 수동 별칭: michelin_name, kakao_name)
    .env.local                  (KAKAO_REST_API_KEY)

출력:
    data/processed/places_matched.csv   매칭 성공 (kakao_id 기준, 지도 표시용)
    data/processed/match_dropped.csv    매칭 실패 (D-002에 따라 최종 데이터에서 제외)

사람 검수 없이 규칙으로만 결정한다. 규칙 순서 (먼저 걸리는 것이 채택):
    1. 좌표 150m 이내 음식점 중 이름 유사도 >= 0.35 인 것 (가장 유사한 것)
    2. 좌표 300m 이내 이름 유사도 >= 0.80 인 것
    3. 서울 내 이름 일치 (유사도 >= 0.80, 1km 이내) 인 것
    4. 좌표 30m 이내 가장 가까운 음식점 (이름이 달라도 채택)
    그 외는 drop.

같은 건물에 식당이 여럿이면 각 식당이 자기 카카오 장소로 연결된다 (지도에서는 같은 위치에 표시됨).
카카오 응답은 data/raw/kakao_cache/ 에 캐시되므로 규칙을 바꿔 재실행해도 API 호출이 늘지 않는다.
"""

from __future__ import annotations

import csv
import difflib
import json
import math
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYWORD_API = "https://dapi.kakao.com/v2/local/search/keyword.json"
CATEGORY_API = "https://dapi.kakao.com/v2/local/search/category.json"
CACHE_DIR = ROOT / "data" / "raw" / "kakao_cache"
PROCESSED = ROOT / "data" / "processed"
ALIASES = ROOT / "data" / "aliases" / "michelin.csv"
ENV_FILE = ROOT / ".env.local"
JUSO_API = "https://business.juso.go.kr/addrlink/addrLinkApi.do"
JUSO_CACHE_DIR = ROOT / "data" / "raw" / "juso_cache"
JUSO_NEAR_M = 100  # 영문 주소 대조는 좌표 100m 이내 음식점 후보에만 적용 (호출 수 절약)

NEAR_M = 150
FAR_M = 300
NAME_ONLY_M = 1000
NEAREST_FOOD_M = 30
SIM_NEAR = 0.40
SIM_NEAR_STRICT = 0.50
SIM_FAR = 0.80
SIM_NAME_ONLY = 0.80

# 규칙별 신뢰도. nearest_food는 같은 건물의 다른 가게가 붙는 경우가 있어 medium으로 둔다.
# 샘플 25건 점검 결과 약 2/3 정답 (docs/decisions.md D-017 참고)
CONFIDENCE = {
    "name_near": "high",
    "name_far": "high",
    "name_only": "high",
    "address_verified_en": "high",
    "address_verified": "high",
    "nearest_food": "medium",
}

# 미쉐린 영문 주소의 구 이름 → 한글 (서울 25개 구)
GU_EN_TO_KO = {
    "Gangnam-gu": "강남구", "Gangdong-gu": "강동구", "Gangbuk-gu": "강북구", "Gangseo-gu": "강서구",
    "Gwanak-gu": "관악구", "Gwangjin-gu": "광진구", "Guro-gu": "구로구", "Geumcheon-gu": "금천구",
    "Nowon-gu": "노원구", "Dobong-gu": "도봉구", "Dongdaemun-gu": "동대문구", "Dongjak-gu": "동작구",
    "Mapo-gu": "마포구", "Seodaemun-gu": "서대문구", "Seocho-gu": "서초구", "Seongdong-gu": "성동구",
    "Seongbuk-gu": "성북구", "Songpa-gu": "송파구", "Yangcheon-gu": "양천구", "Yeongdeungpo-gu": "영등포구",
    "Yongsan-gu": "용산구", "Eunpyeong-gu": "은평구", "Jongno-gu": "종로구", "Jung-gu": "중구",
    "Jungnang-gu": "중랑구",
}
GU_KO = set(GU_EN_TO_KO.values())


def _address_numbers(addr: str) -> set[str]:
    """주소에서 번지 숫자만 뽑는다. 층수, 호수, 우편번호는 제외."""
    text = addr
    text = re.sub(r"\b\d+F\b|\bB\d+\b|\d+\s*층|지하\s*\d+|(?:Shop|Unit|Room|Suite)\s*\d+", " ", text, flags=re.I)
    nums = set(re.findall(r"\d+", text))
    return {n for n in nums if len(n) < 5}  # 5자리 이상(우편번호)은 제외


def _address_gu(addr: str) -> str | None:
    for en, ko in GU_EN_TO_KO.items():
        if en in addr:
            return ko
    for ko in GU_KO:
        if ko in addr:
            return ko
    return None


def address_matches(src_addr: str, kakao_addr: str) -> bool:
    """소스 주소의 구와 번지가 카카오 도로명 주소와 모두 일치하는지 본다."""
    if not src_addr or not kakao_addr:
        return False
    src_nums = _address_numbers(src_addr)
    if not src_nums:
        return False
    if not src_nums <= _address_numbers(kakao_addr):
        return False
    src_gu = _address_gu(src_addr)
    if src_gu is not None and src_gu not in kakao_addr:
        return False
    return True



def load_key() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("KAKAO_REST_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit(".env.local 에 KAKAO_REST_API_KEY 가 없습니다.")


def call(api_key: str, url: str, params: dict) -> dict:
    """Kakao 호출 + 캐시. 같은 요청은 파일에서 읽는다."""
    key = url + "?" + urllib.parse.urlencode(sorted(params.items()))
    safe = re.sub(r"[^0-9A-Za-z가-힣]+", "_", key.split("//", 1)[1])[:160]
    path = CACHE_DIR / f"{safe}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    req = urllib.request.Request(
        url + "?" + urllib.parse.urlencode(params),
        headers={"Authorization": f"KakaoAK {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.05)
    return data


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def norm(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\(.*?\)", "", text)
    text = re.sub(r"[^0-9a-z가-힣]", "", text)
    return text


def name_sim(a: str, b: str) -> float:
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    short, long_ = sorted([na, nb], key=len)
    ratio = difflib.SequenceMatcher(None, na, nb).ratio()
    # 짧은 이름이 긴 이름에 포함되는 경우는 길이 비율이 충분할 때만 인정 ("설렁탕" ⊂ "신가원설렁탕" 오탐 방지)
    if len(short) >= 2 and short in long_ and len(short) / len(long_) >= 0.6:
        return max(ratio, 0.85)
    return ratio


def load_aliases() -> dict[str, str]:
    if not ALIASES.exists():
        return {}
    with ALIASES.open(encoding="utf-8", newline="") as f:
        return {r["michelin_name"]: r["kakao_name"] for r in csv.DictReader(f) if r.get("kakao_name")}


def to_cand(doc: dict, lat: float, lng: float, name: str, name_only: bool = False) -> dict:
    return {
        "kakao_id": doc["id"],
        "kakao_name": doc["place_name"],
        "kakao_address": doc.get("road_address_name") or doc.get("address_name", ""),
        "kakao_category": doc.get("category_name", ""),
        "kakao_url": doc["place_url"],
        "kakao_lat": doc["y"],
        "kakao_lng": doc["x"],
        "distance_m": round(haversine_m(lat, lng, float(doc["y"]), float(doc["x"])), 1),
        "sim": round(name_sim(name, doc["place_name"]), 3),
        "name_only": name_only,
        "is_food": "음식점" in (doc.get("category_name") or ""),
    }


def candidates_for(api_key: str, name: str, lat: float, lng: float) -> list[dict]:
    found: dict[str, dict] = {}

    # (a) 좌표 주변 음식점 전체 (이름과 무관하게 가까운 것부터). 카테고리 검색은 최대 45건
    for page in (1, 2, 3):
        data = call(api_key, CATEGORY_API, {
            "category_group_code": "FD6", "x": lng, "y": lat,
            "radius": FAR_M, "sort": "distance", "size": 15, "page": page,
        })
        for doc in data.get("documents", []):
            found.setdefault(doc["id"], doc)
        if data.get("meta", {}).get("is_end", True):
            break

    # (b) 이름 검색 (좌표 반경 내) — 음식점이 아닌 카테고리로 등록된 곳도 포함
    data = call(api_key, KEYWORD_API, {"query": name, "x": lng, "y": lat, "radius": FAR_M, "size": 15})
    for doc in data.get("documents", []):
        found.setdefault(doc["id"], doc)

    # (c) 이름만으로 서울 내 검색 (좌표가 부정확한 경우 보완)
    data = call(api_key, KEYWORD_API, {"query": name, "size": 15})
    name_only_ids = set()
    for doc in data.get("documents", []):
        addr = doc.get("road_address_name") or doc.get("address_name", "")
        if addr.startswith("서울"):
            name_only_ids.add(doc["id"])
            found.setdefault(doc["id"], doc)

    out = []
    for doc in found.values():
        out.append(to_cand(doc, lat, lng, name, name_only=doc["id"] in name_only_ids))
    out.sort(key=lambda c: c["distance_m"])
    return out


def load_juso_key() -> str | None:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("JUSO_API_KEY="):
            return line.split("=", 1)[1].strip()
    return None


def juso_english(juso_key: str, road_addr: str) -> str:
    """한글 도로명주소 → 영문 도로명주소 (행정안전부 도로명주소 API의 engAddr). 캐시 사용."""
    if not road_addr:
        return ""
    JUSO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^0-9A-Za-z가-힣]+", "_", road_addr)[:150]
    path = JUSO_CACHE_DIR / f"{safe}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("engAddr", "")
    params = {
        "confmKey": juso_key, "currentPage": 1, "countPerPage": 5,
        "keyword": road_addr, "resultType": "json",
    }
    url = JUSO_API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    common = data.get("results", {}).get("common", {})
    if common.get("errorCode") not in ("0", 0):
        raise SystemExit(f"도로명주소 API 오류: {common.get('errorCode')} {common.get('errorMessage')}")
    jusos = data.get("results", {}).get("juso") or []
    # 검색어와 같은 도로명을 가진 첫 결과를 쓴다 (정확도순 정렬 결과의 첫 항목)
    eng = jusos[0].get("engAddr", "") if jusos else ""
    path.write_text(json.dumps({"roadAddr": road_addr, "engAddr": eng}, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.05)
    return eng


EN_NOISE = {"south", "korea", "republic", "of", "seoul"}


def _en_tokens(text: str) -> list[str]:
    return re.sub(r"[^0-9a-zA-Z]+", " ", text).lower().split()


def en_address_matches(src_en: str, juso_en: str) -> bool:
    """미쉐린 영문 주소의 도로명·번지 구간이 도로명주소 영문에 있는지 본다.
    - 호텔·빌딩명, 층수(2F), 호수(Shop 202), 우편번호, 국가명은 비교하지 않는다.
    - 번지 숫자는 정확히 일치해야 한다.
    - 도로명 단어는 철자 차이(Shinheung/Sinheung 등)를 허용한다 (유사도 0.8 이상).
    - 구(-gu) 이름은 정확히 일치해야 한다."""
    if not src_en or not juso_en:
        return False
    src_clean = re.sub(r"\b(shop|unit|room|suite)\s*\w+", " ", src_en, flags=re.I)
    src_clean = re.sub(r"\b\d+f\b|\bb\d+\b", " ", src_clean, flags=re.I)
    parts = [p.strip() for p in src_clean.split(",") if p.strip()]
    road_parts = [p for p in parts if re.search(r"\d", p) and re.search(r"-(ro|gil|daero)\b", p, re.I)]
    if not road_parts:
        road_parts = [p for p in parts if re.search(r"\d", p)]
    gu_parts = [p for p in parts if re.search(r"-gu\b", p, re.I)]

    road_tokens = [t for t in _en_tokens(" ".join(road_parts)) if t not in EN_NOISE and not (t.isdigit() and len(t) == 5)]
    if len(road_tokens) < 2:
        return False
    juso_tokens = _en_tokens(juso_en)
    juso_set = set(juso_tokens)
    juso_digits = {t for t in juso_tokens if t.isdigit()}

    for t in road_tokens:
        if t.isdigit():
            if t not in juso_digits:
                return False
            continue
        if t in juso_set:
            continue
        # 철자 차이 허용 (글자 수가 4자 이상인 단어만)
        if len(t) < 4 or not any(
            difflib.SequenceMatcher(None, t, j).ratio() >= 0.8 for j in juso_set if not j.isdigit() and len(j) >= 4
        ):
            return False

    for gu in gu_parts:
        gu_tok = _en_tokens(gu)
        if gu_tok and not all(g in juso_set for g in gu_tok):
            return False
    return True

def decide(cands: list[dict], src_address: str = "", src_en: str = "") -> tuple[str, dict | None, str]:
    """(verdict, 선택 후보, 규칙 이름). verdict는 accept 또는 drop."""
    # 1. 이름이 충분히 비슷한 음식점: 150m 이내 유사도 0.50 이상, 또는 30m 이내 유사도 0.40 이상
    #    (유사도 0.4대는 "식사"→"전아사" 같은 오탐이 확인되어 거리 조건을 더 엄격히 둔다)
    near = [c for c in cands if (c["distance_m"] <= NEAR_M and c["sim"] >= SIM_NEAR_STRICT)
            or (c["distance_m"] <= NEAREST_FOOD_M and c["sim"] >= SIM_NEAR)]
    if near:
        best = max(near, key=lambda c: (c["sim"], -c["distance_m"]))
        return "accept", best, "name_near"
    # 2. 300m 이내 이름이 거의 같은 것
    far = [c for c in cands if c["distance_m"] <= FAR_M and c["sim"] >= SIM_FAR]
    if far:
        best = max(far, key=lambda c: (c["sim"], -c["distance_m"]))
        return "accept", best, "name_far"
    # 3. 서울 내 이름 일치 (좌표가 부정확할 수 있으므로 거리 상한은 1km)
    named = [c for c in cands if c["name_only"] and c["sim"] >= SIM_NAME_ONLY and c["distance_m"] <= NAME_ONLY_M]
    if named:
        best = max(named, key=lambda c: (c["sim"], -c["distance_m"]))
        return "accept", best, "name_only"
    # 4a. 영문 도로명주소 일치 (미쉐린 영문 주소 ↔ 도로명주소 API의 영문 주소)
    en_ok = [c for c in cands if c.get("juso_eng") and en_address_matches(src_en, c["juso_eng"])]
    if en_ok:
        best = min(en_ok, key=lambda c: c["distance_m"])
        return "accept", best, "address_verified_en"
    # 4. 주소 검증: 300m 이내 음식점 중 구(區)와 번지 숫자가 소스 주소와 일치하는 가장 가까운 것
    #    영문명이나 이름 검색이 안 되는 경우에도 주소로 확인할 수 있다
    verified = [c for c in cands if c["is_food"] and c["distance_m"] <= FAR_M
                and address_matches(src_address, c["kakao_address"])]
    if verified:
        best = min(verified, key=lambda c: c["distance_m"])
        return "accept", best, "address_verified"
    # 5. 30m 이내 가장 가까운 음식점 (주소 정보가 없거나 검증이 안 된 경우의 최후 수단)
    food = [c for c in cands if c["is_food"] and c["distance_m"] <= NEAREST_FOOD_M]
    if food:
        best = min(food, key=lambda c: c["distance_m"])
        return "accept", best, "nearest_food"
    return "drop", None, "-"


def load_sources() -> list[dict]:
    aliases = load_aliases()
    sources = []
    with (PROCESSED / "seoul_heritage_food.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not (r["lat"] and r["lng"]):
                print(f"좌표 없음, 매칭 불가: {r['name']}")
                continue
            sources.append({
                "source": "seoul_heritage", "src_id": r["ht_no"], "name": r["name"],
                "lat": float(r["lat"]), "lng": float(r["lng"]), "src_group": r["group"],
                "src_address": r["address"], "opened_year": r["opened_year"],
                "heritage_selected_year": r["heritage_selected_year"], "source_url": r["detail_url"],
            })
    with (PROCESSED / "michelin_seoul.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            sources.append({
                "source": "michelin", "src_id": r["michelin_url"],
                "name": aliases.get(r["michelin_name"], r["michelin_name"]),
                "lat": float(r["lat"]), "lng": float(r["lng"]), "src_group": r["award"],
                "src_address": r["address_en"], "opened_year": "", "heritage_selected_year": "",
                "source_url": r["michelin_url"], "michelin_name": r["michelin_name"],
                "price": r["price"], "cuisine": r["cuisine"],
            })
    return sources


def main() -> None:
    api_key = load_key()
    juso_key = load_juso_key()
    if not juso_key:
        print("JUSO_API_KEY 없음: 영문 주소 대조 생략 (한글 주소 규칙만 사용)")
    sources = load_sources()

    matched, dropped = [], []
    for i, s in enumerate(sources, 1):
        cands = candidates_for(api_key, s["name"], s["lat"], s["lng"])
        src_en = ""
        if s["source"] == "michelin" and juso_key:
            src_en = s["src_address"]
            for c in cands:
                if c["is_food"] and c["distance_m"] <= JUSO_NEAR_M:
                    c["juso_eng"] = juso_english(juso_key, c["kakao_address"])
        verdict, best, rule = decide(cands, s["src_address"], src_en)
        row = {**s, "match_rule": rule, "match_confidence": CONFIDENCE.get(rule, "")}
        if best:
            row.update({f"match_{k}": v for k, v in best.items() if k not in ("is_food",)})
            matched.append(row)
        else:
            row["candidate_count"] = len(cands)
            row["nearest_candidate"] = (
                f"{cands[0]['kakao_name']} ({cands[0]['distance_m']}m)" if cands else ""
            )
            dropped.append(row)
        if i % 50 == 0:
            print(f"  진행 {i}/{len(sources)}")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    write_csv(PROCESSED / "places_matched.csv", matched)
    write_csv(PROCESSED / "match_dropped.csv", dropped)
    print(f"매칭 {len(matched)} / drop {len(dropped)} (전체 {len(sources)})")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
