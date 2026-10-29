"""Set definitions and evaluation for VISL CG-3."""

from typing import List, Set as PySet, Dict, Union, Optional, Any
from pycg3.tag import TagPattern, is_wordform, is_baseform
from pycg3.cohort import Reading, Cohort


class CompositeTag:
    """Represents a composite tag (tag1 tag2 ...) where all elements must match."""

    __slots__ = ('elements',)

    def __init__(self, elements: List[Union[TagPattern, 'SetDefinition', 'CompositeTag']]):
        self.elements = elements

    def matches_reading(self, reading: Reading, grammar: Optional[Any] = None) -> bool:
        # Every element in the composite must match something in the reading
        for elem in self.elements:
            if isinstance(elem, TagPattern):
                if elem.is_any:
                    continue
                matched = False
                for tag in reading.all_tags():
                    if elem.matches_tag(tag):
                        matched = True
                        break
                if not matched:
                    return False
            elif isinstance(elem, CompositeTag):
                if not elem.matches_reading(reading, grammar):
                    return False
            elif isinstance(elem, SetDefinition):
                if not elem.matches_reading(reading, grammar):
                    return False
            elif isinstance(elem, str):
                if not reading.has_tag(elem):
                    return False
        return True

    def __repr__(self) -> str:
        return f"CompositeTag({' '.join(str(e) for e in self.elements)})"


class SetItem:
    """An element in a set expression: can be a TagPattern, CompositeTag, or set reference name."""

    __slots__ = ('item', 'is_negated')

    def __init__(self, item: Any, is_negated: bool = False):
        self.item = item
        self.is_negated = is_negated

    def __repr__(self) -> str:
        prefix = "!" if self.is_negated else ""
        return f"{prefix}{self.item}"


class SetDefinition:
    """Represents a named or anonymous set/list in CG-3."""

    __slots__ = ('name', 'items', 'operations', 'is_ordered', 'line_number')

    def __init__(self, name: str = "", line_number: int = 0, is_ordered: bool = False):
        self.name = name
        self.line_number = line_number
        self.is_ordered = is_ordered
        # items can be a list of items for a LIST, or set operations
        self.items: List[Any] = []
        # operations for SET expressions: list of (op, operand) where op in ('+', '-', '_', '^')
        self.operations: List[tuple] = []

    def is_empty(self) -> bool:
        return len(self.items) == 0 and len(self.operations) == 0

    def add_item(self, item: Any):
        self.items.append(item)

    def matches_reading(self, reading: Reading, grammar: Optional[Any] = None) -> bool:
        """Check whether a single reading matches this set."""
        # If set has complex operations (union, difference, intersection)
        if self.operations:
            # First evaluate initial item/set
            base_matches = False
            if self.items:
                base_matches = self._check_item_match(self.items[0], reading, grammar)
            for op, operand in self.operations:
                op_matches = self._check_item_match(operand, reading, grammar)
                if op == '+':
                    base_matches = base_matches or op_matches
                elif op == '-':
                    base_matches = base_matches and (not op_matches)
                elif op == '_':
                    base_matches = base_matches and op_matches
                elif op == '^':
                    base_matches = base_matches != op_matches
            return base_matches

        # Default LIST: OR of all items
        if not self.items:
            return False

        for item in self.items:
            if self._check_item_match(item, reading, grammar):
                return True
        return False

    def _check_item_match(self, item: Any, reading: Reading, grammar: Optional[Any] = None) -> bool:
        negated = False
        if isinstance(item, SetItem):
            negated = item.is_negated
            item = item.item

        res = False
        if isinstance(item, TagPattern):
            if item.is_any:
                res = True
            else:
                for t in reading.all_tags():
                    if item.matches_tag(t):
                        res = True
                        break
        elif isinstance(item, CompositeTag):
            res = item.matches_reading(reading, grammar)
        elif isinstance(item, SetDefinition):
            res = item.matches_reading(reading, grammar)
        elif isinstance(item, str):
            # Might be a set name or tag
            if grammar and item in grammar.sets:
                res = grammar.sets[item].matches_reading(reading, grammar)
            else:
                # Check direct tag match
                pattern = TagPattern(item)
                for t in reading.all_tags():
                    if pattern.matches_tag(t):
                        res = True
                        break
        return (not res) if negated else res

    def matches_cohort_normal(self, cohort: Cohort, grammar: Optional[Any] = None) -> bool:
        """Normal cohort match: at least one active reading matches, or untouchable tags match."""
        # Check untouchable tags on cohort
        if cohort.untouchable_tags:
            for item in self.items:
                target_tag = item.item if isinstance(item, SetItem) else item
                if isinstance(target_tag, TagPattern):
                    for ut in cohort.untouchable_tags:
                        if target_tag.matches_tag(ut):
                            return True
                elif isinstance(target_tag, str):
                    if target_tag in cohort.untouchable_tags:
                        return True

        for r in cohort.active_readings():
            if self.matches_reading(r, grammar):
                return True
        return False

    def matches_cohort_careful(self, cohort: Cohort, grammar: Optional[Any] = None) -> bool:
        """Careful cohort match: ALL active readings must match the set."""
        readings = cohort.active_readings()
        if not readings:
            return False
        for r in readings:
            if not self.matches_reading(r, grammar):
                return False
        return True

    def __repr__(self) -> str:
        return f"SetDefinition({self.name}, items={len(self.items)})"
