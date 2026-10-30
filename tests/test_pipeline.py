import json
import os
import tempfile
import unittest

import pycg3
from pycg3 import Cg, CgWord, analyses_to_cg, analysis_to_cg

GRAMMAR = '''
DELIMITERS = "<.>" ;
LIST BOS = (>>>) ;
SECTION
SELECT (V) IF (-1 (Pron)) ;
'''
MAPPER = '''
DELIMITERS = "<.>" ;
SECTION
MAP (@FMV) TARGET (V) ;
'''
# what pyhfst gives for "I talk": [[analysis, weight], ...] for each word
MORPH = [[["i+Pron+Pers+Sg1+Nom", 0.0]],
         [["talk+N+Sg+Nom+Indef", 0.0], ["talk+V+Ind+Prs+ScSg1", 0.0], ["talk+V+Ind+Prs+ScSg1", 0.0]]]


class TestAnalysesToCg(unittest.TestCase):
    def test_one_analysis(self):
        self.assertEqual(analysis_to_cg("talk+V+Ind+Prs+ScSg1", 0.0), ['\t"talk" V Ind Prs ScSg1 <W:0.0>'])
        self.assertEqual(analysis_to_cg("i+Pron", 2), ['\t"i" Pron <W:2.0>'])

    def test_compound_becomes_subreading(self):
        lines = analysis_to_cg("car+N+Sg+Nom+Cmp#pet+N+Sg+Nom+Indef", 0.0)
        self.assertEqual(lines, ['\t"pet" N Sg Nom Indef <W:0.0>', '\t\t"car" N Sg Nom Cmp'])

    def test_variant_tags_dropped_unless_asked(self):
        self.assertEqual(analysis_to_cg("now+v1+N", 0.0), ['\t"now" N <W:0.0>'])
        self.assertEqual(analysis_to_cg("now+v1+N", 0.0, drop_variants=False), ['\t"now" v1 N <W:0.0>'])

    def test_stream_with_unknown_word_and_duplicates(self):
        text = analyses_to_cg(["I", "talk", "xyzzy"], MORPH + [[]])
        self.assertEqual(text.count('"<'), 3)
        self.assertEqual(text.count('\t"talk" V'), 1)                  # the double analysis is one reading
        self.assertTrue(text.rstrip().endswith('\t"xyzzy" ?'))


class TestCg(unittest.TestCase):
    def test_disambiguate_returns_words_with_readings(self):
        cg = Cg([GRAMMAR])
        result = cg.disambiguate(["I", "talk"], MORPH)
        self.assertEqual([form for form, _ in result], ["I", "talk"])
        readings = result[1][1]
        self.assertEqual(len(readings), 1)
        w = readings[0]
        self.assertIsInstance(w, CgWord)
        self.assertEqual((w.form, w.lemma), ("talk", "talk"))
        self.assertEqual(w.morphology, ["V", "Ind", "Prs", "ScSg1", "<W:0.0>"])      # like UralicNLP's Cg3Word
        self.assertEqual(w.tags, ["V", "Ind", "Prs", "ScSg1"])
        self.assertEqual(w.weight, 0.0)
        self.assertEqual(w.analysis(), ["talk+V+Ind+Prs+ScSg1", 0.0])           # back to pyhfst's shape
        self.assertEqual(cg.to_morphologies(result)[1], [["talk+V+Ind+Prs+ScSg1", 0.0]])

    def test_grammars_run_in_a_chain(self):
        cg = Cg([GRAMMAR, MAPPER], names=["disambiguator", "functions"])
        result = cg.disambiguate(["I", "talk"], MORPH)
        self.assertEqual(result[1][1][0].tags, ["V", "Ind", "Prs", "ScSg1", "@FMV"])
        self.assertEqual(Cg([MAPPER, GRAMMAR]).disambiguate(["I", "talk"], MORPH)[1][1][0].tags[-1], "@FMV")

    def test_empty_words_are_ignored_with_their_analyses(self):
        cg = Cg([GRAMMAR])
        result = cg.disambiguate(["I", "talk", ""], MORPH + [[]])      # UralicNLP ends a sentence with ""
        self.assertEqual([f for f, _ in result], ["I", "talk"])

    def test_trace(self):
        result = Cg([GRAMMAR], trace=True).disambiguate(["I", "talk"], MORPH)
        self.assertTrue(result[1][1][0].trace[0].startswith("SELECT:"))

    def test_compound_subreadings(self):
        cg = Cg(["DELIMITERS = \"<.>\" ;\nSECTION\nSELECT (N) ;\n"])
        result = cg.disambiguate(["carpet"], [[["car+N+Cmp#pet+N+Sg", 0.0], ["carpet+N+SP+Lat", 0.0]]])
        w = result[0][1][0]
        self.assertEqual(w.lemma, "pet")
        self.assertEqual([(s.lemma, s.tags) for s in w.sub_readings], [("car", ["N", "Cmp"])])

    def test_from_files(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("disambiguator.cg3", GRAMMAR), ("functions.cg3", MAPPER)):
                with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                    fh.write(text)
            cg = Cg.from_files(os.path.join(d, "disambiguator.cg3"), os.path.join(d, "functions.cg3"))
            self.assertEqual(cg.names, ["disambiguator", "functions"])
            self.assertEqual(cg.disambiguate(["I", "talk"], MORPH)[1][1][0].tags[-1], "@FMV")


if __name__ == "__main__":
    unittest.main()
