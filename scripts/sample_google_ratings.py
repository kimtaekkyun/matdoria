"""Google Places API(New)로 식당 평점과 리뷰 수를 샘플 조회한다 (실험용).

사용법:
    python scripts/sample_google_ratings.py [개수]

- 입력: data/processed/places_matched.csv 중 미쉐린 high 항목
- 키: 루트 .env.local 의 GOOGLE_PLACES_API_KEY (값은 출력하지 않음)
- 출력: 콘솔 표 (결과는 파일로 저장하지 않음)
- 매칭 검증: 반환된 좌표와 카카오 좌표의 거리(m)를 함께 표시한다.
"""

from __future__ import annotations

import csv
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
MATCHED_PATH = ROOT / "data" / "processed" / "places_matched.csv"
ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount"


def load_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_PLACES_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GOOGLE_PLACES_API_KEY가 .env.local에 없습니다.")


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search(key: str, name: str, lat: float, lng: float) -> dict | None:
    body = {
        "textQuery": f"{name} Seoul",
        "languageCode": "en",
        "maxResultCount": 1,
        "locationBias": {
            "circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 300.0}
        },
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
    places = data.get("places") or []
    return places[0] if places else None


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    key = load_key()
    with MATCHED_PATH.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["source"] == "michelin" and r["match_confidence"] == "high"]
    rows = rows[:n]

    print(f"{'미쉐린 이름':<26}{'Google 이름':<34}{'평점':>5}{'리뷰수':>8}{'거리(m)':>9}")
    for r in rows:
        lat, lng = float(r["lat"]), float(r["lng"])
        hit = search(key, r["michelin_name"] or r["name"], lat, lng)
        if hit is None:
            print(f"{r['name'][:24]:<26}{'(결과 없음)':<34}")
            continue
        loc = hit.get("location", {})
        dist = haversine_m(lat, lng, loc.get("latitude", lat), loc.get("longitude", lng))
        gname = hit.get("displayName", {}).get("text", "")
        rating = hit.get("rating")
        count = hit.get("userRatingCount")
        print(
            f"{r['name'][:24]:<26}{gname[:32]:<34}"
            f"{(f'{rating:.1f}' if rating is not None else '-'):>5}"
            f"{(str(count) if count is not None else '-'):>8}"
            f"{dist:>9.0f}"
        )


if __name__ == "__main__":
    main()
