"""매칭 결과(high)를 카카오 장소 ID 기준으로 합쳐 웹앱용 JSON을 만든다.

사용법:
    python scripts/export_places.py

입력:  data/processed/places_matched.csv
출력:  web/public/data/places.json

MVP 정책 (D-018): match_confidence == high 만 사용한다. medium은 제외.
같은 카카오 장소가 여러 출처에 있으면 하나의 장소로 합치고 출처 정보를 모두 담는다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "places_matched.csv"
OUT = ROOT / "web" / "public" / "data" / "places.json"


def source_entry(row: dict) -> dict:
    if row["source"] == "michelin":
        return {
            "source": "michelin",
            "label": "미쉐린 가이드",
            "award": row["src_group"],
            "price": row.get("price", ""),
            "cuisine": row.get("cuisine", ""),
            "url": row["source_url"],
            "originalName": row.get("michelin_name", row["name"]),
        }
    return {
        "source": "seoul_heritage",
        "label": "서울미래유산",
        "group": row["src_group"],
        "openedYear": int(row["opened_year"]) if row.get("opened_year") else None,
        "selectedYear": int(row["heritage_selected_year"]) if row.get("heritage_selected_year") else None,
        "url": row["source_url"],
        "originalName": row["name"],
    }


def main() -> None:
    with SRC.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["match_confidence"] == "high"]

    places: dict[str, dict] = {}
    for r in rows:
        kid = r["match_kakao_id"]
        place = places.setdefault(kid, {
            "id": kid,
            "name": r["match_kakao_name"],
            "address": r["match_kakao_address"],
            "category": r["match_kakao_category"],
            "lat": float(r["match_kakao_lat"]),
            "lng": float(r["match_kakao_lng"]),
            "kakaoUrl": r["match_kakao_url"],
            "sources": [],
        })
        place["sources"].append(source_entry(r))

    result = sorted(places.values(), key=lambda p: p["name"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    michelin_n = sum(1 for p in result if any(s["source"] == "michelin" for s in p["sources"]))
    heritage_n = sum(1 for p in result if any(s["source"] == "seoul_heritage" for s in p["sources"]))
    print(f"장소 {len(result)}곳 (미쉐린 {michelin_n}, 서울미래유산 {heritage_n}) -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
