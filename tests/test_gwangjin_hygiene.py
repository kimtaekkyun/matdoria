import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_gwangjin_hygiene import DATASET_ID, PROVENANCE_FIELDS, SOURCE_URL, normalize_csv_bytes


class GwangjinHygieneTests(unittest.TestCase):
    def test_normalization_preserves_source_fields_and_appends_provenance(self):
        source_fields = [
            "연번", "지정기관", "지정일자", "위생등급", "업소명(상호)",
            "영업장소재지", "업종", "데이터기준일자",
        ]
        raw = (
            "연번,지정기관,지정일자,위생등급,업소명(상호),영업장소재지,업종,데이터기준일자\n"
            "001,광진구,2024-01-02,매우우수,예시 식당,서울 광진구 주소,일반음식점,2025-12-31\n"
        ).encode("utf-8-sig")
        columns, rows, encoding = normalize_csv_bytes(
            raw,
            source_snapshot="2025-12-31",
            collected_at="2026-11-23T14:00:00Z",
            source_modified_at="2026-01-20",
        )

        self.assertEqual(encoding, "utf-8-sig")
        self.assertEqual(columns, source_fields + list(PROVENANCE_FIELDS))
        self.assertEqual(len(rows), 1)
        self.assertEqual([rows[0][field] for field in source_fields], [
            "001", "광진구", "2024-01-02", "매우우수", "예시 식당",
            "서울 광진구 주소", "일반음식점", "2025-12-31",
        ])
        self.assertEqual(rows[0]["source"], "gwangjin_hygiene")
        self.assertEqual(rows[0]["source_id"], DATASET_ID)
        self.assertEqual(rows[0]["source_url"], SOURCE_URL)
        self.assertEqual(rows[0]["source_snapshot"], "2025-12-31")
        self.assertEqual(rows[0]["collected_at"], "2026-11-23T14:00:00Z")
        self.assertEqual(rows[0]["source_modified_at"], "2026-01-20")

    def test_all_empty_placeholder_rows_are_not_normalized_as_establishments(self):
        raw = "id,위생등급,업종\n001,매우우수,일반음식점\n,,\n".encode("utf-8")
        _columns, rows, _encoding = normalize_csv_bytes(
            raw,
            source_snapshot="2025-12-31",
            collected_at="2026-11-23T14:00:00Z",
            source_modified_at="2026-01-20",
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "001")

    def test_empty_source_values_are_preserved_as_empty_strings(self):
        raw = "id,위생등급,업종\n001,,\n".encode("cp949")
        columns, rows, encoding = normalize_csv_bytes(
            raw,
            source_snapshot="2025-12-31",
            collected_at="2026-11-23T14:00:00Z",
            source_modified_at="2026-01-20",
        )
        self.assertEqual(encoding, "cp949")
        self.assertEqual(rows[0]["id"], "001")
        self.assertEqual(rows[0]["위생등급"], "")
        self.assertEqual(rows[0]["업종"], "")


if __name__ == "__main__":
    unittest.main()
