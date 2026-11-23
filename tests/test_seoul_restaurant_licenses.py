import csv
import gzip
import hashlib
import io
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_seoul_restaurant_licenses import (
    DATASET_ID,
    NORMALIZED_PATH,
    PROJECTED_SOURCE_FIELDS,
    PROVENANCE_FIELDS,
    SOURCE_URL,
    normalize_csv_bytes,
    normalize_csv_file,
)

RAW_SNAPSHOT = ROOT / "data/raw/seoul_restaurant_licenses/2026-11-23/seoul_restaurant_licenses_20261122.csv"
EXPECTED_RAW_SHA256 = "9f1119ab4af602f5920ef0e06b81c11327b29809e9cce8d1f12f9fdf0003b091"
EXPECTED_DATA_ROWS = 540_008


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_csv(rows, fields=PROJECTED_SOURCE_FIELDS, encoding="utf-8-sig"):
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode(encoding)


def sample_row(**overrides):
    row = {field: "" for field in PROJECTED_SOURCE_FIELDS}
    row.update({
        "개방자치단체코드": "6110000",
        "관리번호": "A001",
        "인허가일자": "20200102",
        "영업상태코드": "01",
        "영업상태명": "영업/정상",
        "상세영업상태코드": "01",
        "상세영업상태명": "정상",
        "지번주소": "서울특별시 중구 예시동 1",
        "도로명주소": "서울특별시 중구 예시로 1",
        "사업장명": "예시 식당",
        "업태구분명": "한식",
        "좌표정보(X)": "198000.1",
        "좌표정보(Y)": "451000.2",
        "위생업태명": "한식",
        "전통업소지정번호": "T-01",
        "전통업소주된음식": "비빔밥",
    })
    row.update(overrides)
    return row


class SeoulRestaurantLicensesTests(unittest.TestCase):
    def test_projection_preserves_status_dates_addresses_types_ids_and_provenance(self):
        raw = make_csv([
            sample_row(),
            sample_row(
                **{
                    "관리번호": "A002",
                    "영업상태코드": "03",
                    "영업상태명": "폐업",
                    "상세영업상태코드": "02",
                    "상세영업상태명": "폐업",
                    "폐업일자": "20240110",
                    "사업장명": "폐업 식당",
                    "업태구분명": "분식",
                }
            ),
        ])
        columns, rows, encoding, empty_records = normalize_csv_bytes(
            raw,
            source_snapshot="2026-11-22",
            collected_at="2026-11-23T15:00:00Z",
            source_modified_at="2026-11-22",
            data_go_modified_at="2025-08-08",
        )

        self.assertEqual(encoding, "utf-8-sig")
        self.assertEqual(columns, list(PROJECTED_SOURCE_FIELDS) + list(PROVENANCE_FIELDS))
        self.assertTrue(NORMALIZED_PATH.name.endswith(".csv.gz"))
        self.assertNotIn("전화번호", columns)
        self.assertNotIn("월세액", columns)
        self.assertNotIn("남성종사자수", columns)
        self.assertEqual(empty_records, 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["관리번호"], "A001")
        self.assertEqual(rows[0]["사업장명"], "예시 식당")
        self.assertEqual(rows[0]["인허가일자"], "20200102")
        self.assertEqual(rows[0]["영업상태명"], "영업/정상")
        self.assertEqual(rows[0]["도로명주소"], "서울특별시 중구 예시로 1")
        self.assertEqual(rows[0]["업태구분명"], "한식")
        self.assertEqual(rows[0]["위생업태명"], "한식")
        self.assertEqual(rows[0]["좌표정보(X)"], "198000.1")
        self.assertEqual(rows[0]["전통업소지정번호"], "T-01")
        self.assertEqual(rows[0]["전통업소주된음식"], "비빔밥")
        self.assertEqual(rows[1]["폐업일자"], "20240110")
        self.assertEqual(rows[0]["source"], "seoul_restaurant_licenses")
        self.assertEqual(rows[0]["source_id"], DATASET_ID)
        self.assertEqual(rows[0]["source_url"], SOURCE_URL)
        self.assertEqual(rows[0]["source_snapshot"], "2026-11-22")
        self.assertEqual(rows[0]["collected_at"], "2026-11-23T15:00:00Z")
        self.assertEqual(rows[0]["source_modified_at"], "2026-11-22")
        self.assertEqual(rows[0]["data_go_modified_at"], "2025-08-08")

    def test_streaming_output_is_gzip_and_empty_rows_only_are_skipped(self):
        empty = {field: "" for field in PROJECTED_SOURCE_FIELDS}
        raw = make_csv([sample_row(), empty, sample_row(**{"관리번호": "A003", "영업상태명": ""})], encoding="cp949")
        with tempfile.TemporaryDirectory() as tmp:
            raw_path = Path(tmp) / "source.csv"
            output_path = Path(tmp) / "projection.csv.gz"
            raw_path.write_bytes(raw)
            columns, row_count, empty_records, encoding = normalize_csv_file(
                raw_path,
                output_path,
                source_snapshot="2026-11-22",
                collected_at="2026-11-23T15:00:00Z",
                source_modified_at="2026-11-22",
                data_go_modified_at="2025-08-08",
            )
            self.assertEqual(output_path.read_bytes()[:2], bytes([31, 139]))
            with gzip.open(output_path, "rt", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                self.assertEqual(reader.fieldnames, columns)
        self.assertEqual(columns, list(PROJECTED_SOURCE_FIELDS) + list(PROVENANCE_FIELDS))
        self.assertEqual(row_count, 2)
        self.assertEqual(empty_records, 1)
        self.assertEqual(encoding, "cp949+surrogateescape")
        self.assertEqual([row["관리번호"] for row in rows], ["A001", "A003"])
        self.assertEqual(rows[1]["영업상태명"], "")
        self.assertEqual(rows[0]["source_id"], DATASET_ID)
        self.assertEqual(rows[0]["source_url"], SOURCE_URL)

    def test_invalid_cp949_bytes_are_explicitly_escaped(self):
        values = {field: "" for field in PROJECTED_SOURCE_FIELDS}
        values.update({"관리번호": "A009", "사업장명": "bad"})
        header = ",".join(PROJECTED_SOURCE_FIELDS).encode("cp949") + bytes([10])
        fields = []
        for field in PROJECTED_SOURCE_FIELDS:
            if field == "사업장명":
                fields.append(b"bad-" + bytes([130]) + b"-name")
            else:
                fields.append(values[field].encode("cp949"))
        raw = header + b",".join(fields) + bytes([10])
        _columns, rows, encoding, _empty = normalize_csv_bytes(
            raw,
            source_snapshot="2026-11-22",
            collected_at="2026-11-23T15:00:00Z",
            source_modified_at="2026-11-22",
            data_go_modified_at="2025-08-08",
        )
        self.assertEqual(encoding, "cp949+surrogateescape")
        self.assertEqual(rows[0]["사업장명"], "bad-" + chr(92) + "x82-name")

    @unittest.skipUnless(RAW_SNAPSHOT.is_file(), "local official raw snapshot is gitignored and not present")
    def test_actual_raw_snapshot_projects_all_records_and_remains_unchanged(self):
        before_size = RAW_SNAPSHOT.stat().st_size
        before_hash = sha256_file(RAW_SNAPSHOT)
        self.assertEqual(before_size, 224_460_984)
        self.assertEqual(before_hash, EXPECTED_RAW_SHA256)

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "actual_projection.csv.gz"
            columns, row_count, empty_records, encoding = normalize_csv_file(
                RAW_SNAPSHOT,
                output_path,
                source_snapshot="2026-11-22",
                collected_at="2026-11-23T15:06:24Z",
                source_modified_at="2026-11-22",
                data_go_modified_at="2025-08-08",
            )
            self.assertEqual(output_path.read_bytes()[:2], bytes([31, 139]))
            statuses = Counter()
            output_rows = 0
            with gzip.open(output_path, "rt", encoding="utf-8", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(reader.fieldnames, columns)
                for row in reader:
                    output_rows += 1
                    statuses[row["영업상태명"]] += 1
                    self.assertTrue(row["관리번호"])
                    self.assertEqual(row["source_id"], DATASET_ID)
                    self.assertEqual(row["source_url"], SOURCE_URL)
                    self.assertEqual(row["source_snapshot"], "2026-11-22")

        self.assertEqual(columns, list(PROJECTED_SOURCE_FIELDS) + list(PROVENANCE_FIELDS))
        self.assertEqual(row_count, EXPECTED_DATA_ROWS)
        self.assertEqual(output_rows, EXPECTED_DATA_ROWS)
        self.assertEqual(empty_records, 0)
        self.assertEqual(statuses, Counter({"폐업": 419_931, "영업/정상": 120_077}))
        self.assertEqual(RAW_SNAPSHOT.stat().st_size, before_size)
        self.assertEqual(sha256_file(RAW_SNAPSHOT), before_hash)


if __name__ == "__main__":
    unittest.main()
