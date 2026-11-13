"""매칭 결과(high)를 카카오 장소 ID 기준으로 합쳐 웹앱용 JSON을 만든다.

사용법:
    python scripts/export_places.py

입력:  data/processed/places_matched.csv, data/raw/google/ratings.csv, data/processed/kakao_ratings.csv
출력:  web/public/data/places.json (출처, Matdoria's Pick, 평점 snapshot 포함)

MVP 정책 (D-018): match_confidence == high 만 사용한다. medium은 제외.
같은 카카오 장소가 여러 출처에 있으면 하나의 장소로 합치고 출처 정보를 모두 담는다.
Matdoria's Pick은 data/curation/matdoria_pick.json 설정으로 계산한다.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "places_matched.csv"
OUT = ROOT / "web" / "public" / "data" / "places.json"
PICK_CONFIG = ROOT / "data" / "curation" / "matdoria_pick.json"
GOOGLE_RATINGS = ROOT / "data" / "raw" / "google" / "ratings.csv"
KAKAO_RATINGS = ROOT / "data" / "processed" / "kakao_ratings.csv"


def source_entry(row: dict) -> dict:
    source = row["source"]
    if source == "michelin":
        return {
            "source": source,
            "label": "미쉐린 가이드",
            "award": row["src_group"],
            "price": row.get("price", ""),
            "cuisine": row.get("cuisine", ""),
            "url": row["source_url"],
            "originalName": row.get("michelin_name", row["name"]),
            "sourceRecordId": row["src_id"],
        }
    if source == "seoul_heritage":
        return {
            "source": source,
            "label": "서울미래유산",
            "group": row["src_group"],
            "openedYear": int(row["opened_year"]) if row.get("opened_year") else None,
            "selectedYear": int(row["heritage_selected_year"]) if row.get("heritage_selected_year") else None,
            "url": row["source_url"],
            "originalName": row["name"],
            "sourceRecordId": row["src_id"],
        }
    if source == "good_price":
        price = row.get("menu_price", "")
        return {
            "source": source,
            "label": "착한가격업소",
            "category": row.get("category", ""),
            "menuName": row.get("menu_name", ""),
            "menuPrice": int(price) if price.isdigit() else None,
            "url": row["source_url"],
            "originalName": row["name"],
        }

    labels = {
        "model_restaurant": "모범음식점",
        "seoul_gourmet_100": "서울미식 100선",
        "hundred_store": "백년가게",
    }
    return {
        "source": source,
        "label": labels[source],
        "category": row.get("src_group", ""),
        "year": int(row["heritage_selected_year"]) if row.get("heritage_selected_year") else None,
        "url": row.get("source_url", ""),
        "originalName": row["name"],
    }


def pick_entry(place: dict, config: dict) -> dict:
    source_weights = config.get("sourceWeights", {})
    award_scores = config.get("michelinAwardScores", {})
    heritage_scores = config.get("heritageGroupScores", {})
    best_by_source: dict[str, float] = {}
    reasons: list[str] = []

    for source in place["sources"]:
        source_type = source["source"]
        if source_type == "michelin":
            points = float(award_scores.get(source["award"], source_weights.get(source_type, 0)))
            label = source["award"]
        elif source_type == "seoul_heritage":
            points = float(heritage_scores.get(source["group"], source_weights.get(source_type, 0)))
            label = source["group"]
        else:
            points = float(source_weights.get(source_type, 0))
            label = source["label"]
        best_by_source[source_type] = max(best_by_source.get(source_type, 0), points)
        if points > 0:
            reasons.append(f"{source['label']}: {label} (+{points:g})")

    score = sum(best_by_source.values())
    place_id = str(place["id"])
    included = place_id in {str(value) for value in config.get("includePlaceIds", [])}
    excluded = place_id in {str(value) for value in config.get("excludePlaceIds", [])}
    minimum = config.get("minimumScore")
    selected = not excluded and (included or (minimum is not None and score >= float(minimum)))
    if included and not excluded and not reasons:
        reasons.append("설정에서 직접 선택")

    return {
        "selected": selected,
        "score": score,
        "reasons": reasons,
        "profileVersion": config.get("profileVersion", "draft"),
    }


def main() -> None:
    with SRC.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["match_confidence"] == "high"]

    google_ratings_by_source: dict[tuple[str, str], dict] = {}
    if GOOGLE_RATINGS.exists():
        with GOOGLE_RATINGS.open(encoding="utf-8", newline="") as f:
            for rating in csv.DictReader(f):
                try:
                    close_enough = float(rating.get("distance_m", "")) <= 100
                except ValueError:
                    close_enough = False
                if rating.get("status") == "ok" and close_enough and rating.get("google_place_id"):
                    google_ratings_by_source[(rating["source"], rating["src_id"])] = rating

    kakao_ratings: dict[str, dict] = {}
    if KAKAO_RATINGS.exists():
        with KAKAO_RATINGS.open(encoding="utf-8", newline="") as f:
            kakao_ratings = {row["kakao_place_id"]: row for row in csv.DictReader(f)}

    places: dict[str, dict] = {}
    google_ids_by_place: dict[str, set[str]] = {}
    google_rows_by_place: dict[str, list[dict]] = {}
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
        google_row = google_ratings_by_source.get((r["source"], r["src_id"]))
        if google_row:
            google_ids_by_place.setdefault(kid, set()).add(google_row["google_place_id"])
            google_rows_by_place.setdefault(kid, []).append(google_row)

    for place_id, place in places.items():
        kakao_row = kakao_ratings.get(place_id, {})
        kakao_rating = float(kakao_row["rating"]) if kakao_row.get("rating") else None
        if kakao_rating is not None and not 0 < kakao_rating <= 5:
            kakao_rating = None
        kakao_count = kakao_row.get("review_count", "") if kakao_rating is not None else ""
        place["ratings"] = {
            "kakao": {
                "rating": kakao_rating,
                "count": int(kakao_count) if kakao_count else None,
                "collectedAt": kakao_row.get("collected_at") or None,
            },
            "google": None,
        }

        google_ids = google_ids_by_place.get(place_id, set())
        # If source records point to different Google places, don't guess which one to display.
        if len(google_ids) == 1:
            google_id = next(iter(google_ids))
            place["googlePlaceId"] = google_id
            candidates = [r for r in google_rows_by_place.get(place_id, []) if r["google_place_id"] == google_id]
            candidates.sort(key=lambda r: float(r.get("distance_m") or 1e9))
            if candidates:
                snapshot = candidates[0]
                value = float(snapshot["rating"]) if snapshot.get("rating") else None
                if value is not None and not 0 < value <= 5:
                    value = None
                count = snapshot.get("user_rating_count", "") if value is not None else ""
                place["ratings"]["google"] = {
                    "rating": value,
                    "count": int(count) if count else None,
                    "collectedAt": snapshot.get("collected_at") or None,
                }

    pick_config = json.loads(PICK_CONFIG.read_text(encoding="utf-8"))
    for place in places.values():
        place["matdoriaPick"] = pick_entry(place, pick_config)

    result = sorted(places.values(), key=lambda p: p["name"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    michelin_n = sum(1 for p in result if any(s["source"] == "michelin" for s in p["sources"]))
    heritage_n = sum(1 for p in result if any(s["source"] == "seoul_heritage" for s in p["sources"]))
    pick_n = sum(1 for p in result if p["matdoriaPick"]["selected"])
    print(f"장소 {len(result)}곳 (미쉐린 {michelin_n}, 서울미래유산 {heritage_n}, Matdoria's Pick {pick_n}) -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
