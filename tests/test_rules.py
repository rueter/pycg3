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

    # -- sub-readings, weights and mapping tags, as vislcg3 does them -----------------------------------------
    COMPOUND = (
        '"<w>"\n'
        '\t"head" N top1 <W:0.0>\n'
        '\t\t"p1" N s1 <W:0.0>\n'
        '\t\t\t"p2" N s2 <W:0.0>\n'
        '\t"whole" N whole <W:0.0>\n'
    )
    SUBHEAD = 'DELIMITERS = "<$.>" ;\nSUBREADINGS = LTR ;\nLIST N = N ;\nLIST s1 = s1 ;\nLIST s2 = s2 ;\nSECTION\n'

    def _run(self, grammar_text, input_text):
        return Disambiguator(GrammarParser().parse(grammar_text), trace=True).run_text(input_text)

    def test_sub_n_target_matches_the_nth_sub_reading(self):
        res = self._run(self.SUBHEAD + 'REMOVE SUB:2 (s2) ;\n', self.COMPOUND)
        self.assertNotIn('"head"', res)             # the whole reading goes when its sub-reading 2 has s2
        self.assertIn('"whole"', res)
        res = self._run(self.SUBHEAD + 'REMOVE SUB:2 (s1) ;\n', self.COMPOUND)
        self.assertIn('"head"', res)                # sub-reading 2 is not s1: nothing is removed
        res = self._run(self.SUBHEAD + 'REMOVE SUB:-1 (s2) ;\n', self.COMPOUND)
        self.assertNotIn('"head"', res)             # -1 is the last sub-reading

    def test_context_slash_n_looks_at_the_nth_sub_reading(self):
        def hit(pos, tag):
            g = self.SUBHEAD + 'ADD (HIT) (whole) IF (%s %s) ;\n' % (pos, tag)
            return 'HIT' in self._run(g, self.COMPOUND)
        self.assertTrue(hit('0/1', 's1'))
        self.assertTrue(hit('0/2', 's2'))
        self.assertTrue(hit('0/-1', 's2'))
        self.assertFalse(hit('0/1', 's2'))
        self.assertFalse(hit('0/3', 's2'))

    def test_weight_tags_compare_by_number(self):
        g = 'DELIMITERS = "<$.>" ;\nLIST W0 = <W:0> ;\nSECTION\nADD (HIT) W0 ;\n'
        res = self._run(g, '"<a>"\n\t"a" N <W:0.0>\n"<b>"\n\t"b" N <W:2.0>\n')
        self.assertIn('"a" N <W:0.0> HIT', res)
        self.assertNotIn('"b" N <W:2.0> HIT', res)

    def test_tags_added_by_a_rule_come_in_vislcg3_order(self):
        g = 'DELIMITERS = "<$.>" ;\nLIST CC = CC ;\nSECTION\nMAP (@P Q @R) TARGET CC ;\n'
        res = self._run(g, '"<a>"\n\t"a" CC\n"<b>"\n\t"b" N\n')
        self.assertIn('"a" CC Q @R @P', res)        # the plain tags, then the mapping tags with the last one first

    def test_a_reading_with_two_mapping_tags_is_split_when_a_rule_targets_one(self):
        head = 'DELIMITERS = "<$.>" ;\nLIST CC = CC ;\nLIST CNP = @CNP ;\nSECTION\nMAP (@CNP @CVP) TARGET CC ;\n'
        inp = '"<a>"\n\t"a" CC\n"<b>"\n\t"b" N\n'
        res = self._run(head + 'REMOVE CNP ;\n', inp)
        self.assertIn('"a" CC @CVP', res)
        self.assertNotIn('@CVP @CNP', res)
        res = self._run(head + 'REMOVE (@X) ;\n', inp)         # a target that matches no mapping tag leaves them together
        self.assertIn('"a" CC @CVP @CNP', res)

    def test_backslash_in_a_plain_tag_means_the_next_character(self):
        # GiellaLT writes LIST WORD = N V \? ; and \# \; \( \) for tags that are special in a grammar file
        g = 'DELIMITERS = "<$.>" ;\nLIST W = N \\? \\# \\( \\; ;\nSECTION\nADD (HIT) W ;\n'
        res = self._run(g, '"<a>"\n\t"a" ?\n"<b>"\n\t"b" #\n"<c>"\n\t"c" (\n"<d>"\n\t"d" ;\n"<e>"\n\t"e" V\n')
        for word, tag in (('a', '?'), ('b', '#'), ('c', '('), ('d', ';')):
            self.assertIn('"%s" %s HIT' % (word, tag), res)
        self.assertNotIn('"e" V HIT', res)

    def test_backslash_in_a_regex_is_left_for_the_regex(self):
        g = 'DELIMITERS = "<$.>" ;\nLIST R = /^a\\.b$/r ;\nSECTION\nADD (HIT) R ;\n'
        res = self._run(g, '"<a>"\n\t"x" a.b\n"<b>"\n\t"y" aXb\n')
        self.assertIn('"x" a.b HIT', res)
        self.assertNotIn('HIT', res.split('"<b>"')[1])

    def test_copy_except_leaves_tags_out_of_the_copy_and_keeps_its_own_target(self):
        # COPY (tags) EXCEPT set TARGET set: the copy lacks the EXCEPT tags, and only the TARGET readings are copied
        g = 'DELIMITERS = "<$.>" ;\nLIST Adv = Adv ;\nLIST N = N ;\nLIST ADR = Sem/Adr ;\nSECTION\n' \
            'COPY:c (Nom) EXCEPT Adv TARGET ADR ;\nCOPY:d (Gen) EXCEPT Adv TARGET N ;\n'
        res = self._run(g, '"<a>"\n\t"a" N Sg Adv\n\t"a" V Sem/Adr Sg\n"<b>"\n\t"b" V Sg\n')
        lines = [l.strip() for l in res.splitlines()]
        self.assertIn('"a" N Sg Adv', lines)
        self.assertIn('"a" N Sg Gen', lines)           # copied without Adv
        self.assertIn('"a" V Sem/Adr Sg Nom', lines)    # only the Sem/Adr reading got the Nom copy
        self.assertEqual(sum('Nom' in l for l in lines), 1)
        self.assertEqual(len([l for l in lines if l.startswith('"b"')]), 1)

    def test_context_slash_star_looks_at_the_reading_and_all_its_sub_readings(self):
        # checked against vislcg3 1.7.0: 0/* is true if any reading of the cohort has the tag on itself or any sub-reading
        g = 'DELIMITERS = "<$.>" ;\nSUBREADINGS = LTR ;\nLIST ATTR = Cmp/Attr ;\nLIST NOM = Cmp/SgNom ;\nSECTION\n' \
            'REMOVE SUB:1 NOM (0/* ATTR) ;\n'
        inp = ('"<x>"\n\t"h" N Sg Nom Cmp/Attr\n\t\t"p" N Cmp/SgNom\n\t"h" N Sg Gen\n\t\t"p" N Cmp/SgNom\n'
               '\t"h" N Sg Ill\n\t\t"p" N Cmp/Other\n')
        res = self._run(g, inp)
        self.assertIn('"h" N Sg Ill', res)
        self.assertNotIn('Sg Nom', res)
        self.assertNotIn('Sg Gen', res)


if __name__ == '__main__':
    unittest.main()
