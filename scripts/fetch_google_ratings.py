"""매칭된 전체 장소에 대해 Google Places(New) 평점과 리뷰 수를 조회한다.

사용법:
    python scripts/fetch_google_ratings.py

- 입력: data/processed/places_matched.csv (confidence high 전체)
- 키: .env.local 의 GOOGLE_PLACES_API_KEY (출력하지 않음)
- 출력: data/raw/google/ratings.csv (git 미추적). 한 번 조회한 항목은 캐시에서 재사용한다.
- 약관: 평점과 리뷰 수 같은 Google 콘텐츠는 캐시 기간에 제한이 있다. 웹앱 배포본에 넣기 전에
  공식 약관을 확인하고, 필요하면 주기적으로 다시 조회한다.
"""

from __future__ import annotations

import csv
import json
import math
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env.local"
MATCHED_PATH = ROOT / "data" / "processed" / "places_matched.csv"
OUT_DIR = ROOT / "data" / "raw" / "google"
OUT_PATH = OUT_DIR / "ratings.csv"
ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = "places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount"
COLUMNS = ["source", "src_id", "name", "query", "google_place_id", "google_name", "google_address",
           "rating", "user_rating_count", "distance_m", "status"]


def load_key() -> str:
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("GOOGLE_PLACES_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GOOGLE_PLACES_API_KEY가 .env.local에 없습니다.")


def haversine_m(lat1, lng1, lat2, lng2) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search(key: str, query: str, lat: float, lng: float) -> dict | None:
    body = {
        "textQuery": f"{query} Seoul",
        "languageCode": "en",
        "maxResultCount": 1,
        "locationBias": {"circle": {"center": {"latitude": lat, "longitude": lng}, "radius": 300.0}},
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    places = data.get("places") or []
    return places[0] if places else None


def save(results: list[dict]) -> None:
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(results)


def main() -> None:
    key = load_key()
    with MATCHED_PATH.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["match_confidence"] == "high"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cached: dict[tuple[str, str], dict] = {}
    if OUT_PATH.exists():
        with OUT_PATH.open(encoding="utf-8", newline="") as f:
            for c in csv.DictReader(f):
                cached[(c["source"], c["src_id"])] = c

    results = []
    for i, r in enumerate(rows, 1):
        k = (r["source"], r["src_id"])
        if k in cached:
            results.append(cached[k])
            continue
        query = r.get("michelin_name") or r["name"]
        lat, lng = float(r["lat"]), float(r["lng"])
        try:
            hit = search(key, query, lat, lng)
        except urllib.error.HTTPError as e:
            # 중간 결과를 저장해 두고 중단한다. 다시 실행하면 저장된 항목은 건너뛴다.
            save(results)
            raise SystemExit(f"HTTP {e.code} at {i}/{len(rows)} (중간 결과 {len(results)}곳 저장): "
                             f"{e.read().decode('utf-8', 'replace')[:200]}")
        row = {c: "" for c in COLUMNS}
        row.update({"source": r["source"], "src_id": r["src_id"], "name": r["name"], "query": query})
        if hit is None:
            row["status"] = "no_result"
        else:
            loc = hit.get("location", {})
            dist = haversine_m(lat, lng, loc.get("latitude", lat), loc.get("longitude", lng))
            row.update({
                "google_place_id": hit.get("id", ""),
                "google_name": hit.get("displayName", {}).get("text", ""),
                "google_address": hit.get("formattedAddress", ""),
                "rating": hit.get("rating", ""),
                "user_rating_count": hit.get("userRatingCount", ""),
                "distance_m": f"{dist:.0f}",
                "status": "ok" if dist <= 100 else "far",
            })
        results.append(row)
        print(f"{i}/{len(rows)} {row['status']:<10} {r['name'][:28]}")

    save(results)
    ok = [x for x in results if x["status"] == "ok"]
    print(f"\n전체 {len(results)}곳 / 좌표 100m 이내 매칭 {len(ok)}곳 -> {OUT_PATH}")


if __name__ == "__main__":
    main()
