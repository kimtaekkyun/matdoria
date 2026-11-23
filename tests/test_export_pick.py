import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from export_places import pick_entry, source_entry


PROFILE = {
    "profileVersion": "2.0.0",
    "dimensions": {
        "popularity": {
            "type": "review_count_thresholds",
            "thresholds": {"kakao_review_count": 50, "google_user_rating_count": 250},
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
                        "thresholds": {"kakaoReviewCount": 50, "googleUserRatingCount": 250},
                    }
                },
            }
        }
        result = pick_entry("42", scores, PROFILE)
        self.assertTrue(result["selected"])
        self.assertEqual(result["profileVersion"], "2.0.0")
        self.assertEqual(result["reviewCounts"], {"kakaoReviewCount": 259, "googleUserRatingCount": 495})
        self.assertEqual(result["thresholds"], {"kakaoReviewCount": 50, "googleUserRatingCount": 250})
        self.assertNotIn("score", result)

    def test_unknown_place_does_not_qualify_or_invent_review_counts(self):
        result = pick_entry("missing", {}, PROFILE)
        self.assertFalse(result["selected"])
        self.assertIsNone(result["reviewCounts"]["kakaoReviewCount"])
        self.assertIsNone(result["reviewCounts"]["googleUserRatingCount"])

    def test_exports_administrative_license_status_without_collection_timestamps(self):
        result = source_entry({
            "source": "restaurant_license",
            "resolved_current_status": "영업/정상",
            "업태구분명": "한식",
            "license_record_count": "2",
            "source_url": "https://www.data.go.kr/data/15071760/fileData.do",
            "사업장명": "우래옥 본점",
            "collected_at": "internal-only",
            "source_snapshot": "internal-only",
        })
        self.assertEqual(result["source"], "restaurant_license")
        self.assertEqual(result["status"], "영업/정상")
        self.assertEqual(result["businessType"], "한식")
        self.assertEqual(result["licenseRecordCount"], 2)
        self.assertNotIn("collectedAt", result)
        self.assertNotIn("sourceSnapshot", result)


if __name__ == "__main__":
    unittest.main()
