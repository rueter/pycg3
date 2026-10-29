import unittest
from pycg3.tag import TagPattern, is_wordform, is_baseform, extract_form


class TestTag(unittest.TestCase):
    def test_wordform_baseform(self):
        self.assertTrue(is_wordform('"<word>"'))
        self.assertFalse(is_wordform('"word"'))
        self.assertFalse(is_wordform('N'))

        self.assertTrue(is_baseform('"word"'))
        self.assertFalse(is_baseform('"<word>"'))
        self.assertFalse(is_baseform('N'))

        self.assertEqual(extract_form('"<apple>"'), 'apple')
        self.assertEqual(extract_form('"apple"'), 'apple')
        self.assertEqual(extract_form('N'), 'N')

    def test_literal_matching(self):
        pat = TagPattern("wanted")
        self.assertTrue(pat.matches_tag("wanted"))
        self.assertFalse(pat.matches_tag("notwanted"))

    def test_regex_matching(self):
        pat = TagPattern('".atc[hm]{2}.*"r')
        self.assertTrue(pat.matches_tag('"matchme"'))
        self.assertTrue(pat.matches_tag('"catchhim"'))
        self.assertFalse(pat.matches_tag('"dog"'))

    def test_case_insensitive_matching(self):
        pat = TagPattern('"MaTcHmE"i')
        self.assertTrue(pat.matches_tag('"matchme"'))
        self.assertTrue(pat.matches_tag('"MATCHME"'))
        self.assertFalse(pat.matches_tag('"other"'))

    def test_slash_regex(self):
        pat = TagPattern('/^@.*-SAM/ri')
        self.assertTrue(pat.matches_tag('@BASEFORM-SAME'))
        self.assertFalse(pat.matches_tag('@OTHER'))


if __name__ == '__main__':
    unittest.main()
