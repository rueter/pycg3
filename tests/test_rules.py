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


if __name__ == '__main__':
    unittest.main()
