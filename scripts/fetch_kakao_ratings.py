"""Capture aggregate Kakao Map ratings for the current Matdoria places (experiment).

Usage:
    python scripts/fetch_kakao_ratings.py
    python scripts/fetch_kakao_ratings.py --refresh

Only score_set.average_score and score_set.review_count are saved. Individual review
content is intentionally discarded. The endpoint is Kakao Map's undocumented web API.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLACES_PATH = ROOT / "web" / "public" / "data" / "places.json"
OUT_PATH = ROOT / "data" / "processed" / "kakao_ratings.csv"
COLUMNS = ["kakao_place_id", "name", "rating", "review_count", "collected_at", "status"]
BASE_URL = "https://place.map.kakao.com/places/tab/reviews/kakaomap/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "appVersion": "6.6.0",
    "pf": "PC",
}


def get_rating(place_id: str) -> tuple[float | None, int | None]:
    params = urllib.parse.urlencode({"order": "RECOMMENDED", "only_photo_review": "false"})
    req = urllib.request.Request(
        f"{BASE_URL}{urllib.parse.quote(place_id)}?{params}",
        headers={**HEADERS, "Referer": f"https://place.map.kakao.com/{place_id}"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.loads(response.read().decode("utf-8"))
    score = data.get("score_set") or {}
    rating = score.get("average_score")
    count = score.get("review_count")
    return (float(rating) if rating is not None else None,
            int(count) if count is not None else None)


def save(rows: list[dict]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="re-fetch IDs already in the local CSV cache")
    args = parser.parse_args()

    places = json.loads(PLACES_PATH.read_text(encoding="utf-8"))
    cached: dict[str, dict] = {}
    if OUT_PATH.exists():
        with OUT_PATH.open(encoding="utf-8", newline="") as f:
            cached = {row["kakao_place_id"]: row for row in csv.DictReader(f)}

    results: dict[str, dict] = dict(cached)
    for index, place in enumerate(places, 1):
        place_id = str(place["id"])
        if place_id in cached and not args.refresh:
            print(f"{index}/{len(places)} cached   {place['name'][:28]}")
            continue

        last_error = None
        for attempt in range(4):
            try:
                rating, count = get_rating(place_id)
                if rating is not None and not 0 < rating <= 5:
                    rating = None
                if rating is None:
                    count = None
                row = {
                    "kakao_place_id": place_id,
                    "name": place["name"],
                    "rating": rating if rating is not None else "",
                    "review_count": count if count is not None else "",
                    "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "status": "ok" if rating is not None else "no_rating",
                }
                results[place_id] = row
                print(f"{index}/{len(places)} {row['status']:<9} {place['name'][:28]}")
                save([results[str(p["id"])] for p in places if str(p["id"]) in results])
                time.sleep(0.25)
                break
            except urllib.error.HTTPError as error:
                last_error = error
                if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    break
                time.sleep(2 ** attempt)
            except Exception as error:  # preserve completed rows, then continue/report
                last_error = error
                break
        else:
            last_error = last_error or RuntimeError("request failed")

        if last_error is not None:
            save([results[str(p["id"])] for p in places if str(p["id"]) in results])
            print(f"{index}/{len(places)} ERROR {place['name'][:28]}: {last_error}")
            time.sleep(1)

    final_rows = [results[str(place["id"])] for place in places if str(place["id"]) in results]
    save(final_rows)
    rated = sum(bool(row["rating"]) for row in final_rows)
    print(f"\n완료: {len(final_rows)}/{len(places)} places, 평점 있음 {rated} -> {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
