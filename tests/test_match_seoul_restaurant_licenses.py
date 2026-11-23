import csv
import gzip
import hashlib
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from match_seoul_restaurant_licenses import (
    INPUT,
    PLACES,
    STATUS_CLOSED,
    STATUS_OPEN,
    build_indexes,
    classify_record,
    normalize_business_name,
    normalize_road_address,
    process_files,
    resolve_place_status,
)

EXPECTED_ROWS = 540_008
EXPECTED_RAW_MATCH_RECORDS = 702
EXPECTED_MATCHED_PLACES = 681


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def license_record(**updates):
    row = {
        "개방자치단체코드": "6110000",
        "관리번호": "3200000-101-2013-00456",
        "사업장명": "예시 식당",
        "인허가일자": "2013-09-23",
        "영업상태코드": "03",
        "영업상태명": STATUS_CLOSED,
        "상세영업상태코드": "02",
        "상세영업상태명": "폐업",
        "폐업일자": "2015-11-26",
        "도로명주소": "서울특별시 광진구 아차산로 225 (화양동, 1층)",
        "지번주소": "서울특별시 광진구 화양동 1",
        "업태구분명": "한식",
        "위생업태명": "한식",
        "좌표정보(X)": "",
        "좌표정보(Y)": "",
        "전통업소지정번호": "",
        "전통업소주된음식": "",
        "source_snapshot": "2026-11-22",
        "collected_at": "2026-11-23T15:06:24Z",
    }
    row.update(updates)
    return row


class SeoulLicenseNormalizationTests(unittest.TestCase):
    def test_normalization_is_exact_after_only_documented_address_cleanup(self):
        self.assertEqual(normalize_business_name(" Cafe A-B (점)") , "cafeab점")
        self.assertEqual(
            normalize_road_address("서울특별시 광진구 아차산로 225, 1층 (화양동)"),
            "광진구아차산로225",
        )
        self.assertNotEqual(normalize_business_name("한마음 식당"), normalize_business_name("한마음식당 별관"))

    def test_unique_exact_pair_only_is_accepted(self):
        places = [
            {"id": "1", "name": "예시 식당", "address": "서울 광진구 아차산로 225"},
            {"id": "2", "name": "다른 식당", "address": "서울 광진구 아차산로 226"},
        ]
        indexes = build_indexes(places)
        exact = classify_record(license_record(), *indexes)
        self.assertEqual(exact["status"], "accepted")
        self.assertEqual(exact["place"]["id"], "1")

        name_only = classify_record(license_record(도로명주소="서울 광진구 다른길 1"), *indexes)
        self.assertEqual(name_only["reason"], "name_only")
        self.assertIsNone(name_only["place"])

        address_only = classify_record(license_record(사업장명="상호 불일치"), *indexes)
        self.assertEqual(address_only["reason"], "address_only")
        self.assertIsNone(address_only["place"])

        ambiguous = classify_record(license_record(), *build_indexes([
            {"id": "1", "name": "예시 식당", "address": "서울 광진구 아차산로 225"},
            {"id": "3", "name": "예시식당", "address": "서울 광진구 아차산로225"},
        ]))
        self.assertEqual(ambiguous["reason"], "ambiguous_exact_pair")
        self.assertEqual(len(ambiguous["pair_places"]), 2)
        self.assertIsNone(ambiguous["place"])


class LicenseStatusResolutionTests(unittest.TestCase):
    def test_latest_event_date_resolves_current_status(self):
        old_closed = license_record()
        newer_open = license_record(
            관리번호="3200000-101-2018-00443",
            인허가일자="2018-11-26",
            영업상태명=STATUS_OPEN,
            영업상태코드="01",
            폐업일자="",
        )
        resolution = resolve_place_status([old_closed, newer_open])
        self.assertEqual(resolution["resolved_current_status"], STATUS_OPEN)
        self.assertEqual(resolution["resolution_event_date"], "2018-11-26")
        self.assertEqual(resolution["status_resolution"], "latest_event_date")

    def test_same_day_closure_and_newer_relicense_resolves_open(self):
        closed = license_record()
        active = license_record(
            관리번호="3200000-101-2015-00443",
            인허가일자="2015-11-26",
            영업상태명=STATUS_OPEN,
            영업상태코드="01",
            폐업일자="",
        )
        resolution = resolve_place_status([closed, active])
        self.assertEqual(resolution["resolved_current_status"], STATUS_OPEN)
        self.assertEqual(resolution["resolution_event_date"], "2015-11-26")
        self.assertEqual(resolution["status_resolution"], "same_day_relicense_active_record_wins")

    def test_unproven_conflicting_same_day_tie_is_ambiguous(self):
        closed = license_record(관리번호="3200000-101-2015-00456", 인허가일자="2015-11-26")
        active = license_record(
            관리번호="3200000-101-2015-00443",
            인허가일자="2015-11-26",
            영업상태명=STATUS_OPEN,
            영업상태코드="01",
            폐업일자="",
        )
        resolution = resolve_place_status([closed, active])
        self.assertEqual(resolution["resolved_current_status"], "ambiguous")
        self.assertEqual(resolution["status_resolution"], "ambiguous_latest_event_tie")


@unittest.skipUnless(INPUT.is_file() and PLACES.is_file(), "local official input/canonical list is unavailable")
class SeoulLicenseIntegrationTests(unittest.TestCase):
    def test_full_join_counts_review_bound_and_record_preservation(self):
        input_hash = hash_file(INPUT)
        places_hash = hash_file(PLACES)
        with tempfile.TemporaryDirectory() as tmp:
            matched_path = Path(tmp) / "matched.csv"
            review_path = Path(tmp) / "review.csv"
            summary = process_files(INPUT, PLACES, matched_path, review_path)

            self.assertEqual(summary["source_rows"], EXPECTED_ROWS)
            self.assertEqual(summary["accepted_source_records"], EXPECTED_RAW_MATCH_RECORDS)
            self.assertEqual(summary["accepted_unique_places"], EXPECTED_MATCHED_PLACES)
            self.assertEqual(summary["multi_record_places"], 19)
            self.assertEqual(summary["extra_license_records_over_places"], 21)
            self.assertEqual(summary["max_license_records_per_place"], 3)
            self.assertEqual(summary["current_open_places"], 663)
            self.assertEqual(summary["closed_places"], 18)
            self.assertEqual(summary["ambiguous_status_places"], 0)
            self.assertEqual(summary["ambiguous_exact_pair_records"], 0)
            self.assertEqual(summary["same_day_relicense_active_wins"], 7)
            self.assertEqual(summary["review_rows"], 16_722)
            self.assertLess(summary["review_rows"], EXPECTED_ROWS)

            output_rows = accepted_rows = 0
            accepted_by_place = Counter()
            with matched_path.open(encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream):
                    output_rows += 1
                    if row["match_status"] == "accepted":
                        accepted_rows += 1
                        accepted_by_place[row["canonical_place_id"]] += 1
                        self.assertTrue(row["canonical_place_id"])
                        self.assertIn(row["resolved_current_status"], {STATUS_OPEN, STATUS_CLOSED})
                        self.assertGreaterEqual(int(row["license_record_count"]), 1)
                        self.assertIn(row["관리번호"], json.loads(row["license_record_ids"]))
            self.assertEqual(output_rows, EXPECTED_RAW_MATCH_RECORDS)
            self.assertEqual(accepted_rows, EXPECTED_RAW_MATCH_RECORDS)
            self.assertEqual(summary["no_candidate_records_not_in_review"], EXPECTED_ROWS - EXPECTED_RAW_MATCH_RECORDS - 16_722)
            self.assertEqual(len(accepted_by_place), EXPECTED_MATCHED_PLACES)
            self.assertEqual(sum(accepted_by_place.values()), EXPECTED_RAW_MATCH_RECORDS)

            with review_path.open(encoding="utf-8", newline="") as stream:
                review_rows = list(csv.DictReader(stream))
            self.assertEqual(len(review_rows), 16_722)
            self.assertNotIn("no_exact_name_or_address_candidate", {row["review_reason"] for row in review_rows})

        self.assertEqual(hash_file(INPUT), input_hash)
        self.assertEqual(hash_file(PLACES), places_hash)


if __name__ == "__main__":
    unittest.main()
