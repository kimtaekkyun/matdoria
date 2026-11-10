"""서울미래유산 식음 관련 항목 수집 및 정규화.

사용법:
    python scripts/fetch_seoul_heritage.py

결과:
    data/raw/seoul_heritage/<YYYY-MM-DD>/  : 구별 원본 JSON 응답
    data/processed/seoul_heritage_food.csv : 식음 관련 항목 (정규화)

출처: 서울미래유산 공개 지도 API (/main/ajaxMainHeritageList.do)
이 엔드포인트는 웹사이트 메인 지도가 사용하는 내부 AJAX이며, 공식 공개 API 문서는 없음.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://futureheritage.seoul.go.kr"
ENDPOINT = f"{BASE}/main/ajaxMainHeritageList.do"
DETAIL_URL = f"{BASE}/futureHeritageMeet/futureHeritage/view.do?htNo={{ht_no}}"

# 메인 지도의 구 선택 코드 (main/mainForm.do 의 #selectGu 옵션)
GU_CODES = ["3001", "3002", "3003", "3004", "3005", "3006", "3007", "3008", "3009",
            "3010", "3011", "3012", "3013", "3014", "3015", "3016", "3017", "3018",
            "3019", "3020", "3021", "3022", "3023", "3024", "3025", "3026"]
CENTER_LAT, CENTER_LNG = 37.56675211686259, 126.97861832225746  # 메인 지도 중심
DISTANCE_KM = 15  # 메인 지도 select 옵션 중 최대값

# 서울미래유산 '찾아보기' 검색 조건 코드 (list.do 의 htCondition)
# 4115 = 음식점. 그 외 식음 관련 항목은 아래 키워드로 후보를 뽑는다.
SEARCH_TYPE_FOOD = "4115"
SEARCH_TYPE_FOOD_DTL_RESTAURANT = "4116"  # 음식점 > (식당류 세부)
# 식음 관련 단어. '탕', '찜', '골목' 같은 짧은 단어는 목욕탕 등 오탐이 많아 제외.
FOOD_WORDS = re.compile(
    r"식당|음식|국밥|설렁탕|곰탕|냉면|칼국수|갈비|해장국|떡볶이|곱창|족발|보쌈|"
    r"중식|양식|한식|맛집|국수|만두|주점|분식|떡집|제과|빵|커피|구이|막걸리|"
    r"순대|생선|노가리|감자탕|추어탕|삼계탕|아구찜|대구탕|매운탕|콩국수|막국수|"
    r"주막|다방|화교거리|피맛골|기사식당"
)
FOOD_STREET = re.compile(r"골목|거리|피맛골|먹자")
# 설명 본문에서 업종을 직접 가리키는 단어 (후보 판정용, 오탐 방지를 위해 좁게 유지)
SHOP_WORDS = re.compile(r"음식점|식당|제과|떡집|빵집|다방|커피 전문|막걸리|분식|주점|식품")

OPEN_PATTERNS = [
    # "1968년 개업", "1950년에 개업", "1936년 개업하여", "1968년경 개업"
    re.compile(r"(\d{4})\s*년(?:\s*경)?\s*(?:에)?\s*(?:개업|창업|개점)"),
    # "개업 1968년", "개업한 1968년" 등 바로 뒤에 연도가 오는 경우만
    re.compile(r"(?:개업|창업|개점)(?:한|하여|했으며)?\s*(?:이래)?\s*(\d{4})\s*년"),
]


def fetch_gu(gu: str) -> dict:
    data = urllib.parse.urlencode({
        "lat": CENTER_LAT,
        "lng": CENTER_LNG,
        "distance": DISTANCE_KM,
        "gu": gu,
    }).encode()
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        headers={"X-Requested-With": "XMLHttpRequest"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_opened_year(*texts: str | None) -> tuple[int | None, str]:
    """설명 텍스트에서 개업 연도를 추출. 못 찾으면 (None, '')."""
    for text in texts:
        if not text:
            continue
        for pat in OPEN_PATTERNS:
            m = pat.search(text)
            if m:
                year = int(m.group(1))
                snippet = text[max(0, m.start() - 20): m.end() + 20].replace("\n", " ").strip()
                return year, snippet
    return None, ""


def classify(rec: dict) -> str | None:
    """식음 그룹 분류. None이면 식음과 무관."""
    st = rec.get("searchType")
    dtl = rec.get("searchTypeDtl")
    name = rec.get("nm") or ""
    text = " ".join(filter(None, [rec.get("expCont"), rec.get("dlbrResult"), rec.get("rmrkCn")]))

    if st == SEARCH_TYPE_FOOD and dtl == SEARCH_TYPE_FOOD_DTL_RESTAURANT:
        return "음식점"
    if st == SEARCH_TYPE_FOOD:
        # 4115 태그지만 음식점 세부분류가 아닌 항목 (시장, 건물 등)
        return "음식 관련(기타)"
    if st == "4101" and FOOD_STREET.search(name) and FOOD_WORDS.search(name + " " + text):
        return "음식 골목"
    # 후보: 이름에 식음 단어가 있거나, 설명에 식당·제과 등 업종을 직접 가리키는 단어가 있는 경우
    if FOOD_WORDS.search(name) or SHOP_WORDS.search(text):
        return "음식 관련 후보(확인 필요)"
    return None


def main() -> None:
    today = dt.date.today().isoformat()
    raw_dir = ROOT / "data" / "raw" / "seoul_heritage" / today
    raw_dir.mkdir(parents=True, exist_ok=True)

    recs: dict[int, dict] = {}
    for gu in GU_CODES:
        payload = fetch_gu(gu)
        (raw_dir / f"gu_{gu}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        for rec in payload.get("resultList") or []:
            recs[rec["htNo"]] = rec
    print(f"전체 미래유산 (중복 제거): {len(recs)}건")

    rows = []
    for rec in recs.values():
        group = classify(rec)
        if group is None:
            continue
        opened, snippet = parse_opened_year(rec.get("dlbrResult"), rec.get("expCont"), rec.get("rmrkCn"))
        cert = rec.get("certNo") or ""
        selected_year = cert[:4] if re.match(r"^\d{4}", cert) else ""
        rows.append({
            "ht_no": rec["htNo"],
            "name": rec["nm"],
            "group": group,
            "address": rec.get("newAddr") or "",
            "gu_code": rec.get("stdgSggCd") or "",
            "lat": rec.get("ylatwgs84") or "",
            "lng": rec.get("xlonwgs84") or "",
            "opened_year": opened or "",
            "opened_year_snippet": snippet,
            "built_year_text": rec.get("buildTime") or "",
            "heritage_selected_year": selected_year,
            "cert_no": cert,
            "search_type": rec.get("searchType") or "",
            "search_type_dtl": rec.get("searchTypeDtl") or "",
            "description": (rec.get("dlbrResult") or "").replace("\n", " ").strip(),
            "detail_url": DETAIL_URL.format(ht_no=rec["htNo"]),
            "fetched_at": today,
        })

    rows.sort(key=lambda r: (r["group"], r["name"]))
    out = ROOT / "data" / "processed" / "seoul_heritage_food.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    by_group: dict[str, int] = {}
    for r in rows:
        by_group[r["group"]] = by_group.get(r["group"], 0) + 1
    print(f"식음 관련 항목: {len(rows)}건 -> {out.relative_to(ROOT)}")
    for k, v in sorted(by_group.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
