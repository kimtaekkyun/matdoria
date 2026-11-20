"""공공 식당 데이터를 Matdoria 공통 레코드 형식으로 정규화한다.

사용법:
    python scripts/prepare_public_sources.py
    python scripts/prepare_public_sources.py --model-csv data/raw/model_restaurant/source.csv

원본은 data/raw/에 보관하고, 정규화 결과는 data/processed/에 저장한다.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOOD_PRICE_RAW = ROOT / "data/raw/good_price/2026-11-12/good_price_20260930.csv"
GOOD_PRICE_OUT = ROOT / "data/processed/good_price_seoul.csv"
MODEL_OUT = ROOT / "data/processed/model_restaurant_seoul.csv"
GOOD_PRICE_URL = "https://www.data.go.kr/data/15172358/fileData.do"
MODEL_URL = "https://www.data.go.kr/data/15076765/fileData.do"
COLUMNS = [
    "source", "src_id", "name", "address", "source_category", "category",
    "food_type", "menu_items", "selected_year", "source_url", "source_snapshot", "collected_at",
]


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def stable_id(source: str, name: str, address: str) -> str:
    key = "|".join(unicodedata.normalize("NFKC", clean(x)).casefold() for x in (name, address))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def normalize_good_price(path: Path, collected_at: str) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for raw in csv.DictReader(stream):
            if clean(raw.get("광역")) != "서울특별시" or clean(raw.get("구분")) != "외식업":
                continue
            name, address = clean(raw.get("업소명")), clean(raw.get("주소"))
            if not name or not address:
                continue
            menus = []
            for i in range(1, 5):
                menu = clean(raw.get(f"착한가격메뉴 품목{i}"))
                price_raw = re.sub(r"[^0-9]", "", clean(raw.get(f"착한가격메뉴 가격{i}")))
                if menu:
                    menus.append({"name": menu, "price": int(price_raw) if price_raw else None})
            rows.append({
                "source": "good_price",
                "src_id": stable_id("good_price", name, address),
                "name": name,
                "address": address,
                "source_category": clean(raw.get("업종1(대분류)")),
                "category": clean(raw.get("업종2(세분류)")),
                "food_type": "",
                "menu_items": json.dumps(menus, ensure_ascii=False, separators=(",", ":")),
                "selected_year": "",
                "source_url": GOOD_PRICE_URL,
                "source_snapshot": "2026-09-30",
                "collected_at": collected_at,
            })
    return rows


HEADER_ALIASES = {
    "name": ("업소명", "업소명칭", "음식점명", "업소명(상호)", "상호명", "name"),
    "address": ("도로명주소", "소재지도로명주소", "소재지도로명", "주소", "소재지", "address"),
    "lot_address": ("지번주소", "소재지지번주소", "소재지지번", "lot_address"),
    "category": ("음식유형", "업태명", "업종", "음식종류", "category"),
    "food_type": ("주된음식", "주요음식", "대표음식", "음식명", "food_type"),
    "id": ("관리번호", "업소관리번호", "인허가번호", "번호", "id"),
    "year": ("지정일자", "지정연도", "등록일", "선정연도", "year"),
    "province": ("광역시도명", "시도명", "광역", "시도", "province"),
    "district": ("시군구명", "자치구", "구군", "시군구", "district"),
}


def find_column(fieldnames: list[str], aliases: tuple[str, ...]) -> str | None:
    normalized = {re.sub(r"\s+", "", name).casefold(): name for name in fieldnames}
    for alias in aliases:
        key = re.sub(r"\s+", "", alias).casefold()
        if key in normalized:
            return normalized[key]
    return None


def normalize_model_restaurants(path: Path, collected_at: str) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        cols = {key: find_column(fields, aliases) for key, aliases in HEADER_ALIASES.items()}
        if not cols["name"] or not (cols["address"] or cols["lot_address"]):
            raise ValueError(f"모범음식점 CSV에서 업소명/주소 열을 찾지 못했습니다: {fields}")
        rows = []
        for raw in reader:
            name = clean(raw.get(cols["name"]))
            address = clean(raw.get(cols["address"])) or clean(raw.get(cols["lot_address"]))
            province = clean(raw.get(cols["province"])) if cols["province"] else ""
            district_name = clean(raw.get(cols["district"])) if cols["district"] else ""
            if province.startswith("서울") and "서울" not in address:
                address = f"{province} {district_name} {address}".strip()
            if not name or not address or "서울" not in address:
                continue
            year_text = clean(raw.get(cols["year"])) if cols["year"] else ""
            year_match = re.search(r"(?:19|20)\d{2}", year_text)
            category = clean(raw.get(cols["category"])) if cols["category"] else ""
            food_type = clean(raw.get(cols["food_type"])) if cols["food_type"] else ""
            record_id = clean(raw.get(cols["id"])) if cols["id"] else ""
            rows.append({
                "source": "model_restaurant",
                "src_id": record_id or stable_id("model_restaurant", name, address),
                "name": name,
                "address": address,
                "source_category": category,
                "category": category,
                "food_type": food_type,
                "menu_items": "[]",
                "selected_year": year_match.group(0) if year_match else "",
                "source_url": MODEL_URL,
                "source_snapshot": "",
                "collected_at": collected_at,
            })
    return rows


def latest_model_csv() -> Path | None:
    candidates = sorted((ROOT / "data/raw/model_restaurant").glob("**/*.csv"))
    return candidates[-1] if candidates else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--good-price-csv", type=Path, default=GOOD_PRICE_RAW)
    parser.add_argument("--model-csv", type=Path, help="공식 모범음식점 원본 CSV (생략 시 data/raw/model_restaurant/에서 자동 탐색)")
    parser.add_argument("--collected-at", default=datetime.now(timezone.utc).date().isoformat())
    args = parser.parse_args()

    good_price = normalize_good_price(args.good_price_csv, args.collected_at)
    write_rows(GOOD_PRICE_OUT, good_price)
    print(f"착한가격업소: 서울 외식업 {len(good_price)}건 -> {GOOD_PRICE_OUT.relative_to(ROOT)}")

    model_path = args.model_csv or latest_model_csv()
    if model_path and model_path.exists():
        model = normalize_model_restaurants(model_path, args.collected_at)
        write_rows(MODEL_OUT, model)
        print(f"모범음식점: {len(model)}건 -> {MODEL_OUT.relative_to(ROOT)}")
    else:
        print("모범음식점: 원본 CSV 없음. 공식 파일 확보 후 --model-csv로 지정하십시오.")


if __name__ == "__main__":
    main()
