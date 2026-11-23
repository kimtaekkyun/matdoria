#!/usr/bin/env python3
"""Fetch Seoul's restaurant permit data via its official CSV button.

The Data.go.kr record links to Seoul Open Data Plaza dataset OA-16094. This
collector follows that public link, loads the official Sheet CSV form, and
submits the same form action as its visible CSV download button. It makes one
CSV file request per online run, uses no API key or login, and never retries or
bypasses access controls. Existing output files are never overwritten.

Attribution: Data.go.kr lists this work as Public Nuri Type 1 (attribution).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "15071760"
SOURCE_URL = f"https://www.data.go.kr/data/{DATASET_ID}/fileData.do"
SEOUL_DATASET_ID = "OA-16094"
SEOUL_SOURCE_URL = f"https://data.seoul.go.kr/dataList/{SEOUL_DATASET_ID}/S/1/datasetView.do"
SEOUL_SHEET_URL = "https://data.seoul.go.kr/dataList/sheetView.do?" + urllib.parse.urlencode({
    "isLogin": "", "srvType": "S", "infId": SEOUL_DATASET_ID, "serviceKind": "1",
    "ssUserId": "", "infNm": "서울시 일반음식점 인허가 정보", "stcRow": "",
})
SEOUL_DOWNLOAD_URL = "https://datafile.seoul.go.kr/bigfile/iot/sheet/csv/download.do"
PORTAL = "https://www.data.go.kr"
RAW_ROOT = ROOT / "data/raw/seoul_restaurant_licenses"
NORMALIZED_PATH = ROOT / "data/processed/seoul_restaurant_licenses.csv.gz"
PROJECTED_SOURCE_FIELDS = (
    "개방자치단체코드", "관리번호", "인허가일자", "영업상태코드", "영업상태명",
    "상세영업상태코드", "상세영업상태명", "폐업일자", "지번주소", "도로명주소",
    "사업장명", "업태구분명", "좌표정보(X)", "좌표정보(Y)", "위생업태명",
    "전통업소지정번호", "전통업소주된음식",
)
OPTIONAL_PROJECTION_FIELDS = {"전통업소지정번호", "전통업소주된음식"}
PROVENANCE_FIELDS = (
    "source", "source_id", "source_url", "source_snapshot", "collected_at",
    "source_modified_at", "data_go_modified_at",
)


class AcquisitionError(RuntimeError):
    """The official source or download flow is unavailable or blocked."""


class FormParser(HTMLParser):
    """Read successful controls from a named HTML form (without a browser)."""

    def __init__(self, form_id: str):
        super().__init__(convert_charrefs=True)
        self.form_id = form_id
        self.in_form = False
        self.form_found = False
        self.values: list[tuple[str, str]] = []
        self.current_select: str | None = None
        self.current_option: tuple[str | None, bool, list[str]] | None = None
        self.select_value: tuple[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "form":
            self.in_form = a.get("id") == self.form_id
            self.form_found = self.form_found or self.in_form
            return
        if not self.in_form:
            return
        if tag == "input" and a.get("name"):
            kind = (a.get("type") or "text").lower()
            if kind not in {"submit", "button", "image", "reset", "file"}:
                self.values.append((a["name"], a.get("value") or ""))
        elif tag == "select" and a.get("name"):
            self.current_select = a["name"]
            self.select_value = None
        elif tag == "option" and self.current_select is not None:
            self.current_option = (a.get("value"), "selected" in a, [])

    def handle_data(self, data: str) -> None:
        if self.current_option is not None:
            self.current_option[2].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self.current_option is not None and self.current_select is not None:
            value, selected, chunks = self.current_option
            option_value = value if value is not None else "".join(chunks).strip()
            if selected or self.select_value is None:
                self.select_value = (self.current_select, option_value)
            if selected:
                self.current_option = None
                return
            self.current_option = None
        elif tag == "select" and self.current_select is not None:
            if self.select_value is not None:
                self.values.append(self.select_value)
            self.current_select = None
            self.select_value = None
        elif tag == "form" and self.in_form:
            self.in_form = False


def _open(opener: Any, request: urllib.request.Request, *, stage: str):
    try:
        response = opener.open(request, timeout=90)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 429):
            raise AcquisitionError(
                f"STOP: official source blocked {stage} (HTTP {error.code}); no bypass attempted"
            ) from error
        raise AcquisitionError(f"official source failed {stage} (HTTP {error.code})") from error
    except urllib.error.URLError as error:
        raise AcquisitionError(f"official source unavailable during {stage}: {error.reason}") from error
    if response.status != 200:
        response.close()
        raise AcquisitionError(
            f"STOP: official source blocked {stage} (HTTP {response.status}); no bypass attempted"
        )
    return response


def _project_columns(source_columns: list[str]) -> list[str]:
    """Select analysis fields in original source order; retain traditional fields when present."""
    missing = [
        field for field in PROJECTED_SOURCE_FIELDS
        if field not in source_columns and field not in OPTIONAL_PROJECTION_FIELDS
    ]
    if missing:
        raise ValueError(f"Source CSV is missing required projection fields: {missing}")
    wanted = set(PROJECTED_SOURCE_FIELDS)
    return [field for field in source_columns if field in wanted]


def _escape_surrogate_bytes(value: str) -> str:
    """Render undecodable source bytes visibly instead of losing them."""
    return "".join(
        f"\\x{ord(char) - 0xDC00:02x}" if 0xDC80 <= ord(char) <= 0xDCFF else char
        for char in value
    )


def _decode_csv(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    # The official response declares CP949, but some legacy records contain
    # isolated invalid bytes. Preserve their byte values as visible \\xNN text;
    # the untouched raw snapshot remains the authoritative source copy.
    text = raw.decode("cp949", errors="surrogateescape")
    return _escape_surrogate_bytes(text), "cp949+surrogateescape"


def normalize_csv_bytes(
    raw: bytes,
    *,
    source_snapshot: str,
    collected_at: str,
    source_modified_at: str,
    data_go_modified_at: str,
) -> tuple[list[str], list[dict[str, str]], str, int]:
    """Project non-empty source records to the analysis fields and append provenance."""
    text, encoding = _decode_csv(raw)
    reader = csv.reader(io.StringIO(text, newline=""))
    source_columns = next(reader, [])
    if not source_columns or any(not column for column in source_columns):
        raise ValueError("CSV has no valid header row")
    if len(set(source_columns)) != len(source_columns):
        raise ValueError(f"CSV has duplicate source columns: {source_columns}")
    collisions = sorted(set(source_columns).intersection(PROVENANCE_FIELDS))
    if collisions:
        raise ValueError(f"Source columns collide with provenance fields: {collisions}")

    projected_columns = _project_columns(source_columns)
    columns = [*projected_columns, *PROVENANCE_FIELDS]
    source_indexes = {column: index for index, column in enumerate(source_columns)}
    rows: list[dict[str, str]] = []
    empty_records = 0
    for line_number, values in enumerate(reader, start=2):
        if not values or not any(values):
            empty_records += 1
            continue
        if len(values) != len(source_columns):
            raise ValueError(
                f"CSV row {line_number} has {len(values)} values; expected {len(source_columns)}"
            )
        row = {column: values[source_indexes[column]] for column in projected_columns}
        row.update({
            "source": "seoul_restaurant_licenses",
            "source_id": DATASET_ID,
            "source_url": SOURCE_URL,
            "source_snapshot": source_snapshot,
            "collected_at": collected_at,
            "source_modified_at": source_modified_at,
            "data_go_modified_at": data_go_modified_at,
        })
        rows.append(row)
    return columns, rows, encoding, empty_records


def normalize_csv_file(
    raw_path: Path,
    output_path: Path,
    *,
    source_snapshot: str,
    collected_at: str,
    source_modified_at: str,
    data_go_modified_at: str,
) -> tuple[list[str], int, int, str]:
    """Stream a compact, deterministic gzip CSV projection without loading records in memory."""
    # The official Seoul export declares charset=cp949. Use surrogateescape
    # for malformed legacy bytes; the untouched raw snapshot remains exact.
    encoding, errors = "cp949", "surrogateescape"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    empty_records = row_count = 0
    with raw_path.open("r", encoding=encoding, errors=errors, newline="") as source, output_path.open(
        "x", encoding="utf-8", newline=""
    ) as target:
        reader = csv.reader(source)
        source_columns = next(reader, [])
        if not source_columns or any(not column for column in source_columns):
            raise ValueError("CSV has no valid header row")
        source_columns = [_escape_surrogate_bytes(column) for column in source_columns]
        if len(set(source_columns)) != len(source_columns):
            raise ValueError(f"CSV has duplicate source columns: {source_columns}")
        collisions = sorted(set(source_columns).intersection(PROVENANCE_FIELDS))
        if collisions:
            raise ValueError(f"Source columns collide with provenance fields: {collisions}")
        projected_columns = _project_columns(source_columns)
        columns = [*projected_columns, *PROVENANCE_FIELDS]
        source_indexes = {column: index for index, column in enumerate(source_columns)}
        with gzip.GzipFile(fileobj=target.buffer, mode="wb", filename="", mtime=0, compresslevel=6) as compressed:
            text_target = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
            writer = csv.DictWriter(text_target, fieldnames=columns, lineterminator=chr(10))
            writer.writeheader()
            for line_number, values in enumerate(reader, start=2):
                if not values or not any(values):
                    empty_records += 1
                    continue
                if len(values) != len(source_columns):
                    raise ValueError(
                        f"CSV row {line_number} has {len(values)} values; expected {len(source_columns)}"
                    )
                row = {
                    column: _escape_surrogate_bytes(values[source_indexes[column]])
                    for column in projected_columns
                }
                row.update({
                    "source": "seoul_restaurant_licenses",
                    "source_id": DATASET_ID,
                    "source_url": SOURCE_URL,
                    "source_snapshot": source_snapshot,
                    "collected_at": collected_at,
                    "source_modified_at": source_modified_at,
                    "data_go_modified_at": data_go_modified_at,
                })
                writer.writerow(row)
                row_count += 1
            text_target.flush()
            text_target.detach()
    return columns, row_count, empty_records, encoding + ("+surrogateescape" if errors == "surrogateescape" else "")


def _modified_date(page: str, *, label: str, pattern: str) -> str:
    match = re.search(pattern, page, re.S)
    if not match:
        raise AcquisitionError(f"STOP: could not verify {label} on the official metadata page")
    value = match.group(1).strip()
    parsed = re.search(r"(20\d{2})[./-](\d{2})[./-](\d{2})", value)
    if not parsed:
        raise AcquisitionError(f"STOP: unexpected {label} value: {value}")
    return f"{parsed.group(1)}-{parsed.group(2)}-{parsed.group(3)}"


def download_official_csv() -> tuple[bytes, dict[str, Any]]:
    """Follow Data.go.kr's source link and submit Seoul's visible CSV form."""
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    common_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Matdoria official public-data downloader/1.0)",
    }

    data_go_response = _open(
        opener, urllib.request.Request(SOURCE_URL, headers=common_headers), stage="Data.go.kr record"
    )
    data_go_page = data_go_response.read().decode("utf-8", "replace")
    data_go_response.close()
    required_data_go_evidence = (
        "서울특별시_일반음식점 인허가 정보",
        "공공저작물 : 출처표시 (제 1유형)",
        "본 데이터는 3일전 자료를 제공합니다",
        SEOUL_DATASET_ID,
    )
    if any(item not in data_go_page for item in required_data_go_evidence):
        raise AcquisitionError("STOP: Data.go.kr metadata/link/license evidence differs from expected")
    if 'href="http://data.seoul.go.kr/dataList/OA-16094/S/1/datasetView.do"' not in data_go_page:
        raise AcquisitionError("STOP: Data.go.kr no longer links to the expected official Seoul dataset")
    if not re.search(r"수정일\s*</[^>]+>\s*<[^>]+>\s*2025-08-08", data_go_page):
        # Allow date rendering through a Schema.org JSON block or the visible page text.
        if "2025-08-08" not in data_go_page:
            raise AcquisitionError("STOP: Data.go.kr modified date no longer matches the audited record")

    # Follow the link printed in the official Data.go.kr record and validate the
    # official Seoul Open Data Plaza record and its public CSV sheet button.
    seoul_response = _open(
        opener, urllib.request.Request(SEOUL_SOURCE_URL, headers={**common_headers, "Referer": SOURCE_URL}),
        stage="official Seoul Open Data Plaza record",
    )
    seoul_page = seoul_response.read().decode("utf-8", "replace")
    seoul_response.close()
    if (
        SEOUL_DATASET_ID not in seoul_page
        or "서울시 일반음식점 인허가 정보" not in seoul_page
        or "이용허락범위 제한 없음" not in seoul_page
        or "Sheet는 최대" not in seoul_page and "sheet는 최대" not in seoul_page
    ):
        raise AcquisitionError("STOP: linked Seoul Open Data Plaza record or reuse evidence differs")
    source_modified_at = _modified_date(
        seoul_page,
        label="Seoul source refresh date",
        pattern=r"데이터 갱신일\s*</th>\s*<td><span[^>]*>([^<]+)</span>",
    )
    data_go_modified_at = "2025-08-08"

    sheet_headers = {**common_headers, "Referer": SEOUL_SOURCE_URL}
    sheet_response = _open(
        opener, urllib.request.Request(SEOUL_SHEET_URL, headers=sheet_headers),
        stage="official Seoul Sheet CSV page",
    )
    sheet_page = sheet_response.read().decode("utf-8", "replace")
    sheet_response.close()
    if (
        'id="frmSheet"' not in sheet_page
        or "serviceDownload('csv')" not in sheet_page
        or "/bigfile/iot/sheet/" not in sheet_page
        or 'id="ssUserId" value="SAMPLE_VIEW"' not in sheet_page
    ):
        raise AcquisitionError("STOP: official page no longer exposes the expected guest CSV download button")

    form = FormParser("frmSheet")
    form.feed(sheet_page)
    if not form.form_found:
        raise AcquisitionError("STOP: could not read the official CSV download form")
    # The portal's page button sends these form fields to its official CSV
    # download action. Keep the unfiltered default form values.
    values: dict[str, str] = {}
    for key, value in form.values:
        values[key] = value
    if values.get("infId") != SEOUL_DATASET_ID or values.get("ssUserId") != "SAMPLE_VIEW":
        raise AcquisitionError("STOP: official CSV form is not the public sample-view form")
    values["gridTotalCnt"] = values.get("gridTotalCnt", "")
    payload = urllib.parse.urlencode(values).encode("utf-8")
    request = urllib.request.Request(
        SEOUL_DOWNLOAD_URL,
        data=payload,
        headers={
            **common_headers,
            "Referer": SEOUL_SHEET_URL,
            "Origin": "https://data.seoul.go.kr",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    response = _open(opener, request, stage="official Seoul CSV button download")
    content_type = (response.headers.get("Content-Type") or "").lower()
    disposition = response.headers.get("Content-Disposition") or ""
    raw = response.read()
    final_url = response.geturl()
    response.close()
    if "text/html" in content_type or not raw or "attachment" not in disposition.lower():
        raise AcquisitionError(
            "STOP: official CSV button did not return an attachment (possible auth/challenge); no alternate route attempted"
        )
    return raw, {
        "content_type": content_type,
        "content_disposition": disposition,
        "final_url": final_url,
        "source_snapshot": source_modified_at,
        "source_modified_at": source_modified_at,
        "data_go_modified_at": data_go_modified_at,
        "license": "공공저작물 제1유형 (출처표시)",
        "download_flow": "Data.go.kr source link -> Seoul Open Data Plaza Sheet -> visible CSV button",
        "login": "not required; form ssUserId=SAMPLE_VIEW",
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(
    collection_date: str,
    collected_at: str | None = None,
    *,
    from_raw: Path | None = None,
    source_snapshot: str = "",
    source_modified_at: str = "",
    data_go_modified_at: str = "2025-08-08",
    normalized_output: Path = NORMALIZED_PATH,
) -> tuple[Path, Path, int, list[str], int, str]:
    day = date.fromisoformat(collection_date).isoformat()
    raw_dir = RAW_ROOT / day
    normalized_output = normalized_output.resolve()
    if normalized_output.suffix != ".gz":
        raise ValueError("normalized output must use a .gz suffix")
    if normalized_output.exists():
        raise FileExistsError(f"refusing to overwrite normalized output: {normalized_output}")

    portal: dict[str, Any]
    if from_raw:
        raw_path = from_raw.resolve()
        if not source_snapshot or not source_modified_at:
            raise ValueError("--from-raw requires --source-snapshot and --source-modified-at")
        portal = {
            "source_snapshot": date.fromisoformat(source_snapshot).isoformat(),
            "source_modified_at": date.fromisoformat(source_modified_at).isoformat(),
            "data_go_modified_at": date.fromisoformat(data_go_modified_at).isoformat(),
        }
    else:
        if raw_dir.exists() and any(raw_dir.iterdir()):
            raise FileExistsError(f"refusing to overwrite raw snapshot directory: {raw_dir}")
        raw, portal = download_official_csv()
        raw_path = raw_dir / f"seoul_restaurant_licenses_{portal['source_snapshot'].replace('-', '')}.csv"
        raw_dir.mkdir(parents=True, exist_ok=True)
        with raw_path.open("xb") as stream:
            stream.write(raw)
        print(f"download_response=content_type:{portal['content_type']}; disposition:{portal['content_disposition']}; bytes:{len(raw)}")
        del raw

    timestamp = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    raw_size = raw_path.stat().st_size
    digest = _sha256_file(raw_path)
    normalized_output.parent.mkdir(parents=True, exist_ok=True)
    temporary_output = normalized_output.with_name(normalized_output.name + ".tmp")
    if temporary_output.exists():
        raise FileExistsError(f"refusing to overwrite temporary normalized output: {temporary_output}")
    try:
        columns, row_count, empty_records, encoding = normalize_csv_file(
            raw_path,
            temporary_output,
            source_snapshot=portal["source_snapshot"],
            collected_at=timestamp,
            source_modified_at=portal["source_modified_at"],
            data_go_modified_at=portal["data_go_modified_at"],
        )
        temporary_output.replace(normalized_output)
    except Exception:
        temporary_output.unlink(missing_ok=True)
        raise

    raw_display = raw_path.relative_to(ROOT) if raw_path.is_relative_to(ROOT) else raw_path
    normalized_display = normalized_output.relative_to(ROOT) if normalized_output.is_relative_to(ROOT) else normalized_output
    print(f"source={SOURCE_URL}")
    if not from_raw:
        print(f"download_flow={portal['download_flow']}")
        print(f"download_outcome=single HTTP attachment; content_type={portal['content_type']}; attachment=true")
        print(f"login={portal['login']}; license={portal['license']}")
    print(f"raw={raw_display} bytes={raw_size} sha256={digest}")
    print(f"normalized={normalized_display} rows={row_count} columns={len(columns)} source_columns={len(columns) - len(PROVENANCE_FIELDS)} encoding={encoding} empty_records_skipped={empty_records}")
    print(f"source_snapshot={portal['source_snapshot']} source_modified_at={portal['source_modified_at']} data_go_modified_at={portal['data_go_modified_at']} collected_at={timestamp}")
    print(f"source_fields={columns[:-len(PROVENANCE_FIELDS)]}")
    return raw_path, normalized_output, row_count, columns, raw_size, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-date", default=datetime.now(timezone.utc).date().isoformat())
    parser.add_argument("--collected-at", help="fixed UTC collection timestamp for reproducible normalization")
    parser.add_argument("--from-raw", type=Path, help="normalize a saved CSV without contacting either portal")
    parser.add_argument("--source-snapshot", help="required with --from-raw (YYYY-MM-DD)")
    parser.add_argument("--source-modified-at", help="required with --from-raw (YYYY-MM-DD)")
    parser.add_argument("--data-go-modified-at", default="2025-08-08")
    parser.add_argument("--normalized-output", type=Path, default=NORMALIZED_PATH)
    args = parser.parse_args()
    collect(
        args.collection_date,
        args.collected_at,
        from_raw=args.from_raw,
        source_snapshot=args.source_snapshot or "",
        source_modified_at=args.source_modified_at or "",
        data_go_modified_at=args.data_go_modified_at,
        normalized_output=args.normalized_output,
    )


if __name__ == "__main__":
    main()
