import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fp import funding  # noqa: E402
from fp.build_site import funding_bars, funding_html  # noqa: E402

H = 3600 * 1000


def rows(rates, t0=1_755_561_600_000):
    return [{"time": t0 + i * H, "fundingRate": str(r)} for i, r in enumerate(rates)]


class FundingSummary(unittest.TestCase):
    def test_weeks_are_168h_buckets_from_listing(self):
        s = funding.summarize(rows([0.00001] * 168 + [0.00002] * 30))
        self.assertEqual([w["n"] for w in s["weeks"]], [1, 2])
        self.assertEqual(s["weeks"][1]["hours"], 30)
        self.assertAlmostEqual(s["weeks"][0]["apr"], 0.00001 * 8760)
        self.assertAlmostEqual(s["weeks"][1]["apr"], 0.00002 * 8760)

    def test_positive_share_and_windows(self):
        s = funding.summarize(rows([-0.00001] * 10 + [0.00001] * 190))
        self.assertAlmostEqual(s["pos_share"], 0.95)
        self.assertAlmostEqual(s["apr_24h"], 0.00001 * 8760)
        self.assertEqual(s["hours"], 200)

    def test_empty(self):
        self.assertIsNone(funding.summarize([]))


class FundingRender(unittest.TestCase):
    def test_partial_week_marked_and_negative_bar_below_zero(self):
        weeks = [{"n": 1, "apr": -0.03, "hours": 168}, {"n": 2, "apr": 0.2, "hours": 20}]
        svg = funding_bars(weeks, "#000")
        self.assertIn("W2*", svg)
        self.assertIn("-3%", svg)
        self.assertIn('opacity=".45"', svg)

    def test_empty_payload_degrades(self):
        self.assertIn("unavailable", funding_html({"assets": {}}, {"assets": {}}))


if __name__ == "__main__":
    unittest.main()
