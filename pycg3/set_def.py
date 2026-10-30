"""Set definitions and evaluation for VISL CG-3."""

from typing import List, Dict, Optional, Any
from pycg3.tag import TagPattern
from pycg3.cohort import Reading, Cohort


class CompositeTag:
    """A composite tag (tag1 tag2 ...): every element must be found on the same reading."""

    __slots__ = ('elements', '_lits', '_pats')

    def __init__(self, elements: List[TagPattern]):
        self.elements = elements
        self._lits = frozenset(e.raw for e in elements if _is_literal(e))
        self._pats = [e for e in elements if not _is_literal(e)]

    def matches_reading(self, reading: Reading, grammar: Optional[Any] = None) -> bool:
        have = reading.match_set()
        if not self._lits <= have:
            return False
        for p in self._pats:
            if not _pattern_matches(p, have):
                return False
        return True

    def __repr__(self) -> str:
        return f"CompositeTag({' '.join(e.raw for e in self.elements)})"


def _is_literal(p: TagPattern) -> bool:
    return not (p.is_any or p.is_regex or p.is_case_insensitive or p.is_failfast)


def _pattern_matches(p: TagPattern, have) -> bool:
    if p.is_any:
        return True
    if _is_literal(p):
        return p.raw in have
    for t in have:
        if p.matches_tag(t):
            return True
    return False


import threading

# While the contexts of one rule are tried on one target reading, $$Set / &&Set operands must agree on
# which member of the set they matched. The rule sets _state.unif to a fresh dict for each target reading
# (per thread, so one grammar can serve several threads).
_state = threading.local()


def get_unif() -> Optional[Dict[str, list]]:
    return getattr(_state, 'unif', None)


def set_unif(value: Optional[Dict[str, list]]) -> None:
    _state.unif = value


class UnifySet:
    """$$Name (any tag of the set) or &&Name (a whole composite tag): every use inside one rule has to match
    the same member of the set. Outside a rule (UNIF is None) it is just the set."""

    __slots__ = ('name', 'kind', 'registry')

    def __init__(self, name: str, kind: str, registry: Dict[str, 'SetDefinition']):
        self.name = name
        self.kind = kind
        self.registry = registry

    def matches_reading(self, reading: Reading, grammar: Optional[Any] = None) -> bool:
        target = self.registry[self.name]
        unif = get_unif()
        if unif is None or not target.items:
            return target.matches_reading(reading)
        have = reading.match_set()
        hits = []
        for item in target.items:
            if isinstance(item, CompositeTag):
                if item.matches_reading(reading):
                    hits.append(item)
            elif _pattern_matches(item, have):
                hits.append(item)
        if not hits:
            return False
        key = self.kind + self.name
        bound = unif.get(key)
        if bound is None:
            unif[key] = hits
            return True
        both = [h for h in hits if h in bound]
        if not both:
            return False
        unif[key] = both
        return True

    def __repr__(self) -> str:
        return "%s%s" % (self.kind, self.name)


class SetDefinition:
    """A named or anonymous set.

    A LIST has `items` (TagPattern or CompositeTag alternatives). A SET expression has `groups`:
    a list of OR-groups, each a left-to-right chain [(None, operand), (op, operand), ...] with op one of
    'and' (+), 'minus' (-), 'xor' (^); an operand is a SetDefinition or the name of one.
    """

    __slots__ = ('name', 'items', 'groups', 'is_ordered', 'line_number', 'registry')

    def __init__(self, name: str = "", line_number: int = 0, is_ordered: bool = False,
                 registry: Optional[Dict[str, 'SetDefinition']] = None):
        self.name = name
        self.line_number = line_number
        self.is_ordered = is_ordered
        self.items: List[Any] = []
        self.groups: List[list] = []
        self.registry = registry if registry is not None else {}

    def is_empty(self) -> bool:
        return not self.items and not self.groups

    def add_item(self, item: Any):
        self.items.append(item)

    def _resolve(self, operand):
        if isinstance(operand, (SetDefinition, UnifySet)):
            return operand
        try:
            return self.registry[operand]
        except KeyError:
            raise ValueError("Undefined set %r (used in %r)" % (operand, self.name or "an inline set"))

    def matches_reading(self, reading: Reading, grammar: Optional[Any] = None) -> bool:
        if self.groups:
            for group in self.groups:
                res = self._resolve(group[0][1]).matches_reading(reading)
                for op, operand in group[1:]:
                    other = self._resolve(operand).matches_reading(reading)
                    if op == 'and':
                        res = res and other
                    elif op == 'minus':
                        res = res and not other
                    elif op == 'xor':
                        res = res != other
                if res:
                    return True
            return False
        have = reading.match_set()
        for item in self.items:
            if isinstance(item, CompositeTag):
                if item.matches_reading(reading):
                    return True
            elif _pattern_matches(item, have):
                return True
        return False

    def matches_cohort_normal(self, cohort: Cohort, grammar: Optional[Any] = None) -> bool:
        """At least one active reading matches."""
        for r in cohort.readings:
            if not r.deleted and self.matches_reading(r):
                return True
        return False

    def matches_cohort_careful(self, cohort: Cohort, grammar: Optional[Any] = None) -> bool:
        """Every active reading matches."""
        seen = False
        for r in cohort.readings:
            if r.deleted:
                continue
            seen = True
            if not self.matches_reading(r):
                return False
        return seen

    def __repr__(self) -> str:
        return f"SetDefinition({self.name}, items={len(self.items)}, groups={len(self.groups)})"
