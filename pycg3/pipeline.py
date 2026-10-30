"""The library entry point: analyses in the shape pyhfst gives, what the Constraint Grammars make of them out.

    from pycg3 import Cg
    cg = Cg.for_language("myv")                      # or Cg.from_files("disambiguator.cg3", "functions.cg3")
    result = cg.disambiguate(["Течи", "кортатано"], morphologies)   # morphologies as pyhfst's lookup gives them
    result[0]   ->  ("Течи", [CgWord, CgWord, ...])

`morphologies` has one entry per word, each a list of [analysis, weight] pairs, e.g.
    [[["течи+N+Sg+Nom+Indef", 0.0], ["течи+Adv", 0.0]], [["кортамс+V+Ind+Prs+ScPl1", 0.0]]]
Several grammars run one after the other, each taking the previous one's output, like `vislcg3 -g a | vislcg3 -g b`.
"""

import io
import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union

from pycg3.engine import Disambiguator
from pycg3.grammar import Grammar, GrammarParser

# Main parts of speech. A POS followed by a Der/... tag and later by another POS becomes Ex/POS, if the analyser
# did not do that itself (analyser-disamb-gt-desc.hfstol does; analyser-gt-desc.hfstol does not).
POS_TAGS = frozenset({"N", "V", "A", "Adv", "Pron", "Num", "Po", "Pr", "CC", "CS", "Pcle", "Interj", "Det"})
_VARIANT = re.compile(r"^v\d+$")                 # +v1: a variant mark of some analysers, not a tag of the grammars
_WEIGHT = re.compile(r"^<W:([-+0-9.eE]+)>$")


def mark_ex_pos(tags: Sequence[str]) -> List[str]:
    """V Der/NomAct N  ->  Ex/V Der/NomAct N"""
    out = list(tags)
    for i, tag in enumerate(out):
        if tag in POS_TAGS:
            rest = out[i + 1:]
            d = next((k for k, x in enumerate(rest) if x.startswith("Der/")), None)
            if d is not None and any(x in POS_TAGS for x in rest[d + 1:]):
                out[i] = "Ex/" + tag
    return out


def analysis_to_cg(analysis: str, weight: float = 0.0, drop_variants: bool = True, ex_pos: bool = False) -> List[str]:
    """One analysis string as the lines of a CG reading. A compound (parts joined by #) becomes a reading for the last
    part with the earlier parts as sub-readings, each one tab deeper, as hfst-tokenise -g writes it."""
    parts = []
    for part in analysis.split("#"):
        lemma, *tags = part.split("+")
        if drop_variants:
            tags = [t for t in tags if not _VARIANT.match(t)]
        if ex_pos:
            tags = mark_ex_pos(tags)
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
                 trace: bool = False, language: Any = None):
        """grammars: parsed Grammar objects or grammar texts. names label the stages."""
        parsed = [g if isinstance(g, Grammar) else GrammarParser().parse(g) for g in grammars]
        self.names = list(names) if names else ["stage%d" % (i + 1) for i in range(len(parsed))]
        self.trace = trace
        self.language = language
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

    @classmethod
    def for_language(cls, code: str, stages: Optional[Sequence[str]] = None, **kwargs) -> "Cg":
        """The grammars of an installed language package (pycg3-lang-CODE), or of a registered directory."""
        from pycg3.languages import get_language
        lang = get_language(code)
        chosen = list(stages) if stages else list(lang.stages)
        missing = [s for s in chosen if s not in lang.stages]
        if missing:
            raise KeyError("%s has no stage %s (it has %s)" % (code, ", ".join(missing), ", ".join(lang.stages)))
        texts = [lang.grammar_text(s) for s in chosen]
        return cls(texts, names=chosen, language=lang, **kwargs)

    # -- running ----------------------------------------------------------------------------------------------
    def run_text(self, cg_input: str) -> str:
        """A CG stream through all the grammars; the stream out."""
        text = cg_input
        for number, engine in enumerate(self._engines):
            last = number == len(self._engines) - 1
            text = "".join(w.to_text(trace=self.trace and last, pipe_deleted=False) + "\n"
                           for w in engine.run_stream(io.StringIO(text)))
        return text

    def disambiguate(self, words: Sequence[str], morphologies: Optional[Sequence[Sequence[Sequence[Any]]]] = None,
                     **options) -> List[Tuple[str, List[CgWord]]]:
        """[(word, [CgWord, ...]), ...] for the words, in order. Without morphologies the language package's
        analyser is asked (needs pyhfst). options go to analysis_to_cg (drop_variants, ex_pos)."""
        if morphologies is None:
            if self.language is None:
                raise ValueError("morphologies are needed when the grammars do not come from a language package")
            words = [w for w in words if w]
            morphologies = self.language.analyse(words)
        else:
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

    def analyse_and_disambiguate(self, text: str, **options) -> List[Tuple[str, List[CgWord]]]:
        """Tokenise text, analyse it with the language package's FST, run the grammars."""
        if self.language is None:
            raise ValueError("this Cg has no language package; give disambiguate() the morphologies")
        return self.disambiguate(self.language.tokenise(text), None, **options)

    def to_morphologies(self, result: Iterable[Tuple[str, List[CgWord]]]) -> List[List[List[Any]]]:
        """A result as pyhfst-shaped analyses again."""
        return [[w.analysis() for w in readings] for _form, readings in result]
