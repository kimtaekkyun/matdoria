import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_places import pick_entry, source_entry


PROFILE = {
    "profileVersion": "2.1.0",
    "dimensions": {
        "popularity": {
            "type": "review_count_thresholds",
            "thresholds": {
                "kakao_review_count": 50, "google_user_rating_count": 250,
                "kakao_rating": 3.5, "google_rating": 4.0,
            },
        }
    },
}


class ExportPickTests(unittest.TestCase):
    def test_exports_threshold_qualification_and_counts_without_a_summed_score(self):
        scores = {
            "42": {
                "selected": True,
                "dimensions": {
                    "popularity": {
                        "counts": {"kakaoReviewCount": 259, "googleUserRatingCount": 495},
                        "thresholds": {
                            "kakaoReviewCount": 50, "googleUserRatingCount": 250,
                            "kakaoRating": 3.5, "googleRating": 4.0,
                        },
                    }
                },
            }
        }
        result = pick_entry("42", scores, PROFILE)
        self.assertTrue(result["selected"])
        self.assertEqual(result["profileVersion"], "2.1.0")
        self.assertEqual(result["reviewCounts"], {"kakaoReviewCount": 259, "googleUserRatingCount": 495})
        self.assertEqual(result["thresholds"], {
            "kakaoReviewCount": 50, "googleUserRatingCount": 250,
            "kakaoRating": 3.5, "googleRating": 4.0,
        })
        self.assertNotIn("score", result)

    def test_unknown_place_does_not_qualify_or_invent_review_counts(self):
        result = pick_entry("missing", {}, PROFILE)
        self.assertFalse(result["selected"])
        self.assertIsNone(result["reviewCounts"]["kakaoReviewCount"])
        self.assertIsNone(result["reviewCounts"]["googleUserRatingCount"])

    def test_administrative_license_status_is_not_public_place_source(self):
        with self.assertRaises(KeyError):
            source_entry({"source": "restaurant_license"})


if __name__ == "__main__":
    unittest.main()
