import unittest
import io
from pycg3.stream import parse_stream, split_tags
from pycg3.cohort import Cohort, Reading, SingleWindow


class TestStream(unittest.TestCase):
    def test_split_tags(self):
        tags = split_tags('wanted (@A @B) "word" r"abc"')
        self.assertEqual(tags, ['wanted', '(@A @B)', '"word"', 'r"abc"'])

    def test_split_tags_nested_parens(self):
        tags = split_tags('(NOT 1* (something) BARRIER (block))')
        self.assertEqual(tags, ['(NOT 1* (something) BARRIER (block))'])

    def test_stream_parsing(self):
        text = '''"<word>" untouchable
\t"word" N SG @SUBJ>
\t"word" V PRES
"<.>"
\t"." CLB
'''
        stream = io.StringIO(text)
        windows = list(parse_stream(stream))
        self.assertEqual(len(windows), 1)
        win = windows[0]
        self.assertEqual(len(win.cohorts), 2)
        c0 = win.cohorts[0]
        self.assertEqual(c0.wordform, '"<word>"')
        self.assertEqual(c0.untouchable_tags, ['untouchable'])
        self.assertEqual(len(c0.readings), 2)
        self.assertEqual(c0.readings[0].baseform, '"word"')
        self.assertEqual(c0.readings[0].tags, ['N', 'SG', '@SUBJ>'])

    def test_wordform_and_baseform_with_special_characters(self):
        """'>' and '"' as word forms ("<>>", "<">"), and '"' as a base form, as hfst-tokenise writes them."""
        text = '"<a>"\n\t"a" N\n"<>>"\n\t">" PUNCT RIGHT\n"<">"\n\t""" PUNCT\n"<.>"\n\t"." CLB\n'
        win = list(parse_stream(io.StringIO(text)))[0]
        self.assertEqual([c.wordform for c in win.cohorts], ['"<a>"', '"<>>"', '"<">"', '"<.>"'])
        self.assertEqual([len(c.readings) for c in win.cohorts], [1, 1, 1, 1])
        self.assertEqual(win.cohorts[1].readings[0].baseform, '">"')
        self.assertEqual(win.cohorts[2].readings[0].baseform, '"""')
        self.assertEqual(win.cohorts[2].readings[0].tags, ['PUNCT'])
        self.assertIn('\t""" PUNCT', win.to_text())

    def test_sub_readings(self):
        text = '''"<compound>"
\t"comp" N
\t\t"part1" PREF
\t\t"part2" ROOT
'''
        stream = io.StringIO(text)
        windows = list(parse_stream(stream))
        c = windows[0].cohorts[0]
        r = c.readings[0]
        self.assertEqual(len(r.sub_readings), 2)
        self.assertEqual(r.sub_readings[0].baseform, '"part1"')
        self.assertEqual(r.sub_readings[1].baseform, '"part2"')


if __name__ == '__main__':
    unittest.main()
