import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fp import build_site  # noqa: E402
from fp.glossary import glossary  # noqa: E402


class GlossaryCoverage(unittest.TestCase):
    def test_every_data_term_has_definition(self):
        page = build_site.build().read_text()
        used = set(re.findall(r'data-term="([a-z0-9_]+)"', page))
        defined = glossary()["terms"]
        self.assertTrue(used, "no glossary terms rendered")
        self.assertEqual(used - set(defined), set())
        for k in used:
            self.assertTrue(defined[k]["def"].strip(), k)
            self.assertIn(defined[k]["group"], glossary()["groups"], k)

    def test_required_terms_defined(self):
        need = """perp preipo_perp implied_valuation last_round multiple premium mark oracle funding funding_apr oi oi_cap
        volume_24h lower_bound upper_bound no_ipo hip3 hyperliquid entropy session discovery luld weekend_gap predicted
        actual hit_rate abs_err pp captured sparkline change_7d""".split()
        self.assertEqual(set(need) - set(glossary()["terms"]), set())

    def test_no_placeholders_left(self):
        page = build_site.build().read_text()
        self.assertNotRegex(page, r"__[A-Z_]+__")
        self.assertNotRegex(page, r"\{\{t:")
        self.assertNotIn("NaN", page)
        self.assertNotIn("undefined", page)


if __name__ == "__main__":
    unittest.main()
