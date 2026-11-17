import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scripts import match_kakao
import match_address_fallback


def candidate(
    *,
    distance=10,
    sim=1.0,
    category="음식점 > 한식",
    name_only=False,
    kakao_address="서울 종로구 10길 1",
    juso_eng="10 Jongno-ro, Jongno-gu, Seoul",
):
    return {
        "distance_m": distance,
        "sim": sim,
        "kakao_category": category,
        "is_food": match_kakao.is_food_category(category),
        "is_name_eligible": match_kakao.is_name_eligible_category(category),
        "name_only": name_only,
        "kakao_address": kakao_address,
        "juso_eng": juso_eng,
    }


class CategoryEligibilityTests(unittest.TestCase):
    def test_accepts_food_venues_shops_and_documented_food_alley(self):
        for category in (
            "음식점 > 한식",
            "음식점 > 간식 > 제과,베이커리",
            "음식점 > 카페",
            "음식점 > 술집 > 호프,요리주점",
            match_kakao.FOOD_ALLEY_CATEGORY,
        ):
            with self.subTest(category=category):
                self.assertTrue(match_kakao.is_name_eligible_category(category))

    def test_rejects_unrelated_and_broad_categories(self):
        for category in (
            "가정,생활 > 시장",
            "여행 > 숙박 > 호텔",
            "여행 > 관광,명소 > 문화유적",
            "문화,예술 > 문화시설",
            "교육,학문 > 학습시설 > 도서관",
            "스포츠,레저 > 스포츠시설",
            "사회,공공기관 > 단체,협회",
            "쇼핑 > 서점",
            "",
        ):
            with self.subTest(category=category):
                self.assertFalse(match_kakao.is_name_eligible_category(category))


class AddressFallbackTests(unittest.TestCase):
    def test_address_fallback_only_accepts_food_categories(self):
        restaurant = candidate(distance=20, category="음식점 > 한식")
        hotel = candidate(distance=1, category="여행 > 숙박 > 호텔")
        too_far = candidate(distance=301, category="음식점 > 한식", sim=0.9)

        self.assertEqual(
            match_address_fallback.eligible_address_candidates([hotel, too_far, restaurant]),
            [restaurant],
        )


class DecideTests(unittest.TestCase):
    def test_name_near_uses_only_eligible_categories(self):
        unrelated = candidate(category="여행 > 숙박 > 호텔")
        verdict, selected, rule = match_kakao.decide([unrelated])
        self.assertEqual((verdict, selected, rule), ("drop", None, "-"))

        alley = candidate(category=match_kakao.FOOD_ALLEY_CATEGORY, distance=40, sim=0.9)
        verdict, selected, rule = match_kakao.decide([unrelated, alley])
        self.assertEqual((verdict, selected, rule), ("accept", alley, "name_near"))

    def test_name_far_uses_only_eligible_categories(self):
        unrelated = candidate(distance=200, category="여행 > 숙박 > 호텔")
        self.assertEqual(match_kakao.decide([unrelated]), ("drop", None, "-"))

        food = candidate(distance=200, sim=0.9)
        verdict, selected, rule = match_kakao.decide([food])
        self.assertEqual((verdict, selected, rule), ("accept", food, "name_far"))

    def test_name_only_uses_only_eligible_categories(self):
        unrelated = candidate(distance=500, category="문화,예술 > 문화시설", name_only=True)
        self.assertEqual(match_kakao.decide([unrelated]), ("drop", None, "-"))

        bakery = candidate(distance=500, category="음식점 > 간식 > 제과,베이커리", name_only=True)
        verdict, selected, rule = match_kakao.decide([bakery])
        self.assertEqual((verdict, selected, rule), ("accept", bakery, "name_only"))

    def test_address_verified_en_rule(self):
        food = candidate(distance=500, sim=0, juso_eng="10 Jongno-ro, Jongno-gu, Seoul")
        verdict, selected, rule = match_kakao.decide([food], src_en="10 Jongno-ro, Jongno-gu, Seoul")
        self.assertEqual((verdict, selected, rule), ("accept", food, "address_verified_en"))

    def test_address_verified_rule(self):
        food = candidate(distance=200, sim=0, kakao_address="서울 종로구 종로 10")
        verdict, selected, rule = match_kakao.decide([food], src_address="종로구 종로 10")
        self.assertEqual((verdict, selected, rule), ("accept", food, "address_verified"))

    def test_nearest_food_rule(self):
        food = candidate(distance=15, sim=0)
        verdict, selected, rule = match_kakao.decide([food])
        self.assertEqual((verdict, selected, rule), ("accept", food, "nearest_food"))

    def test_drop_rule(self):
        self.assertEqual(match_kakao.decide([]), ("drop", None, "-"))


if __name__ == "__main__":
    unittest.main()
