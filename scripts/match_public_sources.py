"""착한가격업소·모범음식점을 Kakao 장소에 주소 검증 기반으로 연결한다.

먼저 prepare_public_sources.py를 실행한다. 자동으로 주소까지 확인된 high만
export 대상이며, 나머지는 사람이 검수할 match_public_review.csv에 남긴다.

기본 실행은 모든 준비된 행을 조회하므로 --limit으로 표본을 먼저 확인할 수 있다.
응답 캐시는 data/raw/kakao_public_cache/에 저장한다.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data/processed"
CACHE = ROOT / "data/raw/kakao_public_cache"
ENV_FILE = ROOT / ".env.local"
KEYWORD_API = "https://dapi.kakao.com/v2/local/search/keyword.json"
OUT = PROCESSED / "public_sources_matched.csv"
REVIEW = PROCESSED / "match_public_review.csv"


def load_key() -> str:
    if not ENV_FILE.exists():
        raise SystemExit("프로젝트 루트 .env.local에 KAKAO_REST_API_KEY가 필요합니다.")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("KAKAO_REST_API_KEY="):
            key = line.split("=", 1)[1].strip()
            if key:
                return key
    raise SystemExit(".env.local에 KAKAO_REST_API_KEY가 필요합니다.")


def norm(text: str) -> str:
    return re.sub(r"[^0-9a-z가-힣]", "", text.casefold())


def clean_address(text: str) -> str:
    text = re.sub(r"\([^)]*\)", " ", text)  # 동명 등 괄호 보충정보는 아래 parcel check에서 별도 처리
    text = re.sub(r"\b(?:지하\s*)?\d+\s*(?:층|호)\b", " ", text)
    text = re.sub(r"\b(?:B\s*\d+|\d+F)\b", " ", text, flags=re.I)
    text = re.sub(r"서울특별시|서울시|대한민국", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def district(text: str) -> str:
    match = re.search(r"([가-힣]+구)", text)
    return match.group(1) if match else ""


def address_verified(source: str, road: str, parcel: str) -> bool:
    source_clean = clean_address(source)
    source_gu = district(source_clean)
    if "서울" not in source or not source_gu:
        return False
    for candidate in (road, parcel):
        if not candidate or "서울" not in candidate:
            continue
        candidate_clean = clean_address(candidate)
        if district(candidate_clean) != source_gu:
            continue
        if norm(source_clean) == norm(candidate_clean):
            return True
        # 도로명 주소끼리는 도로명과 번지 모두 같아야 한다.
        src_road = re.search(r"([가-힣0-9]+(?:대로|로|길))(?=\s)\s+(\d+(?:-\d+)?)", source_clean)
        cand_road = re.search(r"([가-힣0-9]+(?:대로|로|길))(?=\s)\s+(\d+(?:-\d+)?)", candidate_clean)
        if src_road and cand_road and src_road.groups() == cand_road.groups():
            return True
        # 지번 주소는 법정동(괄호 또는 주소 텍스트 내 동)과 본번/부번이 모두 일치해야 한다.
        src_dong = re.search(r"([가-힣0-9]+(?:동|가))", source)
        cand_dong = re.search(r"([가-힣0-9]+(?:동|가))", candidate)
        src_lot = re.search(r"(?:^|\s)(\d+(?:-\d+)?)(?:\s|$)", source_clean)
        cand_lot = re.search(r"(?:^|\s)(\d+(?:-\d+)?)(?:\s|$)", candidate_clean)
        if src_dong and cand_dong and src_lot and cand_lot:
            if src_dong.group(1) == cand_dong.group(1) and src_lot.group(1) == cand_lot.group(1):
                return True
    return False


def kakao_query(api_key: str, query: str, refresh: bool = False) -> list[dict]:
    params = {"query": query, "size": 15}
    cache_name = hashlib.sha256(query.encode("utf-8")).hexdigest()[:24]
    path = CACHE / f"{cache_name}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8")).get("documents", [])
    url = KEYWORD_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {api_key}"})
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.05)
    return payload.get("documents", [])


def load_sources() -> list[dict]:
    paths = [PROCESSED / "good_price_seoul.csv", PROCESSED / "model_restaurant_seoul.csv"]
    rows = []
    for path in paths:
        if path.exists():
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows.extend(csv.DictReader(stream))
    return rows


def evaluate(source: dict, docs: list[dict]) -> tuple[dict | None, list[dict]]:
    source_name = norm(source.get("name", ""))
    source_gu = district(source.get("address", ""))
    candidates = []
    for doc in docs:
        category = doc.get("category_name", "")
        if not category.startswith("음식점"):
            continue
        name = norm(doc.get("place_name", ""))
        similarity = difflib.SequenceMatcher(None, source_name, name).ratio()
        road, parcel = doc.get("road_address_name", ""), doc.get("address_name", "")
        addr_ok = address_verified(source.get("address", ""), road, parcel)
        same_gu = bool(source_gu and source_gu in (road + " " + parcel))
        candidates.append({
            "doc": doc,
            "similarity": similarity,
            "address_verified": addr_ok,
            "same_gu": same_gu,
        })
    candidates.sort(key=lambda item: (item["address_verified"], item["similarity"]), reverse=True)
    accepted = [item for item in candidates if item["address_verified"] and item["similarity"] >= 0.82]
    # 모호한 동일 상호/주소 후보는 자동 연결하지 않는다.
    if len(accepted) == 1:
        return accepted[0], candidates[:3]
    return None, candidates[:3]


def output_row(source: dict, result: dict | None, candidates: list[dict]) -> dict:
    record = dict(source)
    if result:
        doc = result["doc"]
        record.update({
            "match_kakao_id": doc.get("id", ""),
            "match_kakao_name": doc.get("place_name", ""),
            "match_kakao_address": doc.get("road_address_name") or doc.get("address_name", ""),
            "match_kakao_category": doc.get("category_name", ""),
            "match_kakao_url": doc.get("place_url", ""),
            "match_kakao_lat": doc.get("y", ""),
            "match_kakao_lng": doc.get("x", ""),
            "match_rule": "exact_name_address_verified",
            "match_confidence": "high",
            "match_name_similarity": round(result["similarity"], 3),
            "match_address_verified": True,
        })
        return record
    record.update({
        "match_kakao_id": "", "match_kakao_name": "", "match_kakao_address": "",
        "match_kakao_category": "", "match_kakao_url": "", "match_kakao_lat": "",
        "match_kakao_lng": "", "match_rule": "needs_review" if candidates else "no_candidate",
        "match_confidence": "",
    })
    record["review_candidates"] = json.dumps([
        {
            "name": item["doc"].get("place_name", ""),
            "address": item["doc"].get("road_address_name") or item["doc"].get("address_name", ""),
            "place_id": item["doc"].get("id", ""),
            "name_similarity": round(item["similarity"], 3),
            "address_verified": item["address_verified"],
        }
        for item in candidates
    ], ensure_ascii=False)
    return record


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="처음 N건만 조회 (API 표본 확인용)")
    parser.add_argument("--refresh", action="store_true", help="기존 Kakao 검색 캐시 무시")
    args = parser.parse_args()
    sources = load_sources()
    if args.limit is not None:
        sources = sources[:max(0, args.limit)]
    if not sources:
        raise SystemExit("정규화 입력이 없습니다. python scripts/prepare_public_sources.py를 먼저 실행하십시오.")

    api_key = load_key()
    matched, review = [], []
    for index, source in enumerate(sources, 1):
        name, gu = source.get("name", "").strip(), district(source.get("address", ""))
        queries = [f"{name} {gu}".strip(), name]
        docs = []
        for query in dict.fromkeys(query for query in queries if query):
            docs.extend(kakao_query(api_key, query, args.refresh))
            # ID 중복 제거
            docs = list({doc.get("id"): doc for doc in docs if doc.get("id")}.values())
            result, candidates = evaluate(source, docs)
            if result:
                break
        row = output_row(source, result, candidates)
        (matched if result else review).append(row)
        if index % 100 == 0:
            print(f"진행 {index}/{len(sources)} · 자동 검증 {len(matched)} · 검수 {len(review)}")

    matched_path = PROCESSED / ("public_sources_matched_sample.csv" if args.limit is not None else OUT.name)
    review_path = PROCESSED / ("match_public_review_sample.csv" if args.limit is not None else REVIEW.name)
    write_csv(matched_path, matched)
    write_csv(review_path, review)
    print(f"완료: high {len(matched)}건 -> {matched_path.relative_to(ROOT)} · 검수 {len(review)}건 -> {review_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
