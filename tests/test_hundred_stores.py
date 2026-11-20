import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_hundred_stores import SOURCE_URL, normalize_csv_bytes


class HundredStoresTests(unittest.TestCase):
    def test_normalization_preserves_source_id_and_fields_and_adds_provenance(self):
        raw = "연번,업체명,업체주소,연락처\n007,가게,서울 중구 주소,\n".encode("cp949")
        columns, rows, encoding = normalize_csv_bytes(
            raw,
            source_snapshot="2026-08-20",
            collected_at="2026-11-20T12:35:51Z",
            source_modified_at="2026-08-30",
        )
        self.assertEqual(encoding, "cp949")
        self.assertEqual(columns[:4], ["연번", "업체명", "업체주소", "연락처"])
        self.assertEqual(rows[0]["연번"], "007")
        self.assertEqual(rows[0]["업체주소"], "서울 중구 주소")
        self.assertEqual(rows[0]["연락처"], "")
        self.assertEqual(rows[0]["source"], "hundred_store")
        self.assertEqual(rows[0]["source_url"], SOURCE_URL)
        self.assertEqual(rows[0]["source_snapshot"], "2026-08-20")
        self.assertEqual(rows[0]["collected_at"], "2026-11-20T12:35:51Z")
        self.assertEqual(rows[0]["source_modified_at"], "2026-08-30")


if __name__ == "__main__":
    unittest.main()
