import unittest
from pycg3.grammar import GrammarParser
from pycg3.engine import Disambiguator


class TestRules(unittest.TestCase):
    def test_select_rule(self):
        grammar_text = '''
        DELIMITERS = "<$.>" ;
        SECTION
        SELECT (V) ;
        '''
        input_text = '''"<word>"
\t"word" N
\t"word" V
'''
        grammar = GrammarParser().parse(grammar_text)
        engine = Disambiguator(grammar)
        res = engine.run_text(input_text)
        expected = '''"<word>"
\t"word" V
'''
        self.assertEqual(res.strip(), expected.strip())

    def test_remove_rule(self):
        grammar_text = '''
        DELIMITERS = "<$.>" ;
        SECTION
        REMOVE (N) ;
        '''
        input_text = '''"<word>"
\t"word" N
\t"word" V
'''
        grammar = GrammarParser().parse(grammar_text)
        engine = Disambiguator(grammar)
        res = engine.run_text(input_text)
        expected = '''"<word>"
\t"word" V
'''
        self.assertEqual(res.strip(), expected.strip())

    def test_add_rule(self):
        grammar_text = '''
        DELIMITERS = "<$.>" ;
        SECTION
        ADD (@VERB) (V) ;
        '''
        input_text = '''"<word>"
\t"word" V
'''
        grammar = GrammarParser().parse(grammar_text)
        engine = Disambiguator(grammar)
        res = engine.run_text(input_text)
        expected = '''"<word>"
\t"word" V @VERB
'''
        self.assertEqual(res.strip(), expected.strip())

    def test_substitute_rule(self):
        grammar_text = '''
        DELIMITERS = "<$.>" ;
        SECTION
        SUBSTITUTE (old) (new1 new2) (target) ;
        '''
        input_text = '''"<word>"
\t"word" target old other
'''
        grammar = GrammarParser().parse(grammar_text)
        engine = Disambiguator(grammar)
        res = engine.run_text(input_text)
        expected = '''"<word>"
\t"word" target new1 new2 other
'''
        self.assertEqual(res.strip(), expected.strip())

    def test_replace_rule(self):
        grammar_text = '''
        DELIMITERS = "<$.>" ;
        SECTION
        REPLACE (N SG) (target) ;
        '''
        input_text = '''"<word>"
\t"word" target old other
'''
        grammar = GrammarParser().parse(grammar_text)
        engine = Disambiguator(grammar)
        res = engine.run_text(input_text)
        expected = '''"<word>"
\t"word" N SG
'''
        self.assertEqual(res.strip(), expected.strip())

    # -- the order vislcg3 keeps readings in --------------------------------------------------------------
    UNIF = '''
        DELIMITERS = "<$.>" ;
        LIST Pcle = Pcle ;
        LIST N = N ;
        LIST X = X ;
        LIST Case = (N Sg) (N Pl) ;
        SECTION
        REMOVE (X) ;
        REMOVE Pcle IF (-1 $$Case) (0 ("ды")) (1 N + $$Case) ;
    '''
    PCLE = '"<ды>"\n\t"ды" CC\n\t"ды" Pcle\n"<r>"\n\t"r" N Sg\n'

    def _pcle_removed(self, left_readings):
        text = '"<l>"\n' + ''.join('\t"l" %s\n' % r for r in left_readings) + self.PCLE
        res = Disambiguator(GrammarParser().parse(self.UNIF)).run_text(text)
        return '"ды" Pcle' not in res

    def test_removal_fills_the_gap_with_the_last_reading(self):
        # $$Case binds to the first reading that matches. vislcg3 does not close up the list when it removes
        # a reading but moves the last one into the gap, so after REMOVE (X) the Sg reading comes first
        self.assertTrue(self._pcle_removed(['N Pl X', 'N Pl', 'N Sg']))
        self.assertFalse(self._pcle_removed(['N Pl', 'N Sg']))             # nothing removed: Pl comes first
        self.assertFalse(self._pcle_removed(['N Pl X', 'N Pl', 'N Sg', 'N Pl Y']))   # the last one is a Pl

    def test_readings_are_printed_in_their_original_order(self):
        grammar = GrammarParser().parse('DELIMITERS = "<$.>" ;\nLIST X = X ;\nSECTION\nREMOVE (X) ;\n')
        text = '"<w>"\n\t"w" A X\n\t"w" B\n\t"w" C\n'
        res = Disambiguator(grammar).run_text(text)
        self.assertEqual(res.strip().split('\n'), ['"<w>"', '\t"w" B', '\t"w" C'])

    # -- regex tags, as vislcg3 reads them -------------------------------------------------------------------
    def _hits(self, grammar_text, input_text):
        res = Disambiguator(GrammarParser().parse(grammar_text)).run_text(input_text)
        return [ln for ln in res.split('\n') if 'HIT' in ln]

    def test_quoted_regex_matches_the_whole_form(self):
        text = '"<banana>"\n\t"banana" N <W:0.0>\n'
        def hit(tag):
            g = 'DELIMITERS = "<$.>" ;\nSECTION\nADD (HIT) TARGET (%s) ;\n' % tag
            return bool(self._hits(g, text))
        self.assertFalse(hit('"ban"r'))             # base form regex: the whole base form, not a part of it
        self.assertTrue(hit('"ban.*"r'))
        self.assertFalse(hit('"<ban>"r'))           # word form regex: the whole word form
        self.assertTrue(hit('"<.*nan.*>"r'))

    def test_wordform_regex_does_not_look_at_other_tags(self):
        # <W:0.0> begins with a capital, but "<\\p{Lu}.*>"r is a word form regex: only the word form is tried
        g = 'DELIMITERS = "<$.>" ;\nLIST UP = "<\\\\p{Lu}(.*)>"r ;\nSECTION\nADD (HIT) TARGET UP ;\n'
        text = '"<Turku>"\n\t"Turku" N <W:0.0>\n"<talo>"\n\t"talo" N <W:0.0>\n'
        res = Disambiguator(GrammarParser().parse(g)).run_text(text).split('\n')
        self.assertIn('\t"Turku" N <W:0.0> HIT', res)
        self.assertIn('\t"talo" N <W:0.0>', res)

    def test_slash_regex_looks_anywhere_in_the_tag(self):
        g = 'DELIMITERS = "<$.>" ;\nSECTION\nADD (HIT) TARGET (/Fo/r) ;\n'
        self.assertTrue(self._hits(g, '"<a>"\n\t"a" N Foo\n'))

    def test_addcohort_needs_its_target(self):
        g = 'DELIMITERS = "<$.>" ;\nLIST T = T ;\nSECTION\nADDCOHORT ("<x>" "x" N) AFTER T ;\n'
        res = Disambiguator(GrammarParser().parse(g)).run_text('"<a>"\n\t"a" U\n"<b>"\n\t"b" U\n')
        self.assertNotIn('"<x>"', res)              # no cohort has T: nothing is added (and nothing runs away)
        res = Disambiguator(GrammarParser().parse(g.replace('AFTER T', 'AFTER T (NEGATE 1 ("x"))'))).run_text('"<a>"\n\t"a" T\n"<b>"\n\t"b" U\n')
        self.assertEqual(res.count('"<x>"'), 1)


if __name__ == '__main__':
    unittest.main()
