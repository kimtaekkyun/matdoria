#!/usr/bin/env python3
"""Offline exact-name/address match and status rollup for Seoul licenses.

This is an enrichment join only. It never calls Kakao, Google, or any network
service and never edits the canonical places list. The normalized gzip input
remains the complete source of all license records. The derived matched output
contains only high-confidence exact joins; unmatched records remain in that
source and their no-candidate count is reported. The review output contains
candidate mismatches and ambiguities, not the full unmatched population.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data/processed/seoul_restaurant_licenses.csv.gz"
PLACES = ROOT / "web/public/data/places.json"
OUTPUT = ROOT / "data/processed/seoul_restaurant_licenses_matched.csv"
REVIEW_OUTPUT = ROOT / "data/processed/seoul_restaurant_licenses_match_review.csv"

STATUS_OPEN = "영업/정상"
STATUS_CLOSED = "폐업"

# This order follows the original source projection. Names and values stay in
# the original Korean source fields; only matching keys are normalized.
MATCH_FIELDS = (
    "match_status",
    "match_reason",
    "canonical_place_id",
    "canonical_place_name",
    "canonical_place_address",
    "normalized_business_name",
    "normalized_road_address",
    "match_evidence",
    "license_record_count",
    "license_record_ids",
    "license_status_dates",
    "resolved_current_status",
    "resolution_event_date",
    "status_resolution",
    "status_resolution_evidence",
)
REVIEW_FIELDS = (
    "review_reason",
    "normalized_business_name",
    "normalized_road_address",
    "name_candidate_count",
    "name_candidates",
    "address_candidate_count",
    "address_candidates",
    "exact_pair_candidate_count",
    "canonical_place_id",
    "status_resolution",
    "resolution_event_date",
    "status_resolution_evidence",
)


def normalize_business_name(value: str | None) -> str:
    """Normalize only Unicode, case, whitespace, and punctuation in a name."""
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def normalize_road_address(value: str | None) -> str:
    """Normalize a Seoul road address without fuzzy or numeric relaxation."""
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    value = re.sub(r"^(?:서울특별시|서울시|서울)\s*", "", value)
    # Korean public road-address exports append legal-dong/building details in
    # parentheses. They are supplemental to the road name/number used here.
    value = re.sub(r"\([^)]*\)", " ", value)
    # Strip trailing floor/unit annotations only. Do not remove building or
    # street numbers, which are required for an exact address match.
    value = re.sub(
        r"(?:,?\s*(?:지하\s*)?\d+\s*(?:층|호)|,?\s*(?:b\s*\d+|\d+\s*f))+\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return re.sub(r"[^0-9a-z가-힣]", "", value)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_places(path: Path = PLACES) -> list[dict[str, Any]]:
    places = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(places, list):
        raise ValueError(f"canonical places must be a JSON list: {path}")
    for place in places:
        if not place.get("id") or not place.get("name") or not place.get("address"):
            raise ValueError("canonical place is missing id, name, or address")
    ids = [str(place["id"]) for place in places]
    if len(ids) != len(set(ids)):
        raise ValueError("canonical place IDs are not unique")
    return places


def build_indexes(places: Iterable[dict[str, Any]]) -> tuple[dict, dict, dict]:
    by_name: dict[str, list[dict]] = defaultdict(list)
    by_address: dict[str, list[dict]] = defaultdict(list)
    by_pair: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for place in places:
        name = normalize_business_name(place.get("name"))
        address = normalize_road_address(place.get("address"))
        if not name or not address:
            continue
        by_name[name].append(place)
        by_address[address].append(place)
        by_pair[(name, address)].append(place)
    return by_name, by_address, by_pair


def _place_candidate(place: dict[str, Any]) -> dict[str, str]:
    return {
        "id": str(place["id"]),
        "name": place["name"],
        "address": place["address"],
    }


def classify_record(
    record: dict[str, str],
    by_name: dict[str, list[dict]],
    by_address: dict[str, list[dict]],
    by_pair: dict[tuple[str, str], list[dict]],
) -> dict[str, Any]:
    name = normalize_business_name(record.get("사업장명"))
    address = normalize_road_address(record.get("도로명주소"))
    name_places = by_name.get(name, []) if name else []
    address_places = by_address.get(address, []) if address else []
    pair_places = by_pair.get((name, address), []) if name and address else []
    if len(pair_places) == 1:
        status, reason = "accepted", "exact_normalized_name_and_road_address"
        place = pair_places[0]
    elif len(pair_places) > 1:
        status, reason, place = "needs_review", "ambiguous_exact_pair", None
    elif name_places and address_places:
        status, reason, place = "needs_review", "name_and_address_candidates_differ", None
    elif name_places:
        status, reason, place = "needs_review", "name_only", None
    elif address_places:
        status, reason, place = "needs_review", "address_only", None
    else:
        status, reason, place = "no_candidate", "no_exact_name_or_address_candidate", None
    return {
        "name": name,
        "address": address,
        "name_places": name_places,
        "address_places": address_places,
        "pair_places": pair_places,
        "status": status,
        "reason": reason,
        "place": place,
    }


def _source_date(value: str | None) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 8:
        return ""
    compact = digits[:8]
    try:
        return date(int(compact[:4]), int(compact[4:6]), int(compact[6:8])).isoformat()
    except ValueError:
        return ""


def _management_year(value: str | None) -> int | None:
    # Data.go/localdata management IDs encode the initial permit year in the
    # third hyphen-separated segment, e.g. 3200000-101-2015-00443.
    parts = (value or "").split("-")
    if len(parts) < 4 or not re.fullmatch(r"20\d{2}|19\d{2}", parts[2]):
        return None
    return int(parts[2])


def _event_for_record(record: dict[str, str]) -> dict[str, str]:
    status = (record.get("영업상태명") or "").strip()
    if status == STATUS_CLOSED:
        event_date = _source_date(record.get("폐업일자"))
    elif status == STATUS_OPEN:
        event_date = _source_date(record.get("인허가일자"))
    else:
        event_date = ""
    return {
        "record_id": record.get("관리번호", ""),
        "status": status,
        "permit_date": _source_date(record.get("인허가일자")),
        "closure_date": _source_date(record.get("폐업일자")),
        "event_date": event_date,
    }


def resolve_place_status(records: list[dict[str, str]]) -> dict[str, str]:
    """Resolve one canonical place from its license records conservatively."""
    events = [_event_for_record(record) for record in records]
    dated = [event for event in events if event["event_date"]]
    if not dated:
        return {
            "resolved_current_status": "ambiguous",
            "resolution_event_date": "",
            "status_resolution": "ambiguous_no_valid_event_date",
            "status_resolution_evidence": "No valid permit/closure event date was available.",
        }

    latest_date = max(event["event_date"] for event in dated)
    latest = [event for event in dated if event["event_date"] == latest_date]
    latest_statuses = {event["status"] for event in latest}
    if len(latest_statuses) == 1:
        status = next(iter(latest_statuses))
        return {
            "resolved_current_status": status,
            "resolution_event_date": latest_date,
            "status_resolution": "latest_event_date",
            "status_resolution_evidence": f"Latest event date {latest_date} has one status: {status}.",
        }

    active_records = [
        record for record, event in zip(records, events)
        if event in latest and event["status"] == STATUS_OPEN
    ]
    closed_records = [
        record for record, event in zip(records, events)
        if event in latest and event["status"] == STATUS_CLOSED
    ]
    active = active_records[0] if len(active_records) == 1 else None
    active_year = _management_year(active.get("관리번호")) if active else None
    active_permit = _source_date(active.get("인허가일자")) if active else ""
    closed_years = [_management_year(record.get("관리번호")) for record in closed_records]
    closed_permits = [_source_date(record.get("인허가일자")) for record in closed_records]
    same_day_relicense = bool(
        active
        and closed_records
        and active_permit == latest_date
        and active_year is not None
        and active_year == int(latest_date[:4])
        and all(year is not None and active_year > year for year in closed_years)
        and all(permit and permit < latest_date for permit in closed_permits)
    )
    if same_day_relicense:
        closed_ids = ", ".join(record.get("관리번호", "") for record in closed_records)
        return {
            "resolved_current_status": STATUS_OPEN,
            "resolution_event_date": latest_date,
            "status_resolution": "same_day_relicense_active_record_wins",
            "status_resolution_evidence": (
                f"Same-day closure/relicense on {latest_date}; active record "
                f"{active.get('관리번호', '')} has a newer permit-year ID than closed record(s) {closed_ids}."
            ),
        }

    statuses = ", ".join(sorted(latest_statuses))
    ids = ", ".join(event["record_id"] for event in latest)
    return {
        "resolved_current_status": "ambiguous",
        "resolution_event_date": latest_date,
        "status_resolution": "ambiguous_latest_event_tie",
        "status_resolution_evidence": (
            f"Conflicting statuses ({statuses}) tie at {latest_date}; latest record(s): {ids}."
        ),
    }


def _group_license_evidence(records: list[dict[str, str]]) -> tuple[str, str, str]:
    events = [_event_for_record(record) for record in records]
    record_ids = [record.get("관리번호", "") for record in records]
    return str(len(records)), _json(record_ids), _json(events)


def _matched_row(
    record: dict[str, str],
    place: dict[str, Any],
    group_records: list[dict[str, str]],
    resolution: dict[str, str],
) -> dict[str, Any]:
    count, record_ids, status_dates = _group_license_evidence(group_records)
    return {
        **record,
        "match_status": "accepted",
        "match_reason": "exact_normalized_name_and_road_address",
        "canonical_place_id": str(place["id"]),
        "canonical_place_name": place["name"],
        "canonical_place_address": place["address"],
        "normalized_business_name": normalize_business_name(record.get("사업장명")),
        "normalized_road_address": normalize_road_address(record.get("도로명주소")),
        "match_evidence": "exact normalized business name and road address",
        "license_record_count": count,
        "license_record_ids": record_ids,
        "license_status_dates": status_dates,
        **resolution,
    }


def _review_row(
    record: dict[str, str],
    classified: dict[str, Any],
    *,
    reason: str | None = None,
    resolution: dict[str, str] | None = None,
    canonical_id: str = "",
) -> dict[str, Any]:
    return {
        **record,
        "review_reason": reason or classified["reason"],
        "normalized_business_name": classified["name"],
        "normalized_road_address": classified["address"],
        "name_candidate_count": len(classified["name_places"]),
        "name_candidates": _json([_place_candidate(p) for p in classified["name_places"]]),
        "address_candidate_count": len(classified["address_places"]),
        "address_candidates": _json([_place_candidate(p) for p in classified["address_places"]]),
        "exact_pair_candidate_count": len(classified["pair_places"]),
        "canonical_place_id": canonical_id,
        "status_resolution": (resolution or {}).get("status_resolution", ""),
        "resolution_event_date": (resolution or {}).get("resolution_event_date", ""),
        "status_resolution_evidence": (resolution or {}).get("status_resolution_evidence", ""),
    }


def _write_dict_rows(path: Path, columns: list[str], rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def process_files(
    input_path: Path = INPUT,
    places_path: Path = PLACES,
    matched_path: Path = OUTPUT,
    review_path: Path = REVIEW_OUTPUT,
) -> dict[str, int]:
    """Create an accepted-only match CSV and a bounded review CSV."""
    for path in (matched_path, review_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite output: {path}")
    matched_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    for path in (matched_path.with_name(matched_path.name + ".tmp"), review_path.with_name(review_path.name + ".tmp")):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite temporary output: {path}")

    places = load_places(places_path)
    by_name, by_address, by_pair = build_indexes(places)
    input_columns: list[str] = []
    matched_by_place: dict[str, list[dict[str, str]]] = defaultdict(list)
    matched_places: dict[str, dict[str, Any]] = {}
    review_rows: list[dict[str, Any]] = []
    input_rows = review_name_only = review_address_only = review_both_mismatch = 0
    exact_match_records = ambiguous_pair_records = no_candidate_records = 0

    with gzip.open(input_path, "rt", encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        input_columns = reader.fieldnames or []
        if not input_columns or "사업장명" not in input_columns or "도로명주소" not in input_columns:
            raise ValueError("license input is missing 사업장명 or 도로명주소")
        for record in reader:
            input_rows += 1
            classified = classify_record(record, by_name, by_address, by_pair)
            place = classified["place"]
            if classified["status"] == "accepted" and place:
                place_id = str(place["id"])
                matched_by_place[place_id].append(record)
                matched_places[place_id] = place
                exact_match_records += 1
            elif classified["status"] == "no_candidate":
                no_candidate_records += 1
            elif classified["reason"] == "ambiguous_exact_pair":
                ambiguous_pair_records += 1
                review_rows.append(_review_row(record, classified))
            else:
                name_hit = bool(classified["name_places"])
                address_hit = bool(classified["address_places"])
                if name_hit and address_hit:
                    review_both_mismatch += 1
                elif name_hit:
                    review_name_only += 1
                else:
                    review_address_only += 1
                review_rows.append(_review_row(record, classified))

    resolutions: dict[str, dict[str, str]] = {}
    accepted_places = current_open_places = closed_places = ambiguous_status_places = 0
    relicense_status_resolutions = 0
    for place_id, records in matched_by_place.items():
        resolution = resolve_place_status(records)
        resolutions[place_id] = resolution
        accepted_places += 1
        status = resolution["resolved_current_status"]
        if status == STATUS_OPEN:
            current_open_places += 1
        elif status == STATUS_CLOSED:
            closed_places += 1
        else:
            ambiguous_status_places += 1
            classified = classify_record(records[0], by_name, by_address, by_pair)
            for record in records:
                review_rows.append(_review_row(
                    record, classified, reason="ambiguous_status_resolution",
                    resolution=resolution, canonical_id=place_id,
                ))
        if resolution["status_resolution"] == "same_day_relicense_active_record_wins":
            relicense_status_resolutions += 1

    matched_columns = [*input_columns, *MATCH_FIELDS]
    review_columns = [*input_columns, *REVIEW_FIELDS]
    matched_tmp = matched_path.with_name(matched_path.name + ".tmp")
    review_tmp = review_path.with_name(review_path.name + ".tmp")
    try:
        with matched_tmp.open("x", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=matched_columns, lineterminator="\n")
            writer.writeheader()
            output_count = 0
            for place_id, records in matched_by_place.items():
                place = matched_places[place_id]
                resolution = resolutions[place_id]
                for record in records:
                    writer.writerow(_matched_row(record, place, records, resolution))
                    output_count += 1
            if output_count != exact_match_records:
                raise AssertionError("accepted output row count does not equal exact-match record count")

        review_count = _write_dict_rows(review_tmp, review_columns, review_rows)
        matched_tmp.replace(matched_path)
        review_tmp.replace(review_path)
    except Exception:
        matched_tmp.unlink(missing_ok=True)
        review_tmp.unlink(missing_ok=True)
        raise

    multi_record_places = sum(len(records) > 1 for records in matched_by_place.values())
    summary = {
        "source_rows": input_rows,
        "accepted_source_records": exact_match_records,
        "accepted_unique_places": accepted_places,
        "multi_record_places": multi_record_places,
        "extra_license_records_over_places": exact_match_records - accepted_places,
        "max_license_records_per_place": max((len(records) for records in matched_by_place.values()), default=0),
        "current_open_places": current_open_places,
        "closed_places": closed_places,
        "ambiguous_status_places": ambiguous_status_places,
        "ambiguous_exact_pair_records": ambiguous_pair_records,
        "same_day_relicense_active_wins": relicense_status_resolutions,
        "review_rows": review_count,
        "review_name_only": review_name_only,
        "review_address_only": review_address_only,
        "review_both_name_and_address_candidates_mismatch": review_both_mismatch,
        "no_candidate_records_not_in_review": no_candidate_records,
    }
    if input_rows != exact_match_records + ambiguous_pair_records + review_name_only + review_address_only + review_both_mismatch + no_candidate_records:
        raise AssertionError("record counts do not reconcile")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--places", type=Path, default=PLACES)
    parser.add_argument("--matched-output", type=Path, default=OUTPUT)
    parser.add_argument("--review-output", type=Path, default=REVIEW_OUTPUT)
    args = parser.parse_args()
    summary = process_files(args.input, args.places, args.matched_output, args.review_output)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    print(f"matched={args.matched_output} review={args.review_output}")


if __name__ == "__main__":
    main()
