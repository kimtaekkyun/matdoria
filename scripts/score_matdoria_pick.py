#!/usr/bin/env python3
"""Build an explainable offline Matdoria's Pick score snapshot.

Pick qualification uses review-count thresholds only. Platform star averages
are never read. Michelin, Seoul Heritage, and Good Price are retained as
independent diagnostic dimensions and cannot affect selection.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "data/curation/matdoria_pick_score_v1.json"
DEFAULT_PLACES = ROOT / "data/processed/places_matched.csv"
DEFAULT_PUBLIC = ROOT / "data/processed/public_sources_matched.csv"
DEFAULT_KAKAO_RATINGS = ROOT / "data/processed/kakao_ratings.csv"
DEFAULT_GOOGLE_RATINGS = ROOT / "data/raw/google/ratings.csv"
DEFAULT_OUTPUT_DIR = ROOT / "data/processed/matdoria_pick_scores"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def normalize_timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def build_stamp(timestamp: str) -> str:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return parsed.strftime("%Y%m%dT%H%M%S%fZ")


def _nonnegative_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or not text.isdigit():
        return None
    number = int(text)
    return number if number >= 0 else None


def _distance(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _matched_place_links(
    matched_rows: list[dict[str, str]],
    public_rows: list[dict[str, str]],
) -> tuple[set[str], dict[tuple[str, str], set[str]]]:
    place_ids: set[str] = set()
    links: dict[tuple[str, str], set[str]] = {}
    for row in [*matched_rows, *public_rows]:
        if row.get("match_confidence") != "high":
            continue
        place_id = str(row.get("match_kakao_id") or "").strip()
        source = str(row.get("source") or "").strip()
        source_id = str(row.get("src_id") or "").strip()
        if not place_id:
            continue
        place_ids.add(place_id)
        if source and source_id:
            links.setdefault((source, source_id), set()).add(place_id)
    return place_ids, links


def assemble_canonical_review_counts(
    kakao_rows: list[dict[str, str]],
    google_rows: list[dict[str, str]],
    matched_rows: list[dict[str, str]],
    public_rows: list[dict[str, str]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Assemble canonical review-count evidence keyed by Kakao place ID.

    Kakao counts join directly by ``kakao_place_id`` and require ``status=ok``.
    Google counts join ``(source, src_id)`` to high-confidence rows from the
    matched/public inputs, require ``status=ok`` and distance <= 100m, and are
    accepted only when all eligible joins for a canonical place agree on one
    Google Place ID. For that ID, the nearest eligible row supplies its count.

    The result value is ``{"placeId": str, "kakao": {...}, "google": {...}}``;
    each platform object has ``count`` (int or None), ``status`` (``known`` or
    ``unknown``), ``reason`` when unknown, and source ``evidence`` records.
    No average-rating column is read or returned.
    """
    public_rows = public_rows or []
    place_ids, source_links = _matched_place_links(matched_rows, public_rows)
    assembled: dict[str, dict[str, Any]] = {
        place_id: {
            "placeId": place_id,
            "kakao": {"count": None, "status": "unknown", "reason": "no_valid_kakao_count", "evidence": []},
            "google": {"count": None, "status": "unknown", "reason": "no_eligible_google_count", "evidence": []},
        }
        for place_id in sorted(place_ids)
    }

    kakao_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in kakao_rows:
        place_id = str(row.get("kakao_place_id") or "").strip()
        if place_id not in assembled:
            continue
        count = _nonnegative_int(row.get("review_count"))
        accepted = row.get("status") == "ok" and count is not None
        evidence: dict[str, Any] = {
            "source": "kakao",
            "kakaoPlaceId": place_id,
            "status": row.get("status") or "unknown",
            "reviewCount": count,
            "collectedAt": row.get("collected_at") or None,
            "accepted": accepted,
        }
        if not accepted:
            evidence["exclusionReason"] = "status_not_ok" if row.get("status") != "ok" else "invalid_or_missing_review_count"
        kakao_by_id.setdefault(place_id, []).append({"row": row, "count": count, "evidence": evidence, "accepted": accepted})

    for place_id, records in kakao_by_id.items():
        valid = [item for item in records if item["accepted"]]
        if not valid:
            assembled[place_id]["kakao"]["evidence"] = [item["evidence"] for item in records]
            continue
        # Select the most recent snapshot; conflicting values at that same
        # timestamp are ambiguous rather than silently aggregated.
        latest = max(str(item["row"].get("collected_at") or "") for item in valid)
        latest_records = [item for item in valid if str(item["row"].get("collected_at") or "") == latest]
        latest_counts = {item["count"] for item in latest_records}
        if len(latest_counts) != 1:
            assembled[place_id]["kakao"].update({
                "reason": "conflicting_kakao_counts_at_latest_timestamp",
                "evidence": [item["evidence"] for item in records],
            })
            continue
        chosen = sorted(latest_records, key=lambda item: (item["count"], str(item["row"].get("name") or "")))[0]
        chosen["evidence"]["selected"] = True
        for item in records:
            item["evidence"].setdefault("selected", False)
        assembled[place_id]["kakao"].update({
            "count": chosen["count"],
            "status": "known",
            "reason": None,
            "evidence": [item["evidence"] for item in records],
        })

    google_by_place: dict[str, list[dict[str, Any]]] = {place_id: [] for place_id in assembled}
    for row in google_rows:
        pair = (str(row.get("source") or "").strip(), str(row.get("src_id") or "").strip())
        linked_ids = source_links.get(pair, set())
        if not linked_ids:
            continue
        count = _nonnegative_int(row.get("user_rating_count"))
        distance = _distance(row.get("distance_m"))
        google_id = str(row.get("google_place_id") or "").strip()
        eligible = row.get("status") == "ok" and distance is not None and distance <= 100 and bool(google_id)
        reason = None
        if len(linked_ids) != 1:
            reason = "source_record_maps_to_multiple_canonical_places"
            eligible = False
        elif row.get("status") != "ok":
            reason = "status_not_ok"
        elif distance is None or distance > 100:
            reason = "distance_missing_or_over_100m"
        elif not google_id:
            reason = "missing_google_place_id"
        evidence = {
            "source": "google",
            "sourceRecordId": row.get("src_id") or None,
            "sourceType": row.get("source") or None,
            "googlePlaceId": google_id or None,
            "distanceMeters": distance,
            "status": row.get("status") or "unknown",
            "userRatingCount": count,
            "countValid": count is not None,
            "collectedAt": row.get("collected_at") or None,
            "eligible": eligible,
        }
        if reason:
            evidence["exclusionReason"] = reason
        for place_id in linked_ids:
            if place_id in google_by_place:
                google_by_place[place_id].append({
                    "row": row, "count": count, "distance": distance,
                    "googlePlaceId": google_id, "eligible": eligible,
                    "evidence": dict(evidence),
                })

    for place_id, records in google_by_place.items():
        eligible = [item for item in records if item["eligible"]]
        google_ids = {item["googlePlaceId"] for item in eligible}
        if len(google_ids) > 1:
            assembled[place_id]["google"].update({
                "reason": "ambiguous_google_place_id",
                "evidence": [item["evidence"] for item in records],
            })
            continue
        if not eligible:
            assembled[place_id]["google"]["evidence"] = [item["evidence"] for item in records]
            continue
        # With one canonical Google ID, choose the closest eligible source row.
        chosen = sorted(eligible, key=lambda item: (
            item["distance"],
            str(item["row"].get("source") or ""),
            str(item["row"].get("src_id") or ""),
            str(item["row"].get("collected_at") or ""),
        ))[0]
        chosen["evidence"]["selected"] = True
        for item in records:
            item["evidence"].setdefault("selected", False)
        if chosen["count"] is None:
            assembled[place_id]["google"].update({
                "reason": "closest_eligible_google_row_has_no_valid_count",
                "googlePlaceId": chosen["googlePlaceId"],
                "distanceMeters": chosen["distance"],
                "evidence": [item["evidence"] for item in records],
            })
            continue
        assembled[place_id]["google"].update({
            "count": chosen["count"],
            "status": "known",
            "reason": None,
            "googlePlaceId": chosen["googlePlaceId"],
            "distanceMeters": chosen["distance"],
            "evidence": [item["evidence"] for item in records],
        })
    return assembled


def source_evidence(row: dict[str, str], source: str) -> dict[str, Any]:
    """Return source-specific diagnostic evidence; never include star averages."""
    common: dict[str, Any] = {
        "source": source,
        "sourceRecordId": row.get("src_id") or None,
        "sourceUrl": row.get("source_url") or None,
        "originalName": row.get("michelin_name") or row.get("name") or None,
        "matchConfidence": row.get("match_confidence") or None,
        "matchRule": row.get("match_rule") or None,
    }
    if row.get("match_distance_m"):
        common["matchDistanceMeters"] = row["match_distance_m"]
    if source == "michelin":
        common.update({
            "award": row.get("src_group") or None,
            "priceCategory": row.get("price") or None,
            "cuisine": row.get("cuisine") or None,
            "sourceSnapshot": row.get("source_snapshot") or None,
            "collectedAt": row.get("collected_at") or None,
        })
    elif source == "seoul_heritage":
        common.update({
            "designationGroup": row.get("src_group") or None,
            "openedYear": row.get("opened_year") or None,
            "selectedYear": row.get("heritage_selected_year") or None,
            "collectedAt": row.get("collected_at") or None,
        })
    elif source == "good_price":
        menus: Any = []
        raw_menus = row.get("menu_items", "")
        if raw_menus:
            try:
                menus = json.loads(raw_menus)
            except json.JSONDecodeError:
                menus = None
        common.update({
            "designation": "good_price",
            "category": row.get("category") or None,
            "sourceCategory": row.get("source_category") or None,
            "menuItems": menus,
            "sourceSnapshot": row.get("source_snapshot") or None,
            "collectedAt": row.get("collected_at") or None,
        })
    return common


def _configured_points(row: dict[str, str], dimension: dict[str, Any]) -> tuple[float, str | None]:
    if dimension.get("source") == "good_price":
        if row.get("source") != "good_price":
            return 0.0, "source_not_configured"
        value = dimension.get("designationValue", "good_price")
        return (float(dimension["weight"]), None) if value == "good_price" else (0.0, "unconfigured_designation")
    field = str(dimension.get("scoreField", ""))
    value = row.get(field, "")
    points = dimension.get("weights", {}).get(value)
    if points is None:
        return 0.0, "unconfigured_or_inapplicable_value"
    return float(points), None


def _popularity_result(
    place_id: str,
    dimension: dict[str, Any],
    review_counts: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    place_counts = (review_counts or {}).get(place_id, {})
    kakao = place_counts.get("kakao", {})
    google = place_counts.get("google", {})
    thresholds = dimension["thresholds"]
    kakao_threshold = int(thresholds["kakao_review_count"])
    google_threshold = int(thresholds["google_user_rating_count"])
    kakao_count = _nonnegative_int(kakao.get("count")) if kakao.get("status") == "known" else None
    google_count = _nonnegative_int(google.get("count")) if google.get("status") == "known" else None
    evidence: list[dict[str, Any]] = []
    for platform, item, count, threshold, count_field in (
        ("kakao", kakao, kakao_count, kakao_threshold, "reviewCount"),
        ("google", google, google_count, google_threshold, "userRatingCount"),
    ):
        evidence.append({
            "source": platform,
            "countField": count_field,
            "count": count,
            "status": item.get("status", "unknown") if count is not None else "unknown",
            "reason": item.get("reason") if count is None else None,
            "threshold": threshold,
            "thresholdMet": count >= threshold if count is not None else None,
            "sourceEvidence": item.get("evidence", []),
            **({"googlePlaceId": item.get("googlePlaceId"), "distanceMeters": item.get("distanceMeters")} if platform == "google" else {}),
        })
    complete = kakao_count is not None and google_count is not None
    selected = bool(complete and kakao_count >= kakao_threshold and google_count >= google_threshold)
    score = (1.0 if selected else 0.0) if complete else None
    status = "qualified" if selected else ("not_qualified" if complete else "unknown")
    return {
        "label": dimension["label"],
        "score": score,
        "status": status,
        "source": dimension["source"],
        "evidenceCount": sum(len(item.get("sourceEvidence", [])) for item in evidence),
        "counts": {"kakaoReviewCount": kakao_count, "googleUserRatingCount": google_count},
        "thresholds": {"kakaoReviewCount": kakao_threshold, "googleUserRatingCount": google_threshold},
        "contributions": evidence,
    }


def score_rows(
    places_rows: list[dict[str, str]],
    public_rows: list[dict[str, str]],
    profile: dict[str, Any],
    build_timestamp: str,
    input_hashes: dict[str, str | None],
    review_counts: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a score payload. Optional ``review_counts`` comes from
    :func:`assemble_canonical_review_counts`; absent counts remain unknown.
    """
    place_map: dict[str, dict[str, Any]] = {}
    input_counts: dict[str, dict[str, int]] = {}
    configured_sources = {
        dimension["source"] for dimension in profile["dimensions"].values()
        if dimension.get("type") != "review_count_thresholds"
    }
    for rows in (places_rows, public_rows):
        for row in rows:
            source = row.get("source", "")
            if source not in configured_sources:
                continue
            counts = input_counts.setdefault(source, {"rows": 0, "highConfidenceMatched": 0})
            counts["rows"] += 1
            place_id = (row.get("match_kakao_id") or "").strip()
            if row.get("match_confidence") != "high" or not place_id:
                continue
            counts["highConfidenceMatched"] += 1
            item = place_map.setdefault(place_id, {
                "placeId": place_id, "name": "", "address": "", "kakaoUrl": "",
                "_names": set(), "_addresses": set(), "_urls": set(), "_records": [],
            })
            if row.get("match_kakao_name"):
                item["_names"].add(row["match_kakao_name"])
            if row.get("match_kakao_address"):
                item["_addresses"].add(row["match_kakao_address"])
            if row.get("match_kakao_url"):
                item["_urls"].add(row["match_kakao_url"])
            item["_records"].append((source, row))

    results: list[dict[str, Any]] = []
    dimension_place_coverage = {
        name: {"knownEvidencePlaces": 0, "scoredPlaces": 0}
        for name in profile["dimensions"]
    }
    review_coverage = {"kakaoCountPlaces": 0, "googleCountPlaces": 0, "bothCountPlaces": 0, "qualifyingPlaces": 0}
    selection_dimensions = set(profile.get("selection", {}).get("dimensions", []))
    for place_id in sorted(place_map):
        place = place_map[place_id]
        place["name"] = sorted(place.pop("_names"))[0] if place["_names"] else ""
        place["address"] = sorted(place.pop("_addresses"))[0] if place["_addresses"] else ""
        place["kakaoUrl"] = sorted(place.pop("_urls"))[0] if place["_urls"] else ""
        dimension_results: dict[str, Any] = {}
        all_evidence: list[dict[str, Any]] = []
        pick_score = 0.0
        any_pick_signal = False

        for dimension_name, dimension in profile["dimensions"].items():
            if dimension.get("type") == "review_count_thresholds":
                result = _popularity_result(place_id, dimension, review_counts)
                dimension_results[dimension_name] = result
                if result["counts"]["kakaoReviewCount"] is not None:
                    review_coverage["kakaoCountPlaces"] += 1
                if result["counts"]["googleUserRatingCount"] is not None:
                    review_coverage["googleCountPlaces"] += 1
                complete = result["status"] != "unknown"
                if complete:
                    review_coverage["bothCountPlaces"] += 1
                    dimension_place_coverage[dimension_name]["knownEvidencePlaces"] += 1
                    dimension_place_coverage[dimension_name]["scoredPlaces"] += 1
                if result["status"] == "qualified":
                    review_coverage["qualifyingPlaces"] += 1
                if dimension_name in selection_dimensions and complete:
                    pick_score = float(result["score"])
                    any_pick_signal = True
                all_evidence.extend(result["contributions"])
                continue

            relevant = [row for source, row in place["_records"] if source == dimension["source"]]
            if relevant:
                dimension_place_coverage[dimension_name]["knownEvidencePlaces"] += 1
            candidates: list[tuple[float, str, dict[str, str], str | None]] = []
            for row in relevant:
                points, reason = _configured_points(row, dimension)
                candidates.append((points, str(row.get("src_id", "")), row, reason))
            candidates.sort(key=lambda item: (-item[0], item[1]))
            winner = candidates[0] if candidates and candidates[0][0] > 0 else None
            dimension_score: float | None = winner[0] if winner else None
            contributions: list[dict[str, Any]] = []
            for points, _record_id, row, reason in candidates:
                evidence = source_evidence(row, dimension["source"])
                contribution = points if winner and row is winner[2] else 0.0
                if winner and row is not winner[2]:
                    reason = "additional_record_same_source_not_double_counted"
                evidence["contribution"] = contribution
                if reason:
                    evidence["notScoredReason"] = reason
                contributions.append(evidence)
                all_evidence.append(evidence)
            if winner:
                dimension_place_coverage[dimension_name]["scoredPlaces"] += 1
                if dimension_name in selection_dimensions:
                    pick_score += winner[0]
                    any_pick_signal = True
            dimension_results[dimension_name] = {
                "label": dimension["label"],
                "score": dimension_score,
                "status": "scored" if winner else ("not_applicable" if relevant else "unknown"),
                "source": dimension["source"],
                "selectionRole": dimension.get("selectionRole", "diagnostic_only"),
                "evidenceCount": len(relevant),
                "contributions": contributions,
            }

        minimum = float(profile.get("selection", {}).get("minimumScore", 0))
        selected = bool(any_pick_signal and pick_score >= minimum)
        results.append({
            "placeId": place_id,
            "name": place["name"],
            "address": place["address"],
            "kakaoUrl": place["kakaoUrl"],
            "pickScore": round(pick_score, 6) if any_pick_signal else None,
            "selected": selected,
            "pickScoreStatus": "scored" if any_pick_signal else "unknown",
            "dimensions": dimension_results,
            "evidence": all_evidence,
        })

    results.sort(key=lambda item: (
        item["pickScore"] is None,
        -(item["pickScore"] or 0),
        item["placeId"],
    ))
    denominator = len(place_map)
    coverage = {
        dimension_name: {
            **counts,
            "candidatePlaces": denominator,
            "knownEvidenceRate": round(counts["knownEvidencePlaces"] / denominator, 6) if denominator else None,
            "scoredPlaceRate": round(counts["scoredPlaces"] / denominator, 6) if denominator else None,
        }
        for dimension_name, counts in dimension_place_coverage.items()
    }
    review_coverage.update({
        "candidatePlaces": denominator,
        "kakaoCountRate": round(review_coverage["kakaoCountPlaces"] / denominator, 6) if denominator else None,
        "googleCountRate": round(review_coverage["googleCountPlaces"] / denominator, 6) if denominator else None,
        "bothCountRate": round(review_coverage["bothCountPlaces"] / denominator, 6) if denominator else None,
        "qualifyingRate": round(review_coverage["qualifyingPlaces"] / denominator, 6) if denominator else None,
    })
    popularity_profile = next((d for d in profile["dimensions"].values() if d.get("type") == "review_count_thresholds"), {})
    hashes = {
        "profile": input_hashes.get("profile"),
        "placesMatched": input_hashes.get("places_matched"),
        "publicSourcesMatched": input_hashes.get("public_sources_matched"),
        "kakaoRatings": input_hashes.get("kakao_ratings"),
        "googleRatings": input_hashes.get("google_ratings"),
    }
    return {
        "metadata": {
            "profileId": profile["profileId"],
            "profileVersion": profile["profileVersion"],
            "profileStatus": profile.get("status", "unspecified"),
            "profileSha256": input_hashes.get("profile"),
            "buildTimestamp": build_timestamp,
            "inputSha256": hashes,
            "inputRows": input_counts,
            "candidatePlaceCount": denominator,
            "selectedPlaceCount": sum(1 for item in results if item["selected"]),
            "reviewCountThresholds": popularity_profile.get("thresholds", {}),
            "platformReviewCountsUsed": bool(popularity_profile),
            "platformRatingAveragesUsed": False,
            "platformRatingsUsed": False,
            "missingDataPolicy": "unknown_not_penalized",
        },
        "coverage": coverage,
        "reviewCountCoverage": review_coverage,
        "places": results,
    }


def run(args: argparse.Namespace) -> Path | None:
    profile_path = args.profile.resolve()
    places_path = args.places_input.resolve()
    public_path = args.public_input.resolve()
    kakao_path = args.kakao_ratings.resolve()
    google_path = args.google_ratings.resolve()
    for required in (profile_path, places_path):
        if not required.is_file():
            raise FileNotFoundError(f"required input not found: {required}")
    if not public_path.exists():
        print(f"note: optional public input not found; treating it as unknown: {public_path}")

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    timestamp = normalize_timestamp(args.build_timestamp)
    matched_rows = read_csv(places_path)
    public_rows = read_csv(public_path)
    kakao_rows = read_csv(kakao_path)
    google_rows = read_csv(google_path)
    review_counts = assemble_canonical_review_counts(kakao_rows, google_rows, matched_rows, public_rows)
    hashes = {
        "profile": sha256_file(profile_path),
        "places_matched": sha256_file(places_path),
        "public_sources_matched": sha256_file(public_path) if public_path.is_file() else None,
        "kakao_ratings": sha256_file(kakao_path) if kakao_path.is_file() else None,
        "google_ratings": sha256_file(google_path) if google_path.is_file() else None,
    }
    payload = score_rows(matched_rows, public_rows, profile, timestamp, hashes, review_counts)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.dry_run:
        print(json.dumps({
            "dryRun": True,
            "profile": str(profile_path),
            "buildTimestamp": timestamp,
            "candidatePlaceCount": payload["metadata"]["candidatePlaceCount"],
            "selectedPlaceCount": payload["metadata"]["selectedPlaceCount"],
            "reviewCountCoverage": payload["reviewCountCoverage"],
            "coverage": payload["coverage"],
            "outputWouldBe": str(args.output.resolve()) if args.output else str(DEFAULT_OUTPUT_DIR / f"{build_stamp(timestamp)}.json"),
        }, ensure_ascii=False, indent=2))
        return None

    output = args.output.resolve() if args.output else DEFAULT_OUTPUT_DIR / f"{build_stamp(timestamp)}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
    except FileExistsError as exc:
        raise FileExistsError(f"refusing to overwrite existing score output: {output}") from exc
    print(f"wrote {payload['metadata']['candidatePlaceCount']} places ({payload['metadata']['selectedPlaceCount']} selected) -> {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE, help="JSON scoring profile")
    parser.add_argument("--places-input", type=Path, default=DEFAULT_PLACES, help="local Michelin/heritage match CSV")
    parser.add_argument("--public-input", type=Path, default=DEFAULT_PUBLIC, help="local public-source match CSV (optional)")
    parser.add_argument("--kakao-ratings", type=Path, default=DEFAULT_KAKAO_RATINGS, help="local Kakao review-count snapshot")
    parser.add_argument("--google-ratings", type=Path, default=DEFAULT_GOOGLE_RATINGS, help="local Google user-rating-count snapshot")
    parser.add_argument("--output", type=Path, help="new output JSON path; must not already exist")
    parser.add_argument("--build-timestamp", help="fixed ISO-8601 timestamp for reproducible builds (UTC assumed if no zone)")
    parser.add_argument("--dry-run", action="store_true", help="compute coverage without writing any output")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
