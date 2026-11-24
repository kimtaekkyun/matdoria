"""매칭 결과(high)를 카카오 장소 ID 기준으로 합쳐 웹앱용 JSON을 만든다.

사용법:
    python scripts/export_places.py

입력:  data/processed/places_matched.csv, data/raw/google/ratings.csv, data/processed/kakao_ratings.csv
출력:  web/public/data/places.json (출처, Matdoria's Pick, 평점 snapshot 포함)

MVP 정책 (D-018): match_confidence == high 만 사용한다. medium은 제외.
같은 카카오 장소가 여러 출처에 있으면 하나의 장소로 합치고 출처 정보를 모두 담는다.
Matdoria's Pick은 `data/curation/matdoria_pick_score_v1.json` 설정으로 계산한다.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path

from score_matdoria_pick import (
    assemble_canonical_review_counts,
    build_stamp,
    normalize_timestamp,
    score_rows,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "processed" / "places_matched.csv"
OUT = ROOT / "web" / "public" / "data" / "places.json"
PICK_CONFIG = ROOT / "data" / "curation" / "matdoria_pick_score_v1.json"
GOOGLE_RATINGS = ROOT / "data" / "raw" / "google" / "ratings.csv"
KAKAO_RATINGS = ROOT / "data" / "processed" / "kakao_ratings.csv"
PUBLIC_MATCHES = ROOT / "data" / "processed" / "public_sources_matched.csv"
LICENSE_MATCHES = ROOT / "data" / "processed" / "seoul_restaurant_licenses_matched.csv"
SCORE_OUTPUT_DIR = ROOT / "data" / "processed" / "matdoria_pick_scores"
BUILD_INFO = ROOT / "web" / "public" / "data" / "build-info.json"
BUILD_HISTORY = ROOT / "data" / "processed" / "build_history.jsonl"


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
        try:
            menu_items = json.loads(row.get("menu_items", "[]"))
        except (TypeError, json.JSONDecodeError):
            menu_items = []
        if not menu_items and row.get("menu_name"):
            price = row.get("menu_price", "")
            menu_items = [{"name": row["menu_name"], "price": int(price) if price.isdigit() else None}]
        return {
            "source": source,
            "label": "착한가격업소",
            "category": row.get("category", ""),
            "categoryGroup": row.get("source_category", ""),
            "menuItems": menu_items,
            "url": row.get("source_url", ""),
            "originalName": row["name"],
        }

    if source == "model_restaurant":
        return {
            "source": source,
            "label": "모범음식점",
            "category": row.get("category", ""),
            "foodType": row.get("food_type", ""),
            "year": int(row["selected_year"]) if row.get("selected_year", "").isdigit() else None,
            "url": row.get("source_url", ""),
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


def pick_entry(place_id: str, scored_places: dict[str, dict], profile: dict) -> dict:
    scored = scored_places.get(str(place_id), {})
    popularity_name = next(
        (name for name, dim in profile["dimensions"].items() if dim.get("type") == "review_count_thresholds"),
        "",
    )
    popularity = scored.get("dimensions", {}).get(popularity_name, {})
    return {
        "selected": bool(scored.get("selected")),
        "profileVersion": profile.get("profileVersion", "draft"),
        "reviewCounts": popularity.get("counts", {"kakaoReviewCount": None, "googleUserRatingCount": None}),
        "thresholds": popularity.get("thresholds", profile["dimensions"].get(popularity_name, {}).get("thresholds", {})),
    }


def encoded_json(payload: dict | list) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def json_sha256(payload: dict | list) -> str:
    return hashlib.sha256(encoded_json(payload).encode("utf-8")).hexdigest()


def write_json_atomic(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        stream.write(encoded_json(payload))
        temporary = Path(stream.name)
    os.replace(temporary, path)


def load_previous_build() -> dict | None:
    if not BUILD_HISTORY.exists():
        return None
    for line in reversed(BUILD_HISTORY.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            return json.loads(line)
    return None


def load_source_metadata() -> dict[str, dict]:
    source_files = {
        "michelin": ROOT / "data" / "processed" / "michelin_seoul.csv",
        "seoul_heritage": ROOT / "data" / "processed" / "seoul_heritage_food.csv",
        "good_price": ROOT / "data" / "processed" / "good_price_seoul.csv",
        "hundred_store": ROOT / "data" / "processed" / "hundred_stores.csv",
        "gwangjin_hygiene": ROOT / "data" / "processed" / "gwangjin_hygiene.csv",
        "seoul_restaurant_licenses": ROOT / "data" / "processed" / "seoul_restaurant_licenses.csv.gz",
        "seoul_restaurant_license_matches": LICENSE_MATCHES,
    }
    result: dict[str, dict] = {}
    for source, path in source_files.items():
        if not path.is_file():
            continue
        opener = gzip.open if path.suffix == ".gz" else open
        row_count = 0
        snapshots: set[str] = set()
        collected: set[str] = set()
        source_modified: set[str] = set()
        data_go_modified: set[str] = set()
        with opener(path, "rt", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                row_count += 1
                snapshot = row.get("source_snapshot") or ""
                collected_at = row.get("fetched_at") or row.get("collected_at") or ""
                modified_at = row.get("source_modified_at") or ""
                data_go_modified_at = row.get("data_go_modified_at") or ""
                if snapshot:
                    snapshots.add(snapshot)
                if collected_at:
                    collected.add(collected_at)
                if modified_at:
                    source_modified.add(modified_at)
                if data_go_modified_at:
                    data_go_modified.add(data_go_modified_at)
        result[source] = {
            "rowCount": row_count,
            "sourceSnapshots": sorted(snapshots),
            "collectedAt": sorted(collected),
            "sourceModifiedAt": sorted(source_modified),
            "dataGoModifiedAt": sorted(data_go_modified),
            "inputSha256": sha256_file(path),
        }
    return result


def load_rating_metadata() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for source, path in (("google", GOOGLE_RATINGS), ("kakao", KAKAO_RATINGS)):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            rating_rows = list(csv.DictReader(f))
        collected = sorted({r.get("collected_at", "") for r in rating_rows if r.get("collected_at")})
        result[source] = {
            "rowCount": len(rating_rows),
            "collectedAt": collected[-1:] if collected else [],
            "collectionWindow": [collected[0], collected[-1]] if collected else [],
            "inputSha256": sha256_file(path),
        }
    return result


def main(build_timestamp: str | None = None) -> None:
    with SRC.open(encoding="utf-8-sig", newline="") as f:
        matched_rows = list(csv.DictReader(f))
    public_rows: list[dict[str, str]] = []
    if PUBLIC_MATCHES.exists():
        with PUBLIC_MATCHES.open(encoding="utf-8-sig", newline="") as f:
            public_rows = list(csv.DictReader(f))
    rows = [r for r in matched_rows if r.get("match_confidence") == "high"]
    rows.extend(r for r in public_rows if r.get("match_confidence") == "high")

    profile = json.loads(PICK_CONFIG.read_text(encoding="utf-8"))
    timestamp = normalize_timestamp(build_timestamp)
    source_metadata = load_source_metadata()
    rating_metadata = load_rating_metadata()
    kakao_rating_rows: list[dict[str, str]] = []
    if KAKAO_RATINGS.is_file():
        with KAKAO_RATINGS.open(encoding="utf-8-sig", newline="") as f:
            kakao_rating_rows = list(csv.DictReader(f))
    google_rating_rows: list[dict[str, str]] = []
    if GOOGLE_RATINGS.is_file():
        with GOOGLE_RATINGS.open(encoding="utf-8-sig", newline="") as f:
            google_rating_rows = list(csv.DictReader(f))
    score_input_hashes = {
        "profile": sha256_file(PICK_CONFIG),
        "places_matched": sha256_file(SRC),
        "public_sources_matched": sha256_file(PUBLIC_MATCHES) if PUBLIC_MATCHES.is_file() else None,
        "kakao_ratings": sha256_file(KAKAO_RATINGS) if KAKAO_RATINGS.is_file() else None,
        "google_ratings": sha256_file(GOOGLE_RATINGS) if GOOGLE_RATINGS.is_file() else None,
    }
    code_hashes = {
        "score_matdoria_pick.py": sha256_file(ROOT / "scripts" / "score_matdoria_pick.py"),
        "export_places.py": sha256_file(Path(__file__).resolve()),
    }
    input_hashes = {
        **score_input_hashes,
        "normalized_sources": {source: value["inputSha256"] for source, value in source_metadata.items()},
        "rating_snapshots": {source: value["inputSha256"] for source, value in rating_metadata.items()},
        "code": code_hashes,
    }
    for row in matched_rows:
        metadata = source_metadata.get(row.get("source", ""), {})
        if row.get("source") == "michelin" and not row.get("source_snapshot"):
            snapshots = metadata.get("sourceSnapshots", [])
            if snapshots:
                row["source_snapshot"] = snapshots[-1]
        if row.get("source") == "seoul_heritage" and not row.get("collected_at"):
            collected = metadata.get("collectedAt", [])
            if collected:
                row["collected_at"] = collected[-1]
    review_counts = assemble_canonical_review_counts(
        kakao_rating_rows, google_rating_rows, matched_rows, public_rows,
    )
    score_payload = score_rows(
        matched_rows, public_rows, profile, timestamp, score_input_hashes,
        review_counts=review_counts,
    )
    scored_places = {item["placeId"]: item for item in score_payload["places"]}

    google_ratings_by_source: dict[tuple[str, str], dict] = {}
    for rating in google_rating_rows:
        try:
            close_enough = float(rating.get("distance_m", "")) <= 100
        except ValueError:
            close_enough = False
        if rating.get("status") == "ok" and close_enough and rating.get("google_place_id"):
            google_ratings_by_source[(rating["source"], rating["src_id"])] = rating

    kakao_ratings: dict[str, dict] = {
        row["kakao_place_id"]: row
        for row in kakao_rating_rows
        if row.get("kakao_place_id") and row.get("status") == "ok"
    }

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
        kakao_count_raw = str(kakao_row.get("review_count") or "").strip().replace(",", "")
        kakao_count = int(kakao_count_raw) if kakao_count_raw.isdigit() else None
        place["ratings"] = {
            "kakao": {
                "rating": kakao_rating,
                "count": kakao_count,
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
                count_raw = str(snapshot.get("user_rating_count") or "").strip().replace(",", "")
                count = int(count_raw) if count_raw.isdigit() else None
                place["ratings"]["google"] = {
                    "rating": value,
                    "count": count,
                }

    for place_id, place in places.items():
        place["matdoriaPick"] = pick_entry(place_id, scored_places, profile)

    result = sorted(places.values(), key=lambda p: p["name"])
    score_payload["metadata"]["inputSha256"]["normalizedSources"] = input_hashes["normalized_sources"]
    score_payload["metadata"]["codeSha256"] = code_hashes
    score_payload["metadata"]["sourceMetadata"] = {
        source: {key: value for key, value in values.items() if key != "inputSha256"}
        for source, values in source_metadata.items()
    }

    # Keep an immutable score/evidence snapshot for each build.
    score_path = SCORE_OUTPUT_DIR / f"{build_stamp(timestamp)}.json"
    score_path.parent.mkdir(parents=True, exist_ok=True)
    with score_path.open("x", encoding="utf-8") as f:
        json.dump(score_payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    previous = load_previous_build()
    selected_ids = sorted(item["placeId"] for item in score_payload["places"] if item["selected"])
    changed_inputs = sorted(
        key for key, value in input_hashes.items()
        if previous and previous.get("inputSha256", {}).get(key) != value
    )
    # Public build metadata is intentionally minimal. Detailed source and rating
    # timestamps, code/data hashes, and score evidence stay in repository-only files.
    popularity_profile = next(
        dim for dim in profile["dimensions"].values()
        if dim.get("type") == "review_count_thresholds"
    )
    profile_thresholds = popularity_profile["thresholds"]
    build_info = {
        "buildTimestamp": timestamp,
        "selectedPlaceCount": len(selected_ids),
        "reviewCountThresholds": {
            "kakaoReviewCount": int(profile_thresholds["kakao_review_count"]),
            "googleUserRatingCount": int(profile_thresholds["google_user_rating_count"]),
        },
    }
    write_json_atomic(OUT, result)
    write_json_atomic(BUILD_INFO, build_info)

    history = {
        "buildTimestamp": timestamp,
        "profileId": profile["profileId"],
        "profileVersion": profile["profileVersion"],
        "candidatePlaceCount": score_payload["metadata"]["candidatePlaceCount"],
        "reviewCountCoverage": score_payload["reviewCountCoverage"],
        "inputSha256": input_hashes,
        "sources": source_metadata,
        "ratingSnapshots": {
            source: {key: value for key, value in values.items() if key != "inputSha256"}
            for source, values in rating_metadata.items()
        },
        "selectedPlaceCount": len(selected_ids),
        "selectedPlaceIds": selected_ids,
        "changedInputsSincePreviousBuild": changed_inputs,
        "scoreSnapshot": str(score_path.relative_to(ROOT)),
        "placesJsonSha256": json_sha256(result),
    }
    if previous:
        old_ids = set(previous.get("selectedPlaceIds", []))
        new_ids = set(selected_ids)
        history["addedSelectedPlaceIds"] = sorted(new_ids - old_ids)
        history["removedSelectedPlaceIds"] = sorted(old_ids - new_ids)
    BUILD_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with BUILD_HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(history, ensure_ascii=False) + "\n")

    michelin_n = sum(1 for p in result if any(s["source"] == "michelin" for s in p["sources"]))
    heritage_n = sum(1 for p in result if any(s["source"] == "seoul_heritage" for s in p["sources"]))
    pick_n = score_payload["metadata"]["selectedPlaceCount"]
    print(f"장소 {len(result)}곳 (미쉐린 {michelin_n}, 서울미래유산 {heritage_n}, Matdoria's Pick {pick_n}) -> {OUT.relative_to(ROOT)}")
    print(f"점수 근거 snapshot -> {score_path.relative_to(ROOT)}; build metadata -> {BUILD_INFO.relative_to(ROOT)}")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Build the static Matdoria dataset and score audit snapshot.")
    parser.add_argument("--build-timestamp", help="fixed ISO-8601 timestamp (UTC assumed if no zone)")
    args = parser.parse_args()
    main(args.build_timestamp)


if __name__ == "__main__":
    cli()
