import csv
import io
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_hundred_store_data import SOURCE_URL, normalize_csv_bytes


class HundredStoreNormalizationTests(unittest.TestCase):
    def test_cp949_csv_preserves_source_fields_and_ids_and_appends_provenance(self):
        source = (
            "연번,업체명,업체주소,연락처,추가정보\r\n"
            "001,가게 A,서울 중구 세종대로 1,02-123-4567,원본 값\r\n"
            "002,가게 B,부산 중구 중앙대로 2,,\r\n"
        ).encode("cp949")
        columns, rows, encoding = normalize_csv_bytes(
            source,
            source_snapshot="2026-08-20",
            collected_at="2026-11-20T12:00:00Z",
            source_modified_at="2026-08-30",
        )
        self.assertEqual(encoding, "cp949")
        self.assertEqual(columns[:5], ["연번", "업체명", "업체주소", "연락처", "추가정보"])
        self.assertEqual(columns[5:], ["source", "source_url", "source_snapshot", "collected_at", "source_modified_at"])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["연번"], "001")
        self.assertEqual(rows[0]["업체명"], "가게 A")
        self.assertEqual(rows[0]["추가정보"], "원본 값")
        self.assertEqual(rows[1]["연락처"], "")
        self.assertEqual(rows[0]["source"], "hundred_store")
        self.assertEqual(rows[0]["source_url"], SOURCE_URL)
        self.assertEqual(rows[0]["source_snapshot"], "2026-08-20")
        self.assertEqual(rows[0]["collected_at"], "2026-11-20T12:00:00Z")
        self.assertEqual(rows[0]["source_modified_at"], "2026-08-30")

    def test_utf8_bom_is_supported_and_source_metadata_collision_is_rejected(self):
        good = "연번,업체명\n1,가게\n".encode("utf-8-sig")
        _, rows, encoding = normalize_csv_bytes(
            good, source_snapshot="2026-08-20", collected_at="2026-11-20T00:00:00Z", source_modified_at="2026-08-30",
        )
        self.assertEqual(encoding, "utf-8-sig")
        self.assertEqual(rows[0]["업체명"], "가게")
        bad = "source,업체명\nx,가게\n".encode("utf-8")
        with self.assertRaisesRegex(ValueError, "collide"):
            normalize_csv_bytes(
                bad, source_snapshot="2026-08-20", collected_at="2026-11-20T00:00:00Z", source_modified_at="2026-08-30",
            )


if __name__ == "__main__":
    unittest.main()
