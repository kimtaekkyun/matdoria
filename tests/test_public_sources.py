import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import match_public_sources
import prepare_public_sources
import export_places


class PublicSourcePreparationTests(unittest.TestCase):
    def test_good_price_filters_to_seoul_food_businesses_and_keeps_all_menus(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "good.csv"
            fields = [
                "광역", "구분", "업종1(대분류)", "업종2(세분류)", "업소명", "주소",
                "착한가격메뉴 품목1", "착한가격메뉴 가격1", "착한가격메뉴 품목2", "착한가격메뉴 가격2",
            ]
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerow({
                    "광역": "서울특별시", "구분": "외식업", "업종1(대분류)": "한식",
                    "업종2(세분류)": "한식_면류", "업소명": "가게", "주소": "서울 종로구 종로 1",
                    "착한가격메뉴 품목1": "국수", "착한가격메뉴 가격1": "8000",
                    "착한가격메뉴 품목2": "만두", "착한가격메뉴 가격2": "9000",
                })
                writer.writerow({"광역": "서울특별시", "구분": "기타개인서비스업", "업소명": "미용실"})
                writer.writerow({"광역": "부산광역시", "구분": "외식업", "업소명": "부산식당"})
            rows = prepare_public_sources.normalize_good_price(path, "2026-11-19")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["category"], "한식_면류")
            self.assertEqual(json.loads(rows[0]["menu_items"]), [
                {"name": "국수", "price": 8000}, {"name": "만두", "price": 9000},
            ])
            self.assertEqual(rows[0]["source_snapshot"], "2026-09-30")

    def test_model_restaurant_flexible_headers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "model.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["업소명", "소재지도로명주소", "업태명", "주된음식", "지정일자"])
                writer.writeheader()
                writer.writerow({"업소명": "모범식당", "소재지도로명주소": "서울 종로구 종로 1", "업태명": "한식", "주된음식": "불고기", "지정일자": "2024-03-01"})
            rows = prepare_public_sources.normalize_model_restaurants(path, "2026-11-19")
            self.assertEqual(rows[0]["source"], "model_restaurant")
            self.assertEqual(rows[0]["food_type"], "불고기")
            self.assertEqual(rows[0]["selected_year"], "2024")


class PublicSourceMatchingTests(unittest.TestCase):
    def test_address_verification_requires_matching_district_and_street_number(self):
        self.assertTrue(match_public_sources.address_verified(
            "서울특별시 종로구 종로 1 (종로1가)",
            "서울 종로구 종로 1", "서울 종로구 종로1가 1",
        ))
        self.assertFalse(match_public_sources.address_verified(
            "서울특별시 종로구 종로 1", "서울 종로구 종로 2", "서울 종로구 종로1가 2",
        ))
        self.assertFalse(match_public_sources.address_verified(
            "서울특별시 종로구 종로 1", "서울 중구 종로 1", "",
        ))
        self.assertFalse(match_public_sources.address_verified(
            "서울특별시 중구 을지로 1", "부산 중구 을지로 1", "",
        ))

    def test_only_single_exact_name_and_verified_address_candidate_is_accepted(self):
        source = {"name": "모범식당", "address": "서울특별시 종로구 종로 1"}
        good = {
            "id": "1", "place_name": "모범식당", "category_name": "음식점 > 한식",
            "road_address_name": "서울 종로구 종로 1", "address_name": "서울 종로구 종로1가 1",
        }
        wrong = {**good, "id": "2", "road_address_name": "서울 종로구 종로 2"}
        result, _ = match_public_sources.evaluate(source, [good, wrong])
        self.assertEqual(result["doc"]["id"], "1")
        result, _ = match_public_sources.evaluate(source, [good, {**good, "id": "3"}])
        self.assertIsNone(result)

    def test_export_preserves_public_source_details(self):
        good_price = export_places.source_entry({
            "source": "good_price", "name": "가게", "category": "한식_면류",
            "source_category": "한식", "menu_items": '[{"name":"국수","price":8000}]',
            "source_url": "https://example.test", "source_snapshot": "2026-09-30",
            "collected_at": "2026-11-19",
        })
        self.assertEqual(good_price["menuItems"], [{"name": "국수", "price": 8000}])
        self.assertEqual(good_price["categoryGroup"], "한식")
        model = export_places.source_entry({
            "source": "model_restaurant", "name": "모범식당", "category": "한식",
            "food_type": "불고기", "selected_year": "2024", "source_url": "https://example.test",
            "source_snapshot": "2024-12-31", "collected_at": "2026-11-19",
        })
        self.assertEqual(model["foodType"], "불고기")
        self.assertEqual(model["year"], 2024)


if __name__ == "__main__":
    unittest.main()
