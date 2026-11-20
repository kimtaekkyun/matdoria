#!/usr/bin/env python3
"""Acquire Data.go.kr dataset 15132695 using the official page download flow.

One file attachment is requested per run. The portal's CAPTCHA/limit result
is honored by the shared official-flow helper; no challenge is solved or
retried. Use --from-raw only to normalize an already acquired raw snapshot.
Outputs are exclusive-create files and are never overwritten.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
from datetime import date, datetime, timezone
from pathlib import Path

# Shared, tested official Data.go.kr page-flow and CSV handling from the prior
# acquisition helper; this module adds the requested stable output paths.
from fetch_hundred_store_data import (
    ROOT,
    SOURCE_URL,
    download_official_csv,
    normalize_csv_bytes,
)

RAW_ROOT = ROOT / "data/raw/hundred_store"
DEFAULT_NORMALIZED = ROOT / "data/processed/hundred_stores.csv"


def _snapshot_from_name(path: Path) -> str:
    match = re.search(r"(20\d{6})", path.stem)
    if not match:
        raise ValueError(f"cannot infer portal source snapshot date from filename: {path.name}")
    return datetime.strptime(match.group(1), "%Y%m%d").date().isoformat()


def _write_csv_exclusive(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def collect(
    *,
    collection_date: str,
    normalized_output: Path = DEFAULT_NORMALIZED,
    collected_at: str | None = None,
    from_raw: Path | None = None,
    source_modified_at: str = "",
    expected_rows: int | None = None,
) -> tuple[Path, Path, int, str]:
    day = date.fromisoformat(collection_date).isoformat()
    normalized_output = normalized_output.resolve()
    if normalized_output.exists():
        raise FileExistsError(f"refusing to overwrite normalized output: {normalized_output}")

    portal: dict = {}
    if from_raw:
        raw = from_raw.read_bytes()
        source_snapshot = _snapshot_from_name(from_raw)
    else:
        raw, portal, source_snapshot = download_official_csv()
        source_modified_at = portal.get("sourceModifiedAt", "")
        expected_rows = portal.get("expectedRowCount")

    collected_timestamp = collected_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    columns, rows, _encoding = normalize_csv_bytes(
        raw,
        source_snapshot=source_snapshot,
        collected_at=collected_timestamp,
        source_modified_at=source_modified_at,
    )
    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(f"portal reports {expected_rows} data rows but parsed CSV has {len(rows)}")

    raw_dir = RAW_ROOT / day
    raw_target = raw_dir / f"hundred_stores_{source_snapshot.replace('-', '')}.csv"
    if raw_target.exists():
        raise FileExistsError(f"refusing to overwrite raw source snapshot: {raw_target}")

    raw_dir.mkdir(parents=True, exist_ok=True)
    with raw_target.open("xb") as stream:
        stream.write(raw)
    _write_csv_exclusive(normalized_output, columns, rows)
    digest = hashlib.sha256(raw).hexdigest()
    print(f"source={SOURCE_URL}")
    print(f"raw={raw_target.relative_to(ROOT)} bytes={len(raw)} sha256={digest}")
    print(f"normalized={normalized_output.relative_to(ROOT)} rows={len(rows)} columns={len(columns)}")
    print(f"source_snapshot={source_snapshot} source_modified_at={source_modified_at} collected_at={collected_timestamp}")
    return raw_target, normalized_output, len(rows), digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection-date", default=datetime.now(timezone.utc).date().isoformat(), help="UTC raw-snapshot directory date (YYYY-MM-DD)")
    parser.add_argument("--collected-at", help="fixed UTC collection timestamp for reproducible normalization")
    parser.add_argument("--normalized-output", type=Path, default=DEFAULT_NORMALIZED, help="normalized CSV path; existing files are never replaced")
    parser.add_argument("--from-raw", type=Path, help="normalize an already downloaded CSV without contacting the portal")
    parser.add_argument("--source-modified-at", default="", help="portal modification date when using --from-raw")
    parser.add_argument("--expected-rows", type=int, help="expected data-row count when using --from-raw")
    args = parser.parse_args()
    collect(
        collection_date=args.collection_date,
        normalized_output=args.normalized_output,
        collected_at=args.collected_at,
        from_raw=args.from_raw,
        source_modified_at=args.source_modified_at,
        expected_rows=args.expected_rows,
    )


if __name__ == "__main__":
    main()
