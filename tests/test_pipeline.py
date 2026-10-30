import json
import os
import tempfile
import unittest

import pycg3
from pycg3 import Cg, CgWord, analyses_to_cg, analysis_to_cg, mark_ex_pos
from pycg3.languages import LanguageData, available_languages, get_language, register_language

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
# what pyhfst gives for "Мон кортан": [[analysis, weight], ...] for each word
MORPH = [[["мон+Pron+Pers+Sg1+Nom", 0.0]],
         [["кортан+N+Sg+Nom+Indef", 0.0], ["кортамс+V+Ind+Prs+ScSg1", 0.0], ["кортамс+V+Ind+Prs+ScSg1", 0.0]]]


class TestAnalysesToCg(unittest.TestCase):
    def test_one_analysis(self):
        self.assertEqual(analysis_to_cg("кортамс+V+Ind+Prs+ScSg1", 0.0), ['\t"кортамс" V Ind Prs ScSg1 <W:0.0>'])
        self.assertEqual(analysis_to_cg("мон+Pron", 2), ['\t"мон" Pron <W:2.0>'])

    def test_compound_becomes_subreading(self):
        lines = analysis_to_cg("тар+N+Sg+Nom+Cmp#кав+N+Sg+Nom+Indef", 0.0)
        self.assertEqual(lines, ['\t"кав" N Sg Nom Indef <W:0.0>', '\t\t"тар" N Sg Nom Cmp'])

    def test_variant_tags_dropped_unless_asked(self):
        self.assertEqual(analysis_to_cg("течи+v1+N", 0.0), ['\t"течи" N <W:0.0>'])
        self.assertEqual(analysis_to_cg("течи+v1+N", 0.0, drop_variants=False), ['\t"течи" v1 N <W:0.0>'])

    def test_ex_pos(self):
        self.assertEqual(mark_ex_pos(["V", "Der/NomAct", "N", "Sg"]), ["Ex/V", "Der/NomAct", "N", "Sg"])
        self.assertEqual(mark_ex_pos(["V", "Der/OvOms", "V", "Der/NomAct", "N"]), ["Ex/V", "Der/OvOms", "Ex/V", "Der/NomAct", "N"])
        self.assertEqual(mark_ex_pos(["V", "Ind", "Prs"]), ["V", "Ind", "Prs"])
        self.assertEqual(mark_ex_pos(["Po", "Der/MWN", "Sg"]), ["Po", "Der/MWN", "Sg"])      # no later POS
        self.assertEqual(analysis_to_cg("молемс+V+Der/NomAct+N+Sg", 0.0, ex_pos=True), ['\t"молемс" Ex/V Der/NomAct N Sg <W:0.0>'])

    def test_stream_with_unknown_word_and_duplicates(self):
        text = analyses_to_cg(["Мон", "кортан", "xyzzy"], MORPH + [[]])
        self.assertEqual(text.count('"<'), 3)
        self.assertEqual(text.count("кортамс"), 1)                  # the double analysis is one reading
        self.assertTrue(text.rstrip().endswith('\t"xyzzy" ?'))


class TestCg(unittest.TestCase):
    def test_disambiguate_returns_words_with_readings(self):
        cg = Cg([GRAMMAR])
        result = cg.disambiguate(["Мон", "кортан"], MORPH)
        self.assertEqual([form for form, _ in result], ["Мон", "кортан"])
        readings = result[1][1]
        self.assertEqual(len(readings), 1)
        w = readings[0]
        self.assertIsInstance(w, CgWord)
        self.assertEqual((w.form, w.lemma), ("кортан", "кортамс"))
        self.assertEqual(w.morphology, ["V", "Ind", "Prs", "ScSg1", "<W:0.0>"])      # like UralicNLP's Cg3Word
        self.assertEqual(w.tags, ["V", "Ind", "Prs", "ScSg1"])
        self.assertEqual(w.weight, 0.0)
        self.assertEqual(w.analysis(), ["кортамс+V+Ind+Prs+ScSg1", 0.0])           # back to pyhfst's shape
        self.assertEqual(cg.to_morphologies(result)[1], [["кортамс+V+Ind+Prs+ScSg1", 0.0]])

    def test_grammars_run_in_a_chain(self):
        cg = Cg([GRAMMAR, MAPPER], names=["disambiguator", "functions"])
        result = cg.disambiguate(["Мон", "кортан"], MORPH)
        self.assertEqual(result[1][1][0].tags, ["V", "Ind", "Prs", "ScSg1", "@FMV"])
        self.assertEqual(Cg([MAPPER, GRAMMAR]).disambiguate(["Мон", "кортан"], MORPH)[1][1][0].tags[-1], "@FMV")

    def test_empty_words_are_ignored_with_their_analyses(self):
        cg = Cg([GRAMMAR])
        result = cg.disambiguate(["Мон", "кортан", ""], MORPH + [[]])      # UralicNLP ends a sentence with ""
        self.assertEqual([f for f, _ in result], ["Мон", "кортан"])

    def test_trace(self):
        result = Cg([GRAMMAR], trace=True).disambiguate(["Мон", "кортан"], MORPH)
        self.assertTrue(result[1][1][0].trace[0].startswith("SELECT:"))

    def test_compound_subreadings(self):
        cg = Cg(["DELIMITERS = \"<.>\" ;\nSECTION\nSELECT (N) ;\n"])
        result = cg.disambiguate(["таркав"], [[["тар+N+Cmp#кав+N+Sg", 0.0], ["тарка+N+SP+Lat", 0.0]]])
        w = result[0][1][0]
        self.assertEqual(w.lemma, "кав")
        self.assertEqual([(s.lemma, s.tags) for s in w.sub_readings], [("тар", ["N", "Cmp"])])

    def test_needs_morphologies_without_a_language(self):
        with self.assertRaises(ValueError):
            Cg([GRAMMAR]).disambiguate(["Мон"])

    def test_from_files(self):
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("disambiguator.cg3", GRAMMAR), ("functions.cg3", MAPPER)):
                with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
                    fh.write(text)
            cg = Cg.from_files(os.path.join(d, "disambiguator.cg3"), os.path.join(d, "functions.cg3"))
            self.assertEqual(cg.names, ["disambiguator", "functions"])
            self.assertEqual(cg.disambiguate(["Мон", "кортан"], MORPH)[1][1][0].tags[-1], "@FMV")


class TestLanguages(unittest.TestCase):
    def make_dir(self, base, code="xx", stages=("disambiguator", "functions")):
        root = os.path.join(base, code)
        os.makedirs(root)
        for stage, text in (("disambiguator", GRAMMAR), ("functions", MAPPER)):
            if stage in stages:
                with open(os.path.join(root, stage + ".cg3"), "w", encoding="utf-8") as fh:
                    fh.write(text)
        with open(os.path.join(root, "metadata.json"), "w", encoding="utf-8") as fh:
            json.dump({"language": code, "stages": list(stages)}, fh)
        return root

    def test_register_and_use(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.make_dir(d)
            lang = register_language("xx", root)
            self.assertIs(get_language("xx"), lang)
            self.assertEqual(list(lang.stages), ["disambiguator", "functions"])
            self.assertIn("xx", available_languages())
            cg = Cg.for_language("xx")
            self.assertEqual(cg.names, ["disambiguator", "functions"])
            self.assertEqual(cg.disambiguate(["Мон", "кортан"], MORPH)[1][1][0].tags[-1], "@FMV")
            only = Cg.for_language("xx", stages=["disambiguator"])
            self.assertEqual(only.disambiguate(["Мон", "кортан"], MORPH)[1][1][0].tags[-1], "ScSg1")
            with self.assertRaises(KeyError):
                Cg.for_language("xx", stages=["dependency"])

    def test_environment_directory(self):
        with tempfile.TemporaryDirectory() as d:
            self.make_dir(d, "yy", stages=("disambiguator",))
            old = os.environ.get("PYCG3_DATA")
            os.environ["PYCG3_DATA"] = d
            try:
                self.assertIn("yy", available_languages())
                self.assertEqual(list(get_language("yy").stages), ["disambiguator"])
            finally:
                if old is None:
                    del os.environ["PYCG3_DATA"]
                else:
                    os.environ["PYCG3_DATA"] = old

    def test_unknown_language_says_what_to_install(self):
        with self.assertRaisesRegex(LookupError, "pycg3-lang-zzz"):
            get_language("zzz")

    def test_stage_listed_but_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.make_dir(d, "ww", stages=("disambiguator",))
            with open(os.path.join(root, "metadata.json"), "w", encoding="utf-8") as fh:
                json.dump({"language": "ww", "stages": ["disambiguator", "functions"]}, fh)
            with self.assertRaises(FileNotFoundError):
                LanguageData.from_directory(root)

    def test_tokenise(self):
        self.assertEqual(pycg3.tokenise("Течи кортатано, ули-паро."), ["Течи", "кортатано", ",", "ули-паро", "."])


if __name__ == "__main__":
    unittest.main()
