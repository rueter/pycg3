"""pycg3 - A pure Python implementation of VISL CG-3 (Constraint Grammar 3)."""

__version__ = "0.2.0"

from pycg3.tag import TagPattern, is_wordform, is_baseform
from pycg3.cohort import Cohort, Reading, SingleWindow
from pycg3.set_def import SetDefinition, CompositeTag
from pycg3.context import ContextualTest
from pycg3.rule import Rule
from pycg3.grammar import Grammar, GrammarParser
from pycg3.stream import parse_stream
from pycg3.engine import Disambiguator
from pycg3.pipeline import Cg, CgWord, analyses_to_cg, analysis_to_cg, mark_ex_pos
from pycg3.languages import LanguageData, available_languages, get_language, register_language, tokenise

__all__ = [
    "__version__",
    "TagPattern",
    "is_wordform",
    "is_baseform",
    "Cohort",
    "Reading",
    "SingleWindow",
    "SetDefinition",
    "CompositeTag",
    "ContextualTest",
    "Rule",
    "Grammar",
    "GrammarParser",
    "parse_stream",
    "Disambiguator",
    "Cg",
    "CgWord",
    "analyses_to_cg",
    "analysis_to_cg",
    "mark_ex_pos",
    "LanguageData",
    "available_languages",
    "get_language",
    "register_language",
    "tokenise",
]
