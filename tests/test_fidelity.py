"""pycg3 against vislcg3: each case in fidelity_cases.json is a small grammar, an input and the output the real
vislcg3 gave (made with tools/make_fidelity_cases.py). They pin down the corners real grammars lean on: the window
edges, 0* and its alternating scan, NOT with scanning and barriers, LINK and OR contexts, which rules re-run a
section, merged duplicate readings, set operators and unification."""
import json
import os
import unittest

from pycg3.grammar import GrammarParser
from pycg3.engine import Disambiguator

CASES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fidelity_cases.json")


def lines(text):
    return [l.rstrip() for l in text.split("\n") if l.strip()]


class TestFidelity(unittest.TestCase):
    def test_cases(self):
        with open(CASES, encoding="utf-8") as fh:
            cases = json.load(fh)
        self.assertGreater(len(cases), 100)
        failed = []
        for case in cases:
            engine = Disambiguator(GrammarParser().parse(case["grammar"]))
            got = engine.run_text(case["input"])
            if lines(got) != lines(case["expected"]):
                failed.append(case["name"])
        self.assertEqual(failed, [], "%d of %d cases differ from vislcg3: %s" % (len(failed), len(cases), failed[:10]))

    def test_traced_cases(self):
        """Dependencies in the input, relations, FROM, REMPARENT, SWITCHPARENT, merged mappings and tests that look into the
        neighbouring windows (W < >), with the -t labels."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fidelity_cases_traced.json")
        with open(path, encoding="utf-8") as fh:
            cases = json.load(fh)
        failed = []
        for case in cases:
            engine = Disambiguator(GrammarParser().parse(case["grammar"]), trace=True)
            got = engine.run_text(case["input"], trace=True, pipe_deleted=True)
            if lines(got) != lines(case["expected"]):
                failed.append(case["name"])
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
