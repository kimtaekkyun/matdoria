"""미쉐린 가이드 서울 레스토랑 수집 및 정규화.

사용법:
    python scripts/fetch_michelin.py

결과:
    data/raw/michelin/<YYYY-MM-DD>/michelin_my_maps.csv : 전 세계 원본 CSV (git 미추적)
    data/processed/michelin_seoul.csv                    : 서울 필터링 결과

출처: ngshiheng/michelin-my-maps (MIT). 미쉐린 공식 API가 아니라 공개 가이드 페이지를
수집한 커뮤니티 데이터셋이므로, 스냅샷 시점과 정확도는 공식 가이드로 교차 확인이 필요함.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://raw.githubusercontent.com/ngshiheng/michelin-my-maps/main/data/michelin_my_maps.csv"
SEOUL_PATTERN = re.compile(r"\bSeoul\b|South Korea", re.IGNORECASE)


def main() -> None:
    today = dt.date.today().isoformat()
    raw_dir = ROOT / "data" / "raw" / "michelin" / today
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / "michelin_my_maps.csv"

    with urllib.request.urlopen(SOURCE_URL, timeout=120) as resp:
        raw_path.write_bytes(resp.read())

    with raw_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"전체 미쉐린 항목: {len(rows)}건")

    seoul = [r for r in rows if r["Location"].startswith("Seoul")]
    out_rows = []
    for r in seoul:
        out_rows.append({
            "michelin_name": r["Name"],
            "address_en": r["Address"],
            "location": r["Location"],
            "price": r["Price"],
            "cuisine": r["Cuisine"],
            "lat": r["Latitude"],
            "lng": r["Longitude"],
            "award": r["Award"],
            "green_star": r["GreenStar"],
            "michelin_url": r["Url"],
            "website": r["WebsiteUrl"],
            "phone": r["PhoneNumber"],
            "source_snapshot": today,
        })
    out_rows.sort(key=lambda r: (r["award"], r["michelin_name"]))

    out = ROOT / "data" / "processed" / "michelin_seoul.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        writer.writeheader()
        writer.writerows(out_rows)

    counts: dict[str, int] = {}
    for r in out_rows:
        counts[r["award"]] = counts.get(r["award"], 0) + 1
    print(f"서울 미쉐린 항목: {len(out_rows)}건 -> {out.relative_to(ROOT)}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
