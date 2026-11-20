import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import score_matdoria_pick

PROFILE = json.loads((ROOT / "data/curation/matdoria_pick_score_v1.json").read_text(encoding="utf-8"))
HASHES = {
    "profile": "profile-hash",
    "places_matched": "places-hash",
    "public_sources_matched": "public-hash",
    "kakao_ratings": "kakao-hash",
    "google_ratings": "google-hash",
}


def matched(source, source_id, place_id, **kwargs):
    row = {
        "source": source,
        "src_id": source_id,
        "match_kakao_id": place_id,
        "match_confidence": "high",
        "match_kakao_name": f"Place {place_id}",
        "match_kakao_address": "서울 종로구 종로 1",
        "match_kakao_url": f"https://map.test/{place_id}",
        "match_rule": "fixture_verified",
        "source_url": f"https://source.test/{source}/{source_id}",
    }
    row.update(kwargs)
    return row


def kakao(place_id, count, **kwargs):
    return {"kakao_place_id": place_id, "review_count": str(count) if count is not None else "", "status": "ok", "collected_at": "2026-11-13T00:00:00Z", **kwargs}


def google(source, source_id, place_id, google_id, count, distance=30, **kwargs):
    return {
        "source": source, "src_id": source_id, "google_place_id": google_id,
        "user_rating_count": str(count) if count is not None else "", "distance_m": str(distance),
        "status": "ok", "collected_at": "2026-11-13T00:00:00Z", **kwargs,
    }


def score(rows, public=None, review_counts=None):
    return score_matdoria_pick.score_rows(
        rows, public or [], PROFILE, "2026-11-20T00:00:00.000000Z", HASHES, review_counts,
    )


class ReviewCountAssemblyTests(unittest.TestCase):
    def test_exact_thresholds_qualify_and_one_below_does_not(self):
        matches = [
            matched("michelin", "a", "1", src_group="3 Stars"),
            matched("michelin", "b", "2", src_group="3 Stars"),
            matched("michelin", "c", "3", src_group="3 Stars"),
        ]
        kakao_rows = [kakao("1", 50, rating="1.0"), kakao("2", 49), kakao("3", 50)]
        google_rows = [
            google("michelin", "a", "1", "g1", 250, rating="1.0"),
            google("michelin", "b", "2", "g2", 250, rating="5.0"),
            google("michelin", "c", "3", "g3", 249),
        ]
        counts = score_matdoria_pick.assemble_canonical_review_counts(kakao_rows, google_rows, matches)
        payload = score(matches, review_counts=counts)
        places = {item["placeId"]: item for item in payload["places"]}
        self.assertTrue(places["1"]["selected"])
        self.assertEqual(places["1"]["pickScore"], 1.0)
        self.assertFalse(places["2"]["selected"])
        self.assertEqual(places["2"]["pickScore"], 0.0)
        self.assertFalse(places["3"]["selected"])
        self.assertEqual(places["3"]["pickScore"], 0.0)
        self.assertEqual(payload["metadata"]["selectedPlaceCount"], 1)
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn('"rating"', serialized)
        def contains_average_field(value):
            if isinstance(value, dict):
                return any(key in {"rating", "averageRating", "ratingAverage"} or contains_average_field(item) for key, item in value.items())
            if isinstance(value, list):
                return any(contains_average_field(item) for item in value)
            return False
        self.assertFalse(contains_average_field(payload))
        self.assertFalse(payload["metadata"]["platformRatingAveragesUsed"])
        self.assertTrue(payload["metadata"]["platformReviewCountsUsed"])

    def test_missing_either_count_is_unknown_not_zero_and_does_not_qualify(self):
        matches = [matched("michelin", "a", "1"), matched("michelin", "b", "2")]
        counts = score_matdoria_pick.assemble_canonical_review_counts(
            [kakao("1", 100)],
            [google("michelin", "b", "2", "g2", 500)],
            matches,
        )
        payload = score(matches, review_counts=counts)
        places = {item["placeId"]: item for item in payload["places"]}
        popularity = places["1"]["dimensions"]["popularity"]
        self.assertEqual(popularity["status"], "unknown")
        self.assertIsNone(popularity["score"])
        self.assertIsNone(popularity["counts"]["googleUserRatingCount"])
        self.assertEqual(places["1"]["pickScoreStatus"], "unknown")
        self.assertIsNone(places["1"]["pickScore"])
        self.assertFalse(places["1"]["selected"])
        self.assertEqual(places["2"]["dimensions"]["popularity"]["counts"]["kakaoReviewCount"], None)
        self.assertEqual(places["2"]["dimensions"]["popularity"]["status"], "unknown")

    def test_google_joins_only_high_status_ok_nearby_records_and_uses_closest(self):
        matches = [
            matched("michelin", "m1", "1"),
            matched("seoul_heritage", "h1", "1"),
            matched("michelin", "m2", "2"),
            matched("michelin", "m3", "3", match_confidence="medium"),
        ]
        google_rows = [
            google("michelin", "m1", "1", "g1", 500, distance=80),
            google("seoul_heritage", "h1", "1", "g1", 300, distance=25),
            google("michelin", "m2", "2", "g2a", 500, distance=20),
            google("michelin", "m2", "2", "g2b", 600, distance=30),
            google("michelin", "m3", "3", "g3", 999, distance=10),
            google("michelin", "m1", "1", "far", 9000, distance=120),
            google("michelin", "m1", "1", "bad-status", 9000, status="far", distance=10),
        ]
        counts = score_matdoria_pick.assemble_canonical_review_counts(
            [kakao("1", 50), kakao("2", 50), kakao("3", 50)], google_rows, matches,
        )
        self.assertEqual(counts["1"]["google"]["count"], 300)
        self.assertEqual(counts["1"]["google"]["distanceMeters"], 25.0)
        self.assertEqual(counts["2"]["google"]["status"], "unknown")
        self.assertEqual(counts["2"]["google"]["reason"], "ambiguous_google_place_id")
        self.assertNotIn("3", counts)  # medium match is not a canonical join
        self.assertEqual(len([e for e in counts["1"]["google"]["evidence"] if e.get("exclusionReason") == "distance_missing_or_over_100m"]), 1)
        self.assertNotIn("rating", json.dumps(counts))

    def test_kakao_requires_status_ok_and_valid_nonnegative_count(self):
        matches = [matched("michelin", "m1", "1")]
        counts = score_matdoria_pick.assemble_canonical_review_counts(
            [kakao("1", 400, status="no_rating")], [], matches,
        )
        self.assertIsNone(counts["1"]["kakao"]["count"])
        self.assertEqual(counts["1"]["kakao"]["status"], "unknown")
        self.assertEqual(counts["1"]["kakao"]["evidence"][0]["exclusionReason"], "status_not_ok")

    def test_star_averages_and_diagnostic_sources_do_not_influence_pick(self):
        rows = [matched("michelin", "m1", "1", src_group="3 Stars", rating="5.0")]
        public = [matched("good_price", "g1", "1", category="food", menu_items="[]", rating="5.0")]
        counts = score_matdoria_pick.assemble_canonical_review_counts(
            [kakao("1", 49, rating="5.0")],
            [google("michelin", "m1", "1", "google-1", 1000, rating="5.0"),
             google("good_price", "g1", "1", "google-1", 1000, rating="5.0")],
            rows, public,
        )
        place = score(rows, public, counts)["places"][0]
        self.assertFalse(place["selected"])
        self.assertEqual(place["pickScore"], 0.0)
        self.assertEqual(place["dimensions"]["expert_recognition"]["score"], 10.0)
        self.assertEqual(place["dimensions"]["value"]["score"], 1.0)

    def test_input_hashes_timestamp_and_threshold_coverage_are_retained(self):
        rows = [matched("michelin", "m1", "1")]
        counts = score_matdoria_pick.assemble_canonical_review_counts(
            [kakao("1", 50)], [google("michelin", "m1", "1", "g1", 250)], rows,
        )
        payload = score(rows, review_counts=counts)
        metadata = payload["metadata"]
        self.assertEqual(metadata["buildTimestamp"], "2026-11-20T00:00:00.000000Z")
        self.assertEqual(metadata["inputSha256"]["kakaoRatings"], "kakao-hash")
        self.assertEqual(metadata["inputSha256"]["googleRatings"], "google-hash")
        self.assertEqual(metadata["reviewCountThresholds"], {"kakao_review_count": 50, "google_user_rating_count": 250})
        self.assertEqual(payload["reviewCountCoverage"]["qualifyingPlaces"], 1)

    def test_no_mapping_means_unknown_not_zero(self):
        payload = score([matched("michelin", "m1", "1", src_group="3 Stars")])
        place = payload["places"][0]
        self.assertIsNone(place["pickScore"])
        self.assertFalse(place["selected"])
        self.assertEqual(place["dimensions"]["popularity"]["status"], "unknown")
        self.assertEqual(place["dimensions"]["expert_recognition"]["score"], 10.0)


if __name__ == "__main__":
    unittest.main()
