import sys
import unittest
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fp import calls, findings  # noqa: E402
from fp.common import NY  # noqa: E402


def call_fixture():
    return {"made_at": "2026-10-05T09:00:00-04:00", "friday": "2026-10-02", "rows": [
        {"symbol": "io:SNDK", "fri_close": 100.0, "call_price": 100.4, "predicted": 0.004},
        {"symbol": "io:NBIS", "fri_close": 50.0, "call_price": 50.1, "predicted": 0.002},
        {"symbol": "io:DRAM", "fri_close": 20.0, "call_price": 19.98, "predicted": -0.001},
    ]}


class Calls(unittest.TestCase):
    def test_first_session_after_break(self):
        self.assertTrue(calls.first_session_after_break(date(2026, 10, 5)))   # Monday
        self.assertFalse(calls.first_session_after_break(date(2026, 10, 6)))  # Tuesday
        self.assertTrue(calls.first_session_after_break(date(2026, 9, 8)))    # Tuesday after Labor Day
        self.assertFalse(calls.first_session_after_break(date(2026, 9, 7)))   # Labor Day itself

    def test_outside_window_is_silent(self):
        self.assertIsNone(calls.make_call(now=datetime(2026, 10, 5, 10, 0, tzinfo=NY)))
        self.assertIsNone(calls.make_call(now=datetime(2026, 10, 6, 9, 0, tzinfo=NY)))

    def test_score(self):
        rows = calls.score(call_fixture(), {"io:SNDK": 100.5, "io:NBIS": 49.3, "io:DRAM": 20.001})
        by = {r["symbol"]: r for r in rows}
        self.assertTrue(by["io:SNDK"]["hit"])
        self.assertFalse(by["io:NBIS"]["hit"])
        self.assertIsNone(by["io:DRAM"]["hit"])  # |actual| < 0.1% is flat

    def test_texts_fit_one_post(self):
        c = call_fixture()
        self.assertLessEqual(len(calls.call_text(c, {"hits": 21, "n_scored": 27})), 280)
        c["receipt"] = calls.score(c, {"io:SNDK": 100.5, "io:NBIS": 49.3, "io:DRAM": 20.001})
        t = calls.receipt_text(c, {"2026-10-05": c})
        self.assertIn("Right direction on 1 of 2", t)
        self.assertLessEqual(len(t), 280)


def metrics_fixture(anth_f=0.098, oai_f=0.249, oi=41.9e6):
    return {
        "io:ANTH": {"short": "ANTH", "name": "Anthropic (pre-IPO)", "valuation_usd": 2.07e12, "last_round_usd": 965e9,
                    "multiple": 2.15, "prev_multiple": 2.14, "change_24h": 0.003, "funding_apr": anth_f,
                    "oi_usd": oi, "oi_cap_usd": 50e6},
        "io:OAI": {"short": "OAI", "name": "OpenAI (pre-IPO)", "valuation_usd": 1.69e12, "last_round_usd": 852e9,
                   "multiple": 1.98, "prev_multiple": 1.97, "change_24h": 0.009, "funding_apr": oai_f,
                   "oi_usd": 5.5e6, "oi_cap_usd": 12e6},
    }


class Findings(unittest.TestCase):
    def test_candidates_and_length(self):
        cs = findings.candidates(metrics_fixture(), {}, [], 1.27)
        types = {c["type"] for c in cs}
        self.assertTrue({"oi_cap", "funding_gap", "ratio", "baseline"} <= types)
        for c in cs:
            self.assertLessEqual(len(findings.compose(c, metrics_fixture(), "@entropyIO")), 270)
            self.assertTrue(c["id"])

    def test_milestone_crossing(self):
        m = metrics_fixture()
        m["io:OAI"]["prev_multiple"], m["io:OAI"]["multiple"] = 1.98, 2.02
        cs = findings.candidates(m, {}, [], None)
        self.assertIn("milestone", {c["type"] for c in cs})

    def test_rotation_penalty(self):
        cs = findings.candidates(metrics_fixture(), {}, [], 1.27)
        first = findings.choose(cs, [], "2026-10-10")
        again = findings.choose(cs, [{"date": "2026-10-09", "type": first["type"]}], "2026-10-10")
        self.assertNotEqual(first["type"], again["type"])

    def test_no_signature_twice_on_ratio(self):
        c = {"type": "ratio", "en": "x", "id": "y"}
        self.assertNotIn("ANTH/OAI", findings.compose(c, metrics_fixture(), "@entropyIO"))


if __name__ == "__main__":
    unittest.main()
