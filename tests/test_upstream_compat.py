import unittest
import os
from pycg3.grammar import GrammarParser
from pycg3.engine import Disambiguator

UPSTREAM_TEST_DIR = "/tmp/cg3_upstream/test"


class TestUpstreamCompat(unittest.TestCase):
    def _run_test(self, test_name: str, sections: int = None):
        test_path = os.path.join(UPSTREAM_TEST_DIR, test_name)
        if not os.path.exists(test_path):
            self.skipTest(f"{test_name} not found in {UPSTREAM_TEST_DIR}")

        grammar_file = os.path.join(test_path, "grammar.cg3")
        input_file = os.path.join(test_path, "input.txt")
        expected_file = os.path.join(test_path, "expected.txt")

        with open(grammar_file, "r", encoding="utf-8", errors="replace") as gf:
            grammar = GrammarParser().parse(gf.read())

        with open(input_file, "r", encoding="utf-8", errors="replace") as inf:
            input_text = inf.read()

        with open(expected_file, "r", encoding="utf-8", errors="replace") as exf:
            expected_text = exf.read()

        engine = Disambiguator(grammar)
        actual_text = engine.run_text(input_text, num_sections=sections)

        # Normalize blank lines as diff -B does
        actual_lines = [l.rstrip() for l in actual_text.splitlines() if l.strip()]
        expected_lines = [l.rstrip() for l in expected_text.splitlines() if l.strip()]

        self.assertEqual(actual_lines, expected_lines)

    def test_context_test(self):
        self._run_test("T_ContextTest")

    def test_barrier(self):
        self._run_test("T_Barrier")

    def test_negated_context_test(self):
        self._run_test("T_NegatedContextTest")

    def test_multiple_sections(self):
        self._run_test("T_MultipleSections")

    def test_sections_num(self):
        self._run_test("T_Sections", sections=4)

    def test_iff(self):
        self._run_test("T_Iff")


if __name__ == '__main__':
    unittest.main()
