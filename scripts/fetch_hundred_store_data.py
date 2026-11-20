#!/usr/bin/env python3
"""Download Data.go.kr dataset 15132695 through its official file button flow.

No API key or login is used. CAPTCHA/403/other portal access challenges are
reported as blockers; this script never solves or retries them. Raw and
normalized outputs are new, date-stamped files and are never overwritten.
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
DATASET_ID = "15132695"
DETAIL_ID = "uddi:706576c0-3d19-4e32-96be-d446b2b76bab"
SOURCE_URL = f"https://www.data.go.kr/data/{DATASET_ID}/fileData.do"
PORTAL = "https://www.data.go.kr"
RAW_ROOT = ROOT / "data/raw/hundred_stores"
PROCESSED_ROOT = ROOT / "data/processed"
NORMALIZED_PREFIX = "hundred_stores"
ADDED_FIELDS = ("source", "source_url", "source_snapshot", "collected_at", "source_modified_at")


class PortalDownloadError(RuntimeError):
    """The official portal flow failed or required an access challenge."""


def decode_csv(raw: bytes) -> tuple[str, str]:
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
    """Keep every source column/value and append provenance columns."""
    text, encoding = decode_csv(raw)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    source_columns = reader.fieldnames or []
    if not source_columns or any(not column for column in source_columns):
        raise ValueError("CSV has no valid header row")
    if len(set(source_columns)) != len(source_columns):
        raise ValueError(f"CSV has duplicate source columns: {source_columns}")
    collisions = sorted(set(source_columns).intersection(ADDED_FIELDS))
    if collisions:
        raise ValueError(f"Source columns collide with provenance fields: {collisions}")

    columns = [*source_columns, *ADDED_FIELDS]
    rows: list[dict[str, str]] = []
    for row in reader:
        if None in row:
            raise ValueError("CSV row contains more values than the source header")
        record = {column: (row.get(column) or "") for column in source_columns}
        record.update({
            "source": "hundred_store",
            "source_url": SOURCE_URL,
            "source_snapshot": source_snapshot,
            "collected_at": collected_at,
            "source_modified_at": source_modified_at,
        })
        rows.append(record)
    return columns, rows, encoding


def _open(opener: Any, request: urllib.request.Request, *, stage: str):
    try:
        response = opener.open(request, timeout=45)
    except urllib.error.HTTPError as error:
        if error.code in (401, 403, 429):
            raise PortalDownloadError(f"STOP: official portal blocked {stage} (HTTP {error.code}); no bypass attempted") from error
        raise PortalDownloadError(f"official portal failed {stage} (HTTP {error.code})") from error
    except urllib.error.URLError as error:
        raise PortalDownloadError(f"official portal unavailable during {stage}: {error.reason}") from error
    if response.status != 200:
        response.close()
        raise PortalDownloadError(f"STOP: official portal blocked {stage} (HTTP {response.status}); no bypass attempted")
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
        return json.loads(body.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PortalDownloadError(f"STOP: portal returned a non-JSON result during {stage}; no alternate route attempted") from error


def download_official_csv() -> tuple[bytes, dict[str, Any], str]:
    """Execute the same GET → file-button POST → CAPTCHA check → file GET flow."""
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
    button_action = f"fileDataDown('{DATASET_ID}', '{DETAIL_ID}',"
    if button_action not in page or "이용허락범위 제한 없음" not in page or "로그인 없이 다운로드" not in page:
        raise PortalDownloadError("STOP: official page no longer shows the expected free, unrestricted file-download action")
    modified_match = re.search(r'<input[^>]+id=["\']updtDt["\'][^>]+value=["\']([^"\']+)', page, re.I)
    source_modified_at = modified_match.group(1).split(" ", 1)[0] if modified_match else ""

    # The portal's page script checks this before invoking its download action.
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
    if int(file_check.get("count") or 0) > 1:
        print(f"Portal update notice: {file_check['count']} file registrations; page metadata modified {source_modified_at or 'date unavailable'}. This is informational; continuing with the displayed public download action.")

    # Exact parameters from the page's visible Download button and its linked JS.
    action = _post_json(opener, f"{PORTAL}/tcs/dss/selectFileDataDownload.do", {
        "publicDataDetailPk": DETAIL_ID,
        "publicDataPk": DATASET_ID,
        "atchFileId": "",
        "fileDetailSn": "1",
        "publicDataTyCode": "PR0051",
        "url": "/tcs/dss/selectFileDataDownload.do",
    }, headers, "official download action")
    if action.get("status") is not True:
        raise PortalDownloadError(f"STOP: official download action did not return success: {action.get('error') or action.get('errorDc') or 'no detail'}")
    detail = action.get("dataSetFileDetailInfo") or {}
    file_registration = action.get("fileDataRegistVO") or {}
    file_id = action.get("atchFileId")
    file_serial = str(action.get("fileDetailSn") or "")
    file_name = detail.get("dataNm") or ""
    expected_rows = detail.get("atchFileCo")
    extension = str(file_registration.get("atchFileExtsn") or "").lower()
    if not file_id or not file_serial or not file_name or extension != "csv":
        raise PortalDownloadError("STOP: portal result did not identify the expected CSV file")

    # This is the portal's own explicit rate-limit/CAPTCHA gate. Never solve it.
    gate = _post_json(opener, f"{PORTAL}/cmm/cmm/check-limit.json", {
        "atchFileId": str(file_id), "fileDetailSn": file_serial,
    }, headers, "official CAPTCHA/rate-limit check")
    if gate.get("needCaptcha") is True:
        raise PortalDownloadError("STOP: portal requires CAPTCHA; no file request made")
    if "needCaptcha" not in gate:
        raise PortalDownloadError("STOP: portal CAPTCHA gate response is ambiguous; no file request made")

    query = urllib.parse.urlencode({
        "atchFileId": str(file_id),
        "fileDetailSn": file_serial,
        "dataNm": file_name,
    })
    request = urllib.request.Request(f"{PORTAL}/cmm/cmm/fileDownload.do?{query}", headers=headers)
    response = _open(opener, request, stage="official file download")
    content_type = (response.headers.get("Content-Type") or "").lower()
    disposition = response.headers.get("Content-Disposition") or ""
    body = response.read()
    final_url = response.geturl()
    response.close()
    if "text/html" in content_type or not body or "attachment" not in disposition.lower():
        raise PortalDownloadError("STOP: portal did not return an attachment CSV; no alternate route attempted")
    # The portal filename is e.g. ..._20260820; retain that source snapshot date.
    snapshot_match = re.search(r"_(\d{8})$", file_name)
    if not snapshot_match:
        raise PortalDownloadError(f"Portal file name has no recognized source snapshot date: {file_name}")
    snapshot = datetime.strptime(snapshot_match.group(1), "%Y%m%d").date().isoformat()
    return body, {
        "fileName": file_name,
        "expectedRowCount": int(expected_rows) if str(expected_rows or "").isdigit() else None,
        "sourceModifiedAt": source_modified_at,
        "contentType": content_type,
        "contentDisposition": disposition,
        "finalUrl": final_url,
        "sourceSnapshot": snapshot,
        "fileId": str(file_id),
        "fileDetailSn": file_serial,
    }, snapshot


def write_normalized(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def collect(snapshot_date: str, collected_at: str | None = None) -> tuple[Path, Path, int, list[str], str]:
    collection_date = date.fromisoformat(snapshot_date).isoformat()
    raw, portal, source_snapshot = download_official_csv()
    collected_timestamp = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    collected_timestamp = collected_timestamp.replace("+00:00", "Z")
    normalized_columns, rows, encoding = normalize_csv_bytes(
        raw,
        source_snapshot=source_snapshot,
        collected_at=collected_timestamp,
        source_modified_at=portal["sourceModifiedAt"],
    )
    expected = portal.get("expectedRowCount")
    if expected is not None and len(rows) != expected:
        raise ValueError(f"Portal reports {expected} data rows but CSV parsed as {len(rows)}")
    digest = hashlib.sha256(raw).hexdigest()
    raw_dir = RAW_ROOT / collection_date
    raw_path = raw_dir / f"hundred_stores_{source_snapshot.replace('-', '')}.csv"
    processed_path = PROCESSED_ROOT / f"{NORMALIZED_PREFIX}_{collection_date}.csv"
    if raw_path.exists() or processed_path.exists():
        raise FileExistsError(f"refusing to overwrite existing snapshot/normalized file: {raw_path} or {processed_path}")

    raw_dir.mkdir(parents=True, exist_ok=True)
    with raw_path.open("xb") as stream:
        stream.write(raw)
    try:
        write_normalized(processed_path, normalized_columns, rows)
    except Exception:
        # Preserve the downloaded raw source; never remove user/source data on failure.
        raise
    print(f"source={SOURCE_URL}")
    print(f"raw={raw_path.relative_to(ROOT)} bytes={len(raw)} sha256={digest}")
    print(f"normalized={processed_path.relative_to(ROOT)} rows={len(rows)} columns={len(normalized_columns)} encoding={encoding}")
    print(f"portal_rows={expected} source_snapshot={source_snapshot} portal_modified={portal['sourceModifiedAt']} collected_at={collected_timestamp}")
    return raw_path, processed_path, len(rows), normalized_columns, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-date", default=datetime.now(timezone.utc).date().isoformat(), help="UTC collection date used in output paths (YYYY-MM-DD)")
    parser.add_argument("--collected-at", help="fixed UTC collection timestamp for repeatable normalization")
    args = parser.parse_args()
    collect(args.collection_date, args.collected_at)


if __name__ == "__main__":
    main()
