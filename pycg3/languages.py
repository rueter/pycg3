"""Language packages: an FST and Constraint Grammars for one language, found by code.

A language is a directory

    analyser-disamb-gt-desc.hfstol      the analyser (optimized-lookup FST, read with pyhfst)
    disambiguator.cg3                   the grammars, as text
    functions.cg3  dependency.cg3       (when there are any)
    metadata.json                       {"language": "myv", "analyser": "...", "stages": ["disambiguator", ...], "source": {...}}

and is found, in this order, through

  1. register_language(code, directory)
  2. the directories listed in the environment variable PYCG3_DATA (os.pathsep-separated), each holding CODE/ directories
  3. installed packages that declare an entry point in the group "pycg3.languages" (pycg3-lang-CODE wheels do;
     tools/build_language_wheel.py makes them)
"""

import json
import os
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

ENTRY_POINT_GROUP = "pycg3.languages"
STAGE_ORDER = ("disambiguator", "functions", "dependency")
_TOKEN = re.compile(r"\w+(?:[-’'·]\w+)*|[^\w\s]", re.UNICODE)

_registry: Dict[str, "LanguageData"] = {}


def tokenise(text: str) -> List[str]:
    """Words (hyphenated words kept whole) and single punctuation marks. A simple stand-in for a real tokeniser."""
    return _TOKEN.findall(text)


class LanguageData:
    """The files of one language."""

    def __init__(self, code: str, root: Path, analyser: Optional[str], stages: Dict[str, str], metadata: Dict[str, Any]):
        self.code = code
        self.root = Path(root)
        self.analyser_file = analyser
        self.stages = stages                       # stage name -> file name, in running order
        self.metadata = metadata
        self._analyser = None
        self._lock = threading.Lock()

    @classmethod
    def from_directory(cls, root, code: Optional[str] = None) -> "LanguageData":
        root = Path(root)
        meta: Dict[str, Any] = {}
        if (root / "metadata.json").exists():
            meta = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        code = code or meta.get("language") or root.name
        names = meta.get("stages") or [s for s in STAGE_ORDER if (root / (s + ".cg3")).exists()]
        stages = {n: n + ".cg3" for n in names}
        for name, file in stages.items():
            if not (root / file).exists():
                raise FileNotFoundError("%s: stage %s lists %s, which is not in %s" % (code, name, file, root))
        analyser = meta.get("analyser")
        if analyser is None:
            found = sorted(root.glob("analyser*.hfstol"))
            analyser = found[0].name if found else None
        return cls(code, root, analyser, stages, meta)

    # -- the grammars ---------------------------------------------------------------------------------------------
    def grammar_path(self, stage: str) -> Path:
        return self.root / self.stages[stage]

    def grammar_text(self, stage: str) -> str:
        return self.grammar_path(stage).read_text(encoding="utf-8")

    # -- the FST --------------------------------------------------------------------------------------------------
    @property
    def analyser_path(self) -> Optional[Path]:
        return self.root / self.analyser_file if self.analyser_file else None

    @property
    def analyser(self):
        """The pyhfst transducer, loaded on first use."""
        if self._analyser is None:
            with self._lock:
                if self._analyser is None:
                    if not self.analyser_file:
                        raise FileNotFoundError("language %s has no analyser" % self.code)
                    try:
                        import pyhfst
                    except ImportError as exc:
                        raise ImportError("analysing needs pyhfst: pip install pycg3[hfst]") from exc
                    self._analyser = pyhfst.HfstInputStream(str(self.analyser_path)).read()
        return self._analyser

    def analyse(self, words: Sequence[str], sort: bool = True) -> List[List[List[Any]]]:
        """pyhfst's analyses for each word: [[analysis, weight], ...]. Doubles are dropped; with sort, the readings are
        in the alphabetical order of the analyses, which is the order hfst-tokenise gives them."""
        result = []
        for word in words:
            found: Dict[str, float] = {}
            for analysis, weight in self.analyser.lookup(word):
                found.setdefault(analysis, weight)
            items = sorted(found.items()) if sort else list(found.items())
            result.append([[a, w] for a, w in items])
        return result

    def tokenise(self, text: str) -> List[str]:
        return tokenise(text)

    def __repr__(self) -> str:
        return "LanguageData(%s, stages=%s, root=%s)" % (self.code, list(self.stages), self.root)


def register_language(code: str, root) -> LanguageData:
    """Make a directory of files known as language CODE (they win over installed packages)."""
    data = LanguageData.from_directory(root, code)
    _registry[code] = data
    return data


def _entry_points():
    from importlib import metadata
    eps = metadata.entry_points()
    if hasattr(eps, "select"):
        return list(eps.select(group=ENTRY_POINT_GROUP))
    return list(eps.get(ENTRY_POINT_GROUP, []))


def _env_dirs() -> List[Path]:
    return [Path(p) for p in os.environ.get("PYCG3_DATA", "").split(os.pathsep) if p]


def get_language(code: str) -> LanguageData:
    if code in _registry:
        return _registry[code]
    for base in _env_dirs():
        if (base / code).is_dir():
            return LanguageData.from_directory(base / code, code)
    for ep in _entry_points():
        if ep.name == code:
            data = ep.load()()
            if not isinstance(data, LanguageData):
                raise TypeError("entry point %s did not return a LanguageData" % ep.value)
            return data
    raise LookupError("no language package for %r; installed: %s. Install pycg3-lang-%s, or set PYCG3_DATA"
                      % (code, ", ".join(available_languages()) or "none", code))


def available_languages() -> List[str]:
    codes = set(_registry)
    for base in _env_dirs():
        if base.is_dir():
            codes.update(p.name for p in base.iterdir() if p.is_dir() and (p / "metadata.json").exists())
    codes.update(ep.name for ep in _entry_points())
    return sorted(codes)
