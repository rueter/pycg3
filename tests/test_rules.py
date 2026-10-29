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


if __name__ == '__main__':
    unittest.main()
