"""Tests that look into the neighbouring windows: the window options. The positions W < > themselves are covered by
the cases in fidelity_cases_traced.json, which were run through the real vislcg3."""

import unittest
from pycg3 import GrammarParser, Disambiguator


def window(word, tag):
    return '"<%s>"\n\t"%s" %s\n"<.>"\n\t"." CLB\n' % (word, word, tag)


# A is three windows before the window with B
FAR = window('a', 'A') + window('p', 'P') + window('q', 'P') + '"<b>"\n\t"b" B\n\t"b" C\n"<.>"\n\t"." CLB\n'
GRAMMAR = 'DELIMITERS = "<.>" ;\nLIST A = A ;\nLIST B = B ;\nSECTION\nREMOVE B (*-1< A) ;\n'


class TestWindowOptions(unittest.TestCase):
    def run_it(self, grammar, text, **options):
        return Disambiguator(GrammarParser().parse(grammar), **options).run_text(text)

    def test_two_windows_are_kept_behind_by_default(self):
        self.assertIn('"b" B', self.run_it(GRAMMAR, FAR))

    def test_num_windows(self):
        self.assertNotIn('"b" B', self.run_it(GRAMMAR, FAR, num_windows=3))
        self.assertIn('"b" B', self.run_it(GRAMMAR, FAR, num_windows=1))

    def test_always_span(self):
        grammar = 'DELIMITERS = "<.>" ;\nLIST A = A ;\nLIST B = B ;\nSECTION\nREMOVE B (*-1 A) ;\n'
        text = window('a', 'A') + '"<b>"\n\t"b" B\n\t"b" C\n"<.>"\n\t"." CLB\n'
        self.assertIn('"b" B', self.run_it(grammar, text))
        self.assertNotIn('"b" B', self.run_it(grammar, text, always_span=True))

    def test_a_window_sees_the_next_one_as_it_was_read(self):
        grammar = 'DELIMITERS = "<.>" ;\nLIST X = X ;\nLIST Y = Y ;\nSECTION\nREMOVE X (*1W Y) ;\n'
        text = '"<a>"\n\t"a" X\n\t"a" Z\n"<.>"\n\t"." CLB\n"<b>"\n\t"b" Y\n"<.>"\n\t"." CLB\n'
        self.assertNotIn('"a" X', self.run_it(grammar, text))

    def test_stream_still_hands_on_every_window_in_order(self):
        text = ''.join(window('w%d' % n, 'N') for n in range(7))
        out = Disambiguator(GrammarParser().parse(GRAMMAR)).run_text(text)
        self.assertEqual([l for l in out.split('\n') if l.startswith('"<w')], ['"<w%d>"' % n for n in range(7)])


if __name__ == '__main__':
    unittest.main()
