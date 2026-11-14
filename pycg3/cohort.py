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
        'mapped',
        'number'
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
        self.number = -1            # place in the output: vislcg3 prints readings by number, whatever order it keeps them in

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

    def sub_chain(self) -> List['Reading']:
        """The sub-readings in the order the stream lists them (1 = the first line below this reading)."""
        out: List['Reading'] = []
        stack = list(reversed(self.sub_readings))
        while stack:
            r = stack.pop()
            out.append(r)
            stack.extend(reversed(r.sub_readings))
        return out

    def sub_reading(self, n: int) -> Optional['Reading']:
        """Sub-reading n as vislcg3 numbers them: 1, 2, ... from the first, -1, -2, ... from the last, 0 = this reading."""
        if n == 0:
            return self
        chain = self.sub_chain()
        if n > 0:
            return chain[n - 1] if n <= len(chain) else None
        return chain[n] if -n <= len(chain) else None

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

    def to_text(self, indent: str = "\t", show_rules: bool = False, trace: bool = False, dep: str = "") -> str:
        """Format reading as VISL CG-3 text line."""
        parts = []
        if self.baseform:
            parts.append(self.baseform)
        parts.extend(t for t in self.tags if t != '<<<' and t != '>>>')     # the window edge tags are never printed
        if dep:
            parts.append(dep)           # #self->parent, after the tags and before the rule labels
        line = indent + " ".join(parts)
        if show_rules and self.changed:
            line += " <<<"
        if trace and self.trace:
            line += " " + " ".join(self.trace)
        lines = [line]
        for sub in self.sub_readings:
            lines.append(sub.to_text(indent=indent + "\t", show_rules=show_rules, trace=trace, dep=dep))
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
        nr.number = self.number
        nr.sub_readings = [s.clone(parent_cohort=parent_cohort) for s in self.sub_readings]
        return nr

    def __repr__(self) -> str:
        return f"Reading({self.baseform} {' '.join(self.tags)})"


def _plain_key(r: 'Reading'):
    """A reading without its mapping tags: what vislcg3 compares (hash_plain) when it merges readings for output."""
    return (r.baseform, frozenset(t for t in r.tags if t not in r.mapping_tags), tuple(_plain_key(s) for s in r.sub_readings))


def _has_mapping(r: 'Reading') -> bool:
    return bool(r.mapping_tags) or any(_has_mapping(s) for s in r.sub_readings)


def merge_mapped_readings(readings: List['Reading'], with_trace: bool = False) -> List['Reading']:
    """vislcg3 prints readings that differ only in their mapping tag as one reading with all the mapping tags, last
    (mergeMappings; --split-mappings turns it off). Readings with a mapping tag only merge with others that have one."""
    groups: Dict[Any, List['Reading']] = {}
    for r in readings:
        key = (_plain_key(r), tuple(r.trace) if with_trace else (), _has_mapping(r))
        groups.setdefault(key, []).append(r)
    if len(groups) == len(readings):
        return list(readings)
    out = []
    for members in groups.values():
        first = members[0]
        nr = first.clone(parent_cohort=first.parent_cohort)
        maps: List[str] = []
        for m in members:
            for t in m.tags:
                if t in m.mapping_tags and t not in maps:
                    maps.append(t)
        nr.tags = [t for t in first.tags if t not in first.mapping_tags] + maps
        nr._tag_set = set(nr.tags)
        nr.mapping_tags = set(maps)
        nr._match_cache = None
        out.append(nr)
    return out


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
        '_wread',
        '_next_number',
        'dep_parent',
        'dep_children',
        'dep_in',
        'relations',
        'related',
        'rel_in'
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
        self._next_number = 0
        self.is_end = False          # the last cohort of a window: its readings answer to the tag <<<
        self.dep_parent: Optional['Cohort'] = None       # set by SETPARENT / SETCHILD; the begin cohort is the root
        self.dep_children: List['Cohort'] = []
        self.relations: Dict[str, List[int]] = {}        # relation name -> global numbers of the cohorts it points to
        self.related = False                              # prints ID:n (and the relations); set by a relation rule or input ID:/R: tags
        self.rel_in: Optional[tuple] = None               # (own input id, {name: set of input ids}) from ID: and R:name:id tags
        self.dep_in: Optional[tuple] = None              # (own number, parent number) as the input gave them in #n->m

    def append_reading(self, reading: Reading):
        """Append a reading to this cohort."""
        reading.parent_cohort = self
        if reading.number < 0:
            reading.number = self._next_number
        self._next_number = max(self._next_number, reading.number + 1)
        self.readings.append(reading)

    def split_mappings(self, mapping_prefix: str = '@') -> bool:
        """A reading with several mapping tags becomes one reading per mapping tag (vislcg3 does this to every
        cohort before it runs the next rule, so after a MAP (@A @B) the two are separate readings)."""
        if not any(len(r.mapping_tags) > 1 for r in self.readings):
            return False
        new_readings = []
        for r in self.readings:
            mapping = [t for t in r.tags if t.startswith(mapping_prefix)]
            if len(mapping) > 1:
                base = [t for t in r.tags if not t.startswith(mapping_prefix)]
                for mt in mapping:
                    nr = Reading(baseform=r.baseform, tags=base + [mt], parent_cohort=self)
                    nr.number = r.number
                    nr.deleted = r.deleted
                    nr.changed = r.changed
                    nr.trace = list(r.trace)
                    nr.sub_readings = [x.clone(parent_cohort=self) for x in r.sub_readings]
                    nr.mapping_tags = {mt}
                    nr.mapped = True
                    new_readings.append(nr)
            else:
                new_readings.append(r)
        self.readings = new_readings
        return True

    def add_relation(self, name: str, target: int) -> bool:
        ids = self.relations.setdefault(name, [])
        if target in ids:
            return False
        ids.append(target)
        ids.sort()
        return True

    def set_relation(self, name: str, target: int) -> bool:
        ids = self.relations.setdefault(name, [])
        if ids == [target]:
            return False
        self.relations[name] = [target]
        return True

    def rem_relation(self, name: str, target: int) -> bool:
        ids = self.relations.get(name)
        if ids is not None and target in ids:
            ids.remove(target)
            return True
        return False

    def relation_text(self) -> str:
        """ID:n R:name:m ... as vislcg3 prints them: the names in the order of their hashes."""
        if not self.related:
            return ""
        from pycg3.tag import cg3_hash
        parts = ["ID:%d" % self.global_number]
        for name in sorted(self.relations, key=cg3_hash):
            parts.extend("R:%s:%d" % (name, target) for target in self.relations[name])
        return " ".join(parts)

    def ordered_readings(self) -> List[Reading]:
        """The readings in the order vislcg3 prints them (see remove_reading for why that is not self.readings)."""
        return sorted(self.readings, key=lambda r: r.number)

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
            for i, r in enumerate(self.readings):
                if r is reading:
                    # vislcg3 fills the gap with the last reading instead of closing it up. The output is kept in
                    # order by the reading numbers, but "first reading that matches" (the $$ unification binds to
                    # it) goes by the order in the list.
                    last = self.readings.pop()
                    if i < len(self.readings):
                        self.readings[i] = last
                    break

    def to_text(self, show_rules: bool = False, trace: bool = False, pipe_deleted: bool = False, dep: str = "") -> str:
        """Format cohort into VISL CG-3 stream format."""
        out = []
        if self.text_before:
            out.extend(self.text_before)
        header = self.wordform
        if self.untouchable_tags:
            header += " " + " ".join(self.untouchable_tags)
        out.append(header)
        for r in merge_mapped_readings(self.ordered_readings(), trace):
            out.append(r.to_text(show_rules=show_rules, trace=trace, dep=dep))
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

    __slots__ = ('cohorts', 'text_after', 'variables', 'flush_after', 'begin', 'has_dep')

    def __init__(self, cohorts: Optional[List[Cohort]] = None):
        self.has_dep = False         # a dependency rule attached something in this window
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

    def index_of(self, cohort: Cohort) -> int:
        """The virtual index of a cohort: 0 for the begin cohort, 1..n for the real ones (vislcg3's dependency numbers)."""
        if cohort is self.begin:
            return 0
        for k, c in enumerate(self.cohorts):
            if c is cohort:
                return k + 1
        return -1

    def append_cohort(self, cohort: Cohort):
        cohort.parent_window = self
        self.cohorts.append(cohort)

    def resolve_input_relations(self, relation_map: Dict[int, 'Cohort']):
        """ID:n and R:name:m of the input: relation_map takes an input id to the cohort that carried it; relations to ids
        not seen (yet) are dropped."""
        for c in self.cohorts:
            if c.rel_in is not None and c.rel_in[0]:
                relation_map[c.rel_in[0]] = c
        for c in self.cohorts:
            if c.rel_in is None:
                continue
            c.related = True
            for name, targets in c.rel_in[1].items():
                for t in sorted(targets):
                    other = relation_map.get(t)
                    if other is not None:
                        c.add_relation(name, other.global_number)

    def resolve_input_dependencies(self):
        """The #n->m of the input become real links. n and m count the cohorts as the input numbered them (it may restart
        in every window, or a repeated n starts a new numbering); a parent that does not exist leaves the cohort without
        one, and 0 is the root (vislcg3's reflowDependencyWindow)."""
        pending, numbering = [], {}

        def flush():
            numbering[0] = self.begin
            for c in pending:
                own, parent = c.dep_in
                if own == parent:
                    continue
                target = numbering.get(parent)
                if target is None or target is c:
                    continue
                c.dep_parent = target
                target.dep_children.append(c)
            for c in pending:
                c.dep_children.sort(key=self.index_of)
            self.begin.dep_children.sort(key=self.index_of)
            pending.clear()
            numbering.clear()

        for c in self.cohorts:
            if c.dep_in is None:
                continue
            self.has_dep = True
            if c.dep_in[0] in numbering:
                flush()
            numbering[c.dep_in[0]] = c
            pending.append(c)
        if pending:
            flush()

    def to_text(self, show_rules: bool = False, trace: bool = False, pipe_deleted: bool = False,
                deps: Optional[bool] = None) -> str:
        """deps: print #self->parent on every reading (vislcg3 does once a dependency rule has attached anything);
        None means: if this window has an attachment."""
        if deps is None:
            deps = self.has_dep
        lines = []
        for k, c in enumerate(self.cohorts):
            dep = ""
            if deps:
                parent = c.dep_parent
                dep = "#%d->%d" % (k + 1, self.index_of(parent) if parent is not None else k + 1)
            rel = c.relation_text()
            if rel:
                dep = (dep + " " + rel) if dep else rel
            lines.append(c.to_text(show_rules=show_rules, trace=trace, pipe_deleted=pipe_deleted, dep=dep))
        if self.text_after:
            lines.extend(self.text_after)
        return "\n".join(lines)
