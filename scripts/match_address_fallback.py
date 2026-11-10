"""미쉐린 항목 중 high가 아닌 것을 주소 검색으로 다시 매칭한다.

사용법 (match_kakao.py 실행 후):
    python scripts/match_address_fallback.py

절차:
  1. data/aliases/michelin_roads.csv 의 한글 도로명 주소 후보를 도로명주소 API로 조회한다.
  2. 조회 결과의 영문 도로명주소(engAddr)가 미쉐린 영문 주소와 일치해야 검증 통과 (잘못 적힌 한글 주소는 여기서 걸린다).
  3. 검증된 도로명주소로 카카오 키워드 검색 → 같은 도로명·번지를 가진 장소 중 미쉐린 좌표에 가장 가까운 것을 채택 (규칙 address_search, high).

결과는 data/processed/places_matched.csv 와 match_dropped.csv 에 반영한다.
"""

from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

import match_kakao as m

ROOT = m.ROOT
PROCESSED = m.PROCESSED
ROAD_TABLE = ROOT / "data" / "aliases" / "michelin_roads.csv"


def juso_search(juso_key: str, keyword: str) -> list[dict]:
    params = {"confmKey": juso_key, "currentPage": 1, "countPerPage": 5, "keyword": keyword, "resultType": "json"}
    url = m.JUSO_API + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("results", {}).get("juso") or []


def clean_road(road_addr: str) -> str:
    """'서울특별시 마포구 토정로37길 47 (염리동)' → '서울 마포구 토정로37길 47'"""
    text = re.sub(r"\(.*?\)", "", road_addr).strip()
    return text.replace("서울특별시", "서울").strip()


def main() -> None:
    api_key = m.load_key()
    juso_key = m.load_juso_key()
    if not juso_key:
        raise SystemExit("JUSO_API_KEY가 없습니다.")

    with ROAD_TABLE.open(encoding="utf-8", newline="") as f:
        road_table = {r["michelin_name"]: r["road_addr_ko"] for r in csv.DictReader(f) if r.get("road_addr_ko")}

    michelin = {r["michelin_name"]: r for r in csv.DictReader((PROCESSED / "michelin_seoul.csv").open(encoding="utf-8"))}
    with (PROCESSED / "places_matched.csv").open(encoding="utf-8") as f:
        matched_rows = list(csv.DictReader(f))
        fieldnames = list(matched_rows[0].keys())
    with (PROCESSED / "match_dropped.csv").open(encoding="utf-8") as f:
        dropped_rows = list(csv.DictReader(f))

    # high가 아닌 미쉐린 항목만 대상으로 한다
    target_urls = set()
    for r in matched_rows:
        if r["source"] == "michelin" and r["match_confidence"] != "high":
            target_urls.add(r["src_id"])
    for r in dropped_rows:
        if r["source"] == "michelin":
            target_urls.add(r["src_id"])

    fixed, failed = [], []
    for name, mrow in michelin.items():
        if mrow["michelin_url"] not in target_urls:
            continue
        if name not in road_table:
            failed.append((name, "한글 주소 후보 없음"))
            continue

        # 1-2. 도로명주소 API 조회 + 영문 주소 검증
        juso_hits = juso_search(juso_key, road_table[name])
        verified = [j for j in juso_hits if m.en_address_matches(mrow["address_en"], j["engAddr"])]
        if not verified:
            failed.append((name, "도로명주소 영문 검증 실패"))
            continue
        road = clean_road(verified[0]["roadAddr"])
        road_core = re.sub(r"^서울\s*", "", road)  # '마포구 토정로37길 47' 형태 비교용

        # 3. 카카오 키워드 검색 → 같은 도로명·번지 장소 중 가장 가까운 것
        data = m.call(api_key, m.KEYWORD_API, {
            "query": road, "x": mrow["lng"], "y": mrow["lat"], "radius": 1000, "size": 15,
        })
        cands = []
        for doc in data.get("documents", []):
            kaddr = doc.get("road_address_name") or doc.get("address_name", "")
            if road_core in kaddr or road in kaddr:
                cands.append(m.to_cand(doc, float(mrow["lat"]), float(mrow["lng"]), name))
        if not cands:
            failed.append((name, f"카카오에 '{road}' 주소 장소 없음"))
            continue
        # 주소가 같아도 식당이 아닌 입주 업체(사무실 등)일 수 있으므로 좌표와 이름으로 한 번 더 거른다
        ok = [c for c in cands if c["distance_m"] <= 30 or (c["distance_m"] <= 300 and c["sim"] >= 0.5)]
        if not ok:
            far = min(cands, key=lambda c: c["distance_m"])
            failed.append((name, f"주소는 같지만 좌표·이름이 맞지 않음 ({far['kakao_name']}, {far['distance_m']}m)"))
            continue
        best = min(ok, key=lambda c: c["distance_m"])
        fixed.append((name, best, road))

    # 결과 반영: 기존 미쉐린 행 제거 후 새 행 추가
    fixed_urls = {michelin[n]["michelin_url"] for n, _, _ in fixed}
    matched_rows = [r for r in matched_rows if not (r["source"] == "michelin" and r["src_id"] in fixed_urls)]
    dropped_rows = [r for r in dropped_rows if not (r["source"] == "michelin" and r["src_id"] in fixed_urls)]
    for name, best, road in fixed:
        mrow = michelin[name]
        row = {k: "" for k in fieldnames}
        row.update({
            "source": "michelin", "src_id": mrow["michelin_url"], "name": name,
            "lat": mrow["lat"], "lng": mrow["lng"], "src_group": mrow["award"],
            "src_address": mrow["address_en"], "source_url": mrow["michelin_url"],
            "michelin_name": mrow["michelin_name"], "price": mrow["price"], "cuisine": mrow["cuisine"],
            "match_rule": "address_search", "match_confidence": "high",
        })
        for k, v in best.items():
            if k != "is_food":
                row[f"match_{k}"] = v
        matched_rows.append(row)
        print(f"  채택  {name:<24} -> {best['kakao_name']} ({best['distance_m']}m) [{road}]")
    for name, reason in failed:
        print(f"  실패  {name:<24} : {reason}")

    m.write_csv(PROCESSED / "places_matched.csv", matched_rows)
    m.write_csv(PROCESSED / "match_dropped.csv", dropped_rows)
    print(f"주소 검색으로 추가 채택 {len(fixed)}곳, 실패 {len(failed)}곳")


if __name__ == "__main__":
    main()
