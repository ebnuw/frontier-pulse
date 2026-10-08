import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fp import weekend  # noqa: E402
from fp.common import NY, funding_apr, implied_valuation_usd, next_trading_day, prev_trading_day  # noqa: E402


def candle(d, hh, mm, close):
    t = int(datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp() * 1000)
    return {"t": t, "c": str(close)}


def make(fri, mon, f, p, o, fri_time=(15, 45)):
    cs = [candle(fri, *fri_time, f), candle(mon, 9, 15, p), candle(mon, 9, 30, o)]
    return {c["t"]: c for c in cs}


class ValuationMath(unittest.TestCase):
    def test_valuation(self):
        self.assertEqual(implied_valuation_usd(2086), 2.086e12)

    def test_apr(self):
        self.assertAlmostEqual(funding_apr(0.0000125), 0.1095)
        self.assertAlmostEqual(funding_apr(-0.00002), -0.1752)


class Calendar(unittest.TestCase):
    def test_labor_day_skipped(self):
        self.assertEqual(next_trading_day(date(2026, 9, 5) + timedelta(days=1)), date(2026, 9, 8))

    def test_good_friday_prev(self):
        self.assertEqual(prev_trading_day(date(2026, 4, 4)), date(2026, 4, 2))


class WeekendMath(unittest.TestCase):
    def test_hit_and_capture(self):
        by = make(date(2026, 10, 2), date(2026, 10, 5), 100, 101, 102)
        r = weekend.weekend_row(by, date(2026, 10, 3))
        self.assertAlmostEqual(r["predicted"], 0.01)
        self.assertAlmostEqual(r["actual"], 0.02)
        self.assertTrue(r["hit"])
        self.assertAlmostEqual(r["abs_err_pp"], 1.0)
        self.assertAlmostEqual(r["captured"], 0.5)

    def test_miss(self):
        by = make(date(2026, 10, 2), date(2026, 10, 5), 100, 101, 98)
        r = weekend.weekend_row(by, date(2026, 10, 3))
        self.assertFalse(r["hit"])
        self.assertIsNone(r["captured"])
        self.assertAlmostEqual(r["abs_err_pp"], 3.0)

    def test_flat_not_scored(self):
        by = make(date(2026, 10, 2), date(2026, 10, 5), 100, 100.5, 100.05)
        r = weekend.weekend_row(by, date(2026, 10, 3))
        self.assertTrue(r["flat"])
        self.assertIsNone(r["hit"])

    def test_missing_candle_skips(self):
        by = make(date(2026, 10, 2), date(2026, 10, 5), 100, 101, 102)
        del by[next(iter(by))]
        self.assertIsNone(weekend.weekend_row(by, date(2026, 10, 3)))

    def test_holiday_monday_moves_to_tuesday(self):
        # Labor Day 2026-09-07: Fri 09-04 -> Tue 09-08
        by = make(date(2026, 9, 4), date(2026, 9, 8), 50, 51, 52)
        r = weekend.weekend_row(by, date(2026, 9, 5))
        self.assertEqual(r["monday"], "2026-09-08")

    def test_early_close_reference(self):
        # Fri 2026-11-27 closes 13:00 -> ref is 12:45 candle
        by = make(date(2026, 11, 27), date(2026, 11, 30), 10, 10.1, 10.2, fri_time=(12, 45))
        r = weekend.weekend_row(by, date(2026, 11, 28))
        self.assertIsNotNone(r)

    def test_dst_correct(self):
        # Winter (EST) weekend: candle timestamps differ in UTC but still map to ET wall clock
        by = make(date(2026, 12, 4), date(2026, 12, 7), 100, 99, 98)
        r = weekend.weekend_row(by, date(2026, 12, 5))
        self.assertTrue(r["hit"])

    def test_aggregate(self):
        rows = [
            {"symbol": "a", "friday": "x", "monday": "y", "hit": True, "abs_err_pp": 1.0, "captured": 0.5},
            {"symbol": "b", "friday": "x", "monday": "y", "hit": False, "abs_err_pp": 3.0, "captured": None},
        ]
        agg = weekend.aggregate({"x": rows})
        self.assertAlmostEqual(agg["overall"]["hit_rate"], 0.5)
        self.assertAlmostEqual(agg["overall"]["mean_abs_err_pp"], 2.0)


if __name__ == "__main__":
    unittest.main()
