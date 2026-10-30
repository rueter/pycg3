"""Cohort, Reading, and SingleWindow data structures."""

from typing import List, Set, Optional, Dict, Any
from pycg3.tag import is_wordform, is_baseform


class Reading:
    """Represents a single reading of a cohort."""

    __slots__ = (
        'baseform',
        'tags',
        '_tag_set',
        'sub_readings',
        'deleted',
        'changed',
        'trace',
        'parent_cohort',
        'mapping_tags',
        'id',
        'parent_id',
        'rel_name',
        '_match_cache',
        'mapped'
    )

    def __init__(self, baseform: str = "", tags: Optional[List[str]] = None, parent_cohort: Optional['Cohort'] = None):
        self.baseform = baseform
        self.tags: List[str] = list(tags) if tags is not None else []
        self._tag_set: Set[str] = set(self.tags)
        self.sub_readings: List['Reading'] = []
        self.deleted = False
        self.changed = False
        self.trace: List[str] = []
        self.parent_cohort: Optional['Cohort'] = parent_cohort
        self.mapping_tags: Set[str] = set()
        self.id: Optional[int] = None
        self.parent_id: Optional[int] = None
        self.rel_name: Optional[str] = None
        self._match_cache: Optional[frozenset] = None
        self.mapped = False

        # Check for dependency / relation tags
        for t in self.tags:
            if t.startswith('#') and '->' in t:
                # Dependency tag: e.g. #1->2 or #1->2:rel
                parts = t[1:].split('->')
                try:
                    self.id = int(parts[0])
                    if ':' in parts[1]:
                        pid, rname = parts[1].split(':', 1)
                        self.parent_id = int(pid)
                        self.rel_name = rname
                    else:
                        self.parent_id = int(parts[1])
                except ValueError:
                    pass

    def add_tag(self, tag: str, mapping_prefix: str = '@'):
        """Add a tag to the reading if not already present."""
        if tag not in self._tag_set:
            self._match_cache = None
            self.tags.append(tag)
            self._tag_set.add(tag)
            if tag.startswith(mapping_prefix):
                self.mapping_tags.add(tag)
            self.changed = True

    def remove_tag(self, tag: str):
        """Remove a tag from the reading."""
        if tag in self._tag_set:
            self._match_cache = None
            self.tags = [t for t in self.tags if t != tag]
            self._tag_set.discard(tag)
            self.mapping_tags.discard(tag)
            self.changed = True

    def replace_tag(self, old_tag: str, new_tags: List[str], mapping_prefix: str = '@'):
        """Replace old_tag with one or more new_tags in-place."""
        if old_tag not in self._tag_set:
            return
        self._match_cache = None
        new_list = []
        replaced = False
        for t in self.tags:
            if t == old_tag and not replaced:
                new_list.extend(new_tags)
                replaced = True
            elif t != old_tag:
                new_list.append(t)
        self.tags = new_list
        self._tag_set = set(self.tags)
        self.mapping_tags = {t for t in self.tags if t.startswith(mapping_prefix)}
        self.changed = True

    def identity(self):
        """What makes two readings the same: base form and tag set (order does not matter), sub-readings in order."""
        return (self.baseform, frozenset(self.tags), tuple(sub.identity() for sub in self.sub_readings))

    def has_tag(self, tag: str) -> bool:
        """Check if reading contains exact tag."""
        return tag in self._tag_set or tag == self.baseform

    def match_set(self) -> frozenset:
        """Every tag a set can match on this reading, base form and word form included (cached)."""
        if self._match_cache is None:
            self._match_cache = frozenset(self.all_tags())
        return self._match_cache

    def all_tags(self) -> List[str]:
        """Return list of all tags including baseform and wordform."""
        res = []
        if self.baseform:
            res.append(self.baseform)
        res.extend(self.tags)
        if self.parent_cohort and self.parent_cohort.wordform:
            res.append(self.parent_cohort.wordform)
        if self.parent_cohort and self.parent_cohort.is_end:
            res.append('<<<')
        return res

    def to_text(self, indent: str = "\t", show_rules: bool = False, trace: bool = False) -> str:
        """Format reading as VISL CG-3 text line."""
        parts = []
        if self.baseform:
            parts.append(self.baseform)
        parts.extend(self.tags)
        line = indent + " ".join(parts)
        if show_rules and self.changed:
            line += " <<<"
        if trace and self.trace:
            line += " " + " ".join(self.trace)
        lines = [line]
        for sub in self.sub_readings:
            lines.append(sub.to_text(indent=indent + "\t", show_rules=show_rules, trace=trace))
        return "\n".join(lines)

    def clone(self, parent_cohort: Optional['Cohort'] = None) -> 'Reading':
        """Deep copy reading for cohort operations."""
        nr = Reading(self.baseform, list(self.tags), parent_cohort=parent_cohort)
        nr.deleted = self.deleted
        nr.changed = self.changed
        nr.trace = list(self.trace)
        nr.mapping_tags = set(self.mapping_tags)
        nr.id = self.id
        nr.parent_id = self.parent_id
        nr.rel_name = self.rel_name
        nr.mapped = self.mapped
        nr.sub_readings = [s.clone(parent_cohort=parent_cohort) for s in self.sub_readings]
        return nr

    def __repr__(self) -> str:
        return f"Reading({self.baseform} {' '.join(self.tags)})"


class Cohort:
    """Represents a cohort (a wordform with its readings and untouchable tags)."""

    __slots__ = (
        'wordform',
        'untouchable_tags',
        '_untouchable_set',
        'readings',
        'deleted_readings',
        'text_before',
        'line_number',
        'global_number',
        'parent_window',
        'is_end',
        '_wread'
    )

    def __init__(
        self,
        wordform: str = "",
        untouchable_tags: Optional[List[str]] = None,
        text_before: Optional[List[str]] = None,
        line_number: int = 0,
        global_number: int = 0,
        parent_window: Optional['SingleWindow'] = None
    ):
        self.wordform = wordform
        self.untouchable_tags: List[str] = list(untouchable_tags) if untouchable_tags is not None else []
        self._untouchable_set: Set[str] = set(self.untouchable_tags)
        self.readings: List[Reading] = []
        self.deleted_readings: List[Reading] = []
        self.text_before: List[str] = list(text_before) if text_before is not None else []
        self.line_number = line_number
        self.global_number = global_number
        self.parent_window: Optional['SingleWindow'] = parent_window
        self._wread = None
        self.is_end = False          # the last cohort of a window: its readings answer to the tag <<<

    def append_reading(self, reading: Reading):
        """Append a reading to this cohort."""
        reading.parent_cohort = self
        self.readings.append(reading)

    def dedupe_readings(self, with_trace: bool = False) -> bool:
        """Drop later readings that have the same base form and the same set of tags as an earlier one
        (vislcg3 does this silently, on input and after a rule has changed a reading). With -t the rules
        that hit a reading are part of what it is, so readings with different traces stay apart."""
        seen, keep = set(), []
        for r in self.readings:
            key = (r.identity(), tuple(r.trace) if with_trace else ())
            if key in seen and not r.deleted:
                continue
            seen.add(key)
            keep.append(r)
        changed = len(keep) != len(self.readings)
        self.readings = keep
        return changed

    def active_readings(self) -> List[Reading]:
        """Return active (non-deleted) readings."""
        return [r for r in self.readings if not r.deleted]

    def select_reading(self, reading: Reading, rule_name: str = ""):
        """Select this reading, removing all other non-matching readings."""
        for r in self.readings:
            if r is not reading and not r.deleted:
                r.deleted = True
                r.changed = True
                if rule_name:
                    r.trace.append(rule_name)
                self.deleted_readings.append(r)
        self.readings = [reading]
        reading.changed = True
        if rule_name:
            reading.trace.append(rule_name)

    def remove_reading(self, reading: Reading, rule_name: str = ""):
        """Remove a reading."""
        if not reading.deleted:
            reading.deleted = True
            reading.changed = True
            if rule_name:
                reading.trace.append(rule_name)
            self.deleted_readings.append(reading)
            self.readings = [r for r in self.readings if r is not reading]

    def to_text(self, show_rules: bool = False, trace: bool = False, pipe_deleted: bool = False) -> str:
        """Format cohort into VISL CG-3 stream format."""
        out = []
        if self.text_before:
            out.extend(self.text_before)
        header = self.wordform
        if self.untouchable_tags:
            header += " " + " ".join(self.untouchable_tags)
        out.append(header)
        for r in self.readings:
            out.append(r.to_text(show_rules=show_rules, trace=trace))
        if pipe_deleted:
            for r in self.deleted_readings:
                # vislcg3 prints a deleted reading, and each of its sub-reading lines, with a leading ';'
                out.extend(";" + ln for ln in r.to_text(show_rules=show_rules, trace=trace).split("\n"))
        return "\n".join(out)

    def clone(self, parent_window: Optional['SingleWindow'] = None) -> 'Cohort':
        """Deep copy cohort."""
        nc = Cohort(
            self.wordform,
            list(self.untouchable_tags),
            list(self.text_before),
            self.line_number,
            self.global_number,
            parent_window=parent_window
        )
        for r in self.readings:
            nc.append_reading(r.clone(parent_cohort=nc))
        nc.deleted_readings = [r.clone(parent_cohort=nc) for r in self.deleted_readings]
        return nc

    def __repr__(self) -> str:
        return f"Cohort({self.wordform}, {len(self.readings)} readings)"


class SingleWindow:
    """Represents a window (sentence / clause) of cohorts."""

    __slots__ = ('cohorts', 'text_after', 'variables', 'flush_after', 'begin')

    def __init__(self, cohorts: Optional[List[Cohort]] = None):
        self.cohorts: List[Cohort] = list(cohorts) if cohorts is not None else []
        self.text_after: List[str] = []
        self.variables: Dict[str, str] = {}
        self.flush_after = False
        # CG-3 puts a begin cohort (tag >>>) before every window that only contextual tests can reach
        self.begin = self._edge('>>>')
        for c in self.cohorts:
            c.parent_window = self

    def _edge(self, tag: str) -> Cohort:
        c = Cohort(wordform="", parent_window=self)
        c.append_reading(Reading(baseform="", tags=[tag]))
        return c

    def mark_end(self):
        """The last cohort of the window gets the tag <<< (for matching only), as vislcg3 does."""
        for c in self.cohorts:
            if c.is_end:
                c.is_end = False
                for r in c.readings:
                    r._match_cache = None
        if self.cohorts:
            last = self.cohorts[-1]
            last.is_end = True
            for r in last.readings:
                r._match_cache = None

    def virtual(self, vi: int) -> Cohort:
        """Cohort at virtual index vi: 0 is the begin cohort, 1..n the real cohorts."""
        return self.begin if vi == 0 else self.cohorts[vi - 1]

    def append_cohort(self, cohort: Cohort):
        cohort.parent_window = self
        self.cohorts.append(cohort)

    def to_text(self, show_rules: bool = False, trace: bool = False, pipe_deleted: bool = False) -> str:
        lines = []
        for c in self.cohorts:
            lines.append(c.to_text(show_rules=show_rules, trace=trace, pipe_deleted=pipe_deleted))
        if self.text_after:
            lines.extend(self.text_after)
        return "\n".join(lines)
