"""The library entry point: analyses in the shape pyhfst gives, what the Constraint Grammars make of them out.

    from pycg3 import Cg
    cg = Cg.from_files("disambiguator.cg3", "functions.cg3")      # grammar files you provide
    result = cg.disambiguate(["Time", "flies"], morphologies)       # morphologies as pyhfst's lookup gives them
    result[0]   ->  ("Time", [CgWord, CgWord, ...])

`morphologies` has one entry per word, each a list of [analysis, weight] pairs, e.g.
    [[["time+N+Sg", 0.0], ["time+V+Inf", 0.0]], [["fly+V+Prs+Sg3", 0.0], ["fly+N+Pl", 0.0]]]
pycg3 knows no language: the analyser and the grammars are yours. Several grammars run one after the other, each taking the previous one's output, like `vislcg3 -g a | vislcg3 -g b`.
"""

import io
import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

from pycg3.engine import Disambiguator
from pycg3.grammar import Grammar, GrammarParser

_VARIANT = re.compile(r"^v\d+$")                 # +v1: a variant mark of some analysers, not a tag of the grammars
_WEIGHT = re.compile(r"^<W:([-+0-9.eE]+)>$")


def analysis_to_cg(analysis: str, weight: float = 0.0, drop_variants: bool = True) -> List[str]:
    """One analysis string as the lines of a CG reading. A compound (parts joined by #) becomes a reading for the last
    part with the earlier parts as sub-readings, each one tab deeper, as hfst-tokenise -g writes it."""
    parts = []
    for part in analysis.split("#"):
        lemma, *tags = part.split("+")
        if drop_variants:
            tags = [t for t in tags if not _VARIANT.match(t)]
        parts.append((lemma, tags))
    lines = []
    for depth, (lemma, tags) in enumerate(reversed(parts), start=1):
        w = " <W:%s>" % float(weight) if depth == 1 else ""
        lines.append("\t" * depth + '"%s"%s%s' % (lemma, (" " + " ".join(tags)) if tags else "", w))
    return lines


def analyses_to_cg(words: Sequence[str], morphologies: Sequence[Sequence[Sequence[Any]]], **options) -> str:
    """The CG input stream for words and their pyhfst analyses. A word without analyses is unknown: "w" ?"""
    out: List[str] = []
    for index, word in enumerate(words):
        if not word:
            continue
        analyses = morphologies[index] if index < len(morphologies) else []
        out.append('"<%s>"' % word)
        seen = set()
        for item in analyses:
            analysis, weight = item[0], (item[1] if len(item) > 1 else 0.0)
            if analysis in seen:
                continue
            seen.add(analysis)
            out.extend(analysis_to_cg(analysis, weight, **options))
        if not seen:
            out.append('\t"%s" ?' % word)
    return "\n".join(out) + "\n"


class CgWord:
    """One reading of one word as a grammar leaves it. Same attributes as UralicNLP's Cg3Word (form, lemma, morphology)
    plus the pieces: tags (without the weight tag), weight, sub_readings (compound parts) and trace (with trace=True)."""

    __slots__ = ("form", "lemma", "morphology", "tags", "weight", "sub_readings", "trace")

    def __init__(self, form: str, lemma: str, morphology: List[str], sub_readings: Optional[List["CgWord"]] = None,
                 trace: Optional[List[str]] = None):
        self.form = form
        self.lemma = lemma
        self.morphology = morphology                       # all tags, as written, the <W:..> tag included
        self.tags = [t for t in morphology if not _WEIGHT.match(t)]
        weights = [_WEIGHT.match(t) for t in morphology]
        self.weight = float(next((m.group(1) for m in weights if m), 0.0))
        self.sub_readings = sub_readings or []
        self.trace = trace or []

    def analysis(self) -> List[Any]:
        """Back to the shape pyhfst gives: ["lemma+Tag+Tag", weight]; the next tool can take it from there."""
        return [self.lemma + "".join("+" + t for t in self.tags), self.weight]

    def __repr__(self) -> str:
        return "<" + self.lemma + " - " + ", ".join(self.morphology) + ">"


def _reading_to_word(form: str, reading, keep_trace: bool) -> CgWord:
    subs = [_reading_to_word(form, sub, keep_trace) for sub in reading.sub_readings]
    return CgWord(form, reading.baseform.strip('"'), list(reading.tags), subs, list(reading.trace) if keep_trace else None)


class Cg:
    """A chain of Constraint Grammars (disambiguator, then functions, then dependency, ...)."""

    def __init__(self, grammars: Sequence[Union[Grammar, str]], names: Optional[Sequence[str]] = None,
                 trace: bool = False):
        """grammars: parsed Grammar objects or grammar texts. names label the stages."""
        parsed = [g if isinstance(g, Grammar) else GrammarParser().parse(g) for g in grammars]
        self.names = list(names) if names else ["stage%d" % (i + 1) for i in range(len(parsed))]
        self.trace = trace
        self._engines = [Disambiguator(g, trace=(trace and i == len(parsed) - 1)) for i, g in enumerate(parsed)]

    # -- constructors ---------------------------------------------------------------------------------------
    @classmethod
    def from_files(cls, *paths: str, **kwargs) -> "Cg":
        """Grammar files, run in the order given."""
        texts = []
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                texts.append(fh.read())
        names = kwargs.pop("names", None) or [re.sub(r"\.cg3$", "", str(p).split("/")[-1]) for p in paths]
        return cls(texts, names=names, **kwargs)

    # -- running ----------------------------------------------------------------------------------------------
    def run_text(self, cg_input: str) -> str:
        """A CG stream through all the grammars; the stream out."""
        text = cg_input
        for number, engine in enumerate(self._engines):
            last = number == len(self._engines) - 1
            text = "".join(w.to_text(trace=self.trace and last, pipe_deleted=False) + "\n"
                           for w in engine.run_stream(io.StringIO(text)))
        return text

    def disambiguate(self, words: Sequence[str], morphologies: Sequence[Sequence[Sequence[Any]]], **options) -> List[Tuple[str, List[CgWord]]]:
        """[(word, [CgWord, ...]), ...] for the words, in order. morphologies: one list of [analysis, weight] pairs
        per word, as pyhfst's lookup gives them. options go to analysis_to_cg (drop_variants)."""
        # empty words (UralicNLP ends a sentence with one) carry no cohort; drop them with their analyses
        kept = [(w, morphologies[i] if i < len(morphologies) else []) for i, w in enumerate(words) if w]
        words = [w for w, _ in kept]
        morphologies = [m for _, m in kept]
        engines = self._engines
        text = analyses_to_cg(words, morphologies, **options)
        for engine in engines[:-1]:
            text = "".join(w.to_text(pipe_deleted=False) + "\n" for w in engine.run_stream(io.StringIO(text)))
        out: List[Tuple[str, List[CgWord]]] = []
        for window in engines[-1].run_stream(io.StringIO(text)):
            for cohort in window.cohorts:
                form = cohort.wordform[2:-2]
                out.append((form, [_reading_to_word(form, r, self.trace) for r in cohort.readings if not r.deleted]))
        return out

    def to_morphologies(self, result: Iterable[Tuple[str, List[CgWord]]]) -> List[List[List[Any]]]:
        """A result as pyhfst-shaped analyses again."""
        return [[w.analysis() for w in readings] for _form, readings in result]
