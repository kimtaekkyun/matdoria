#!/usr/bin/env python3
"""Fetch and normalize Data.go.kr dataset 15112215 via its official download flow.

The script follows the dataset page's displayed download action, checks the
portal's file-type and CAPTCHA/rate-limit responses, and makes at most one file
request. It stops on CAPTCHA, access denial, authentication, or an ambiguous
check response. It never solves or retries a challenge. Existing outputs are
never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "15112215"
SOURCE_URL = f"https://www.data.go.kr/data/{DATASET_ID}/fileData.do"
PORTAL = "https://www.data.go.kr"
RAW_ROOT = ROOT / "data/raw/gwangjin_hygiene"
NORMALIZED_PATH = ROOT / "data/processed/gwangjin_hygiene.csv"
PROVENANCE_FIELDS = (
    "source", "source_id", "source_url", "source_snapshot", "collected_at",
    "source_modified_at",
)


class PortalDownloadError(RuntimeError):
    """The official portal flow failed or required an access challenge."""


def _open(opener: Any, request: urllib.request.Request, *, stage: str):
    try:
        response = opener.open(request, timeout=45)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 429):
            raise PortalDownloadError(
                f"STOP: official portal blocked {stage} (HTTP {error.code}); no bypass attempted"
            ) from error
        raise PortalDownloadError(f"official portal failed {stage} (HTTP {error.code})") from error
    except urllib.error.URLError as error:
        raise PortalDownloadError(f"official portal unavailable during {stage}: {error.reason}") from error
    if response.status != 200:
        response.close()
        raise PortalDownloadError(
            f"STOP: official portal blocked {stage} (HTTP {response.status}); no bypass attempted"
        )
    return response


def _post_json(opener: Any, url: str, values: dict[str, str], headers: dict[str, str], stage: str) -> dict:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(values).encode("utf-8"),
        headers={**headers, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"},
        method="POST",
    )
    response = _open(opener, request, stage=stage)
    body = response.read()
    response.close()
    try:
        value = json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortalDownloadError(
            f"STOP: portal returned a non-JSON result during {stage}; no alternate route attempted"
        ) from error
    if not isinstance(value, dict):
        raise PortalDownloadError(f"STOP: ambiguous portal response during {stage}")
    return value


def _decode_csv(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("Downloaded file is not valid UTF-8/CP949 CSV text")


def normalize_csv_bytes(
    raw: bytes,
    *,
    source_snapshot: str,
    collected_at: str,
    source_modified_at: str,
) -> tuple[list[str], list[dict[str, str]], str]:
    """Preserve every source column and value, then append provenance fields."""
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

    columns = [*source_columns, *PROVENANCE_FIELDS]
    rows: list[dict[str, str]] = []
    for line_number, values in enumerate(reader, start=2):
        if not values or not any(values):  # Empty placeholder rows are not establishments.
            continue
        if len(values) != len(source_columns):
            raise ValueError(
                f"CSV row {line_number} has {len(values)} values; expected {len(source_columns)}"
            )
        row = dict(zip(source_columns, values))
        row.update({
            "source": "gwangjin_hygiene",
            "source_id": DATASET_ID,
            "source_url": SOURCE_URL,
            "source_snapshot": source_snapshot,
            "collected_at": collected_at,
            "source_modified_at": source_modified_at,
        })
        rows.append(row)
    return columns, rows, encoding


def count_source_records(raw: bytes) -> tuple[int, int]:
    """Return CSV data-record count and fully empty placeholder-row count."""
    text, _encoding = _decode_csv(raw)
    reader = csv.reader(io.StringIO(text, newline=""))
    next(reader, None)
    records = blanks = 0
    for values in reader:
        if not values:  # Physical blank lines are not CSV records.
            continue
        records += 1
        if not any(values):
            blanks += 1
    return records, blanks


def download_official_csv() -> tuple[bytes, dict[str, Any], str]:
    """Follow the page's visible CSV download action and its limit/CAPTCHA gate."""
    import http.cookiejar

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; Matdoria official public-data downloader/1.0)",
        "Referer": SOURCE_URL,
    }

    page_response = _open(opener, urllib.request.Request(SOURCE_URL, headers=headers), stage="dataset page")
    page = page_response.read().decode("utf-8", "replace")
    page_response.close()
    # Verify the public page still advertises this dataset and its unrestricted,
    # login-free CSV download before invoking the page's displayed button action.
    if (
        f'id="publicDataPk" name="publicDataPk" value="{DATASET_ID}"' not in page
        or "이용허락범위 제한 없음" not in page
        or "파일데이터는 로그인 없이 다운로드" not in page
        or "fileDetailObj.fn_fileDataDown" not in page
    ):
        raise PortalDownloadError(
            "STOP: official page no longer confirms the expected unrestricted, login-free download action"
        )

    detail_match = re.search(
        r"fileDetailObj\.fn_fileDataDown\(\s*'15112215'\s*,\s*'([^']+)'\s*,\s*'([^']*)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'\s*\)",
        page,
    )
    if not detail_match:
        raise PortalDownloadError("STOP: could not read the official page's displayed download action")
    detail_id, attachment_id, file_serial, history_serial = detail_match.groups()
    source_modified_match = re.search(
        r'<input[^>]+id=["\']updtDt["\'][^>]+value=["\']([^"\']+)', page, re.I
    )
    source_modified_at = source_modified_match.group(1).split(" ", 1)[0] if source_modified_match else ""
    advertised_match = re.search(r'>\s*전체 행\s*</strong>\s*<div class="value">([\d,]+)</div>', page)
    advertised_rows = int(advertised_match.group(1).replace(",", "")) if advertised_match else None

    # This GET is the same public pre-download check used by the portal page.
    check_request = urllib.request.Request(
        f"{PORTAL}/tcs/dss/checkFileType.do?{urllib.parse.urlencode({'publicDataPk': DATASET_ID})}",
        headers=headers,
    )
    check_response = _open(opener, check_request, stage="official file-type check")
    check_body = check_response.read()
    check_response.close()
    try:
        file_check = json.loads(check_body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortalDownloadError("STOP: non-JSON response from official file-type check") from error
    if file_check.get("result") is not True:
        raise PortalDownloadError("STOP: official file-type check did not confirm a downloadable file")

    # Submit the parameters used by the page's own fileDetailObj download button.
    action = _post_json(opener, f"{PORTAL}/tcs/dss/selectFileDataDownload.do", {
        "publicDataDetailPk": detail_id,
        "publicDataPk": DATASET_ID,
        "atchFileId": attachment_id,
        "fileDetailSn": file_serial,
        "publicDataTyCode": "PR0051",
        "url": "/tcs/dss/selectFileDataDownload.do",
    }, headers, "official download action")
    if action.get("status") is not True:
        raise PortalDownloadError(
            f"STOP: official download action did not return success: {action.get('error') or action.get('errorDc') or 'no detail'}"
        )
    detail = action.get("dataSetFileDetailInfo") or {}
    registration = action.get("fileDataRegistVO") or {}
    file_id = action.get("atchFileId")
    file_serial = str(action.get("fileDetailSn") or "")
    file_name = detail.get("dataNm") or detail.get("publicDataSj") or ""
    extension = str(registration.get("atchFileExtsn") or "").lower()
    if not file_id or not file_serial or not file_name or extension != "csv":
        raise PortalDownloadError("STOP: portal result did not identify the expected CSV file")

    # The portal's CAPTCHA/rate-limit gate is mandatory. Do not request the file
    # unless it explicitly returns needCaptcha=false.
    gate = _post_json(opener, f"{PORTAL}/cmm/cmm/check-limit.json", {
        "atchFileId": str(file_id), "fileDetailSn": file_serial,
    }, headers, "official CAPTCHA/rate-limit check")
    if gate.get("needCaptcha") is not False:
        if gate.get("needCaptcha") is True:
            raise PortalDownloadError("STOP: portal requires CAPTCHA; no file request made")
        raise PortalDownloadError("STOP: ambiguous CAPTCHA/rate-limit response; no file request made")

    query = urllib.parse.urlencode({
        "atchFileId": str(file_id), "fileDetailSn": file_serial, "dataNm": file_name,
    })
    response = _open(
        opener,
        urllib.request.Request(f"{PORTAL}/cmm/cmm/fileDownload.do?{query}", headers=headers),
        stage="official file download",
    )
    content_type = (response.headers.get("Content-Type") or "").lower()
    disposition = response.headers.get("Content-Disposition") or ""
    raw = response.read()
    final_url = response.geturl()
    response.close()
    if "text/html" in content_type or not raw or "attachment" not in disposition.lower():
        raise PortalDownloadError("STOP: portal did not return an attachment CSV; no alternate route attempted")

    # Use the portal's registered name to identify the source snapshot; do not
    # infer it from the advertised row count.
    stem = Path(file_name).stem
    snapshot_match = re.search(r"(20\d{6})$", stem.replace("-", ""))
    if not snapshot_match:
        raise PortalDownloadError(f"Portal filename has no recognizable snapshot date: {file_name}")
    snapshot = datetime.strptime(snapshot_match.group(1), "%Y%m%d").date().isoformat()
    return raw, {
        "file_name": file_name,
        "advertised_rows": advertised_rows,
        "source_modified_at": source_modified_at,
        "content_type": content_type,
        "content_disposition": disposition,
        "final_url": final_url,
        "file_type_check": file_check,
        "limit_check": gate,
        "history_serial": history_serial,
    }, snapshot


def collect(
    collection_date: str,
    collected_at: str | None = None,
    *,
    from_raw: Path | None = None,
    source_modified_at: str = "",
    normalized_output: Path = NORMALIZED_PATH,
) -> tuple[Path, Path, int, list[str], int, str]:
    day = date.fromisoformat(collection_date).isoformat()
    raw_dir = RAW_ROOT / day
    normalized_output = normalized_output.resolve()
    if normalized_output.exists():
        raise FileExistsError(f"refusing to overwrite normalized output: {normalized_output}")

    portal: dict[str, Any] = {}
    if from_raw:
        raw_path = from_raw.resolve()
        raw = raw_path.read_bytes()
        snapshot_match = re.search(r"(20\d{6})$", raw_path.stem.replace("-", ""))
        if not snapshot_match:
            raise ValueError(f"cannot infer source snapshot date from raw filename: {raw_path.name}")
        source_snapshot = datetime.strptime(snapshot_match.group(1), "%Y%m%d").date().isoformat()
        portal["source_modified_at"] = source_modified_at
        portal["advertised_rows"] = None
    else:
        if raw_dir.exists() and any(raw_dir.iterdir()):
            raise FileExistsError(f"refusing to overwrite raw snapshot directory: {raw_dir}")
        raw, portal, source_snapshot = download_official_csv()
        portal["source_modified_at"] = portal["source_modified_at"] or source_modified_at
        filename = Path(portal["file_name"]).name
        if not filename.lower().endswith(".csv"):
            filename += ".csv"
        raw_path = raw_dir / filename

    timestamp = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    columns, rows, encoding = normalize_csv_bytes(
        raw,
        source_snapshot=source_snapshot,
        collected_at=timestamp,
        source_modified_at=portal["source_modified_at"],
    )
    source_record_count, blank_record_count = count_source_records(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if not from_raw:
        raw_dir.mkdir(parents=True, exist_ok=True)
        with raw_path.open("xb") as stream:
            stream.write(raw)
    try:
        normalized_output.parent.mkdir(parents=True, exist_ok=True)
        with normalized_output.open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    except Exception:
        # Never delete the acquired raw source snapshot on normalization/write failure.
        raise

    print(f"source={SOURCE_URL}")
    if not from_raw:
        print(f"download_outcome=single HTTP attachment; content_type={portal['content_type']}; attachment=true")
        print(f"portal_checks=file_type:{portal['file_type_check']}; limit:{portal['limit_check']}")
        print(f"portal_advertised_rows={portal['advertised_rows']}")
    raw_display = raw_path.relative_to(ROOT) if raw_path.is_relative_to(ROOT) else raw_path
    normalized_display = normalized_output.relative_to(ROOT) if normalized_output.is_relative_to(ROOT) else normalized_output
    print(f"raw={raw_display} bytes={len(raw)} sha256={digest}")
    print(f"normalized={normalized_display} rows={len(rows)} columns={len(columns)} source_columns={len(columns) - len(PROVENANCE_FIELDS)} encoding={encoding}")
    print(f"source_csv_records={source_record_count} empty_placeholder_records={blank_record_count}")
    print(f"source_snapshot={source_snapshot} source_modified_at={portal['source_modified_at']} collected_at={timestamp}")
    print(f"source_fields={columns[:-len(PROVENANCE_FIELDS)]}")
    return raw_path, normalized_output, len(rows), columns, len(raw), digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection-date",
        default=datetime.now(timezone.utc).date().isoformat(),
        help="UTC raw-snapshot directory date (YYYY-MM-DD)",
    )
    parser.add_argument("--collected-at", help="fixed UTC collection timestamp for reproducible normalization")
    parser.add_argument("--from-raw", type=Path, help="normalize an acquired raw CSV without contacting the portal")
    parser.add_argument("--source-modified-at", default="", help="portal modification date when using --from-raw")
    parser.add_argument("--normalized-output", type=Path, default=NORMALIZED_PATH, help="output path; existing files are never replaced")
    args = parser.parse_args()
    collect(
        args.collection_date,
        args.collected_at,
        from_raw=args.from_raw,
        source_modified_at=args.source_modified_at,
        normalized_output=args.normalized_output,
    )


if __name__ == "__main__":
    main()
