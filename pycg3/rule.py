"""Rule representation and execution for VISL CG-3."""

from typing import List, Optional, Any, Tuple
from pycg3.cohort import Cohort, Reading, SingleWindow
from pycg3.context import ContextualTest
from pycg3.set_def import SetDefinition, CompositeTag, _is_literal


class Rule:
    """A single CG-3 rule: TYPE[:name] [flags] [action] [TARGET] set [IF test...]."""

    __slots__ = (
        'type', 'name', 'label', 'line_number', 'target', 'target_modifiers', 'context_tests',
        'action_tags', 'subst_old', 'subst_old_tag', 'wordform_filter', 'direction', 'flags', 'is_careful',
        'uses_unify',
    )

    def __init__(self, rule_type: str, target: Any, name: str = "", line_number: int = 0,
                 context_tests: Optional[List[ContextualTest]] = None, action_tags: Optional[List[str]] = None,
                 subst_old: Optional[SetDefinition] = None, target_modifiers: str = "",
                 wordform_filter: Optional[str] = None, subst_old_tag: Optional[str] = None):
        self.type = rule_type.upper()
        self.name = name
        # the trace label vislcg3 -t prints after a changed reading: TYPE:line[:name]
        self.label = "%s:%d%s" % (self.type, line_number, (":" + name) if name else "")
        self.line_number = line_number
        self.target = target
        self.target_modifiers = target_modifiers
        self.context_tests = list(context_tests or [])
        self.action_tags = list(action_tags or [])
        self.subst_old = subst_old
        self.subst_old_tag = subst_old_tag
        self.wordform_filter = wordform_filter
        self.direction = "AFTER"
        self.flags: set = set()
        self.is_careful = 'c' in target_modifiers.lower()
        self.uses_unify = False

    @property
    def iterates(self) -> bool:
        """Does a change by this rule send its section round again? As in vislcg3, only SELECT, REMOVE, IFF,
        REMCOHORT, MOVE and SWITCH do, unless the rule says ITERATE / NOITERATE."""
        if 'ITERATE' in self.flags:
            return True
        if 'NOITERATE' in self.flags:
            return False
        return self.type in ('SELECT', 'REMOVE', 'IFF', 'DELIMIT', 'REMCOHORT', 'MOVE', 'SWITCH')

    # -- application ------------------------------------------------------------------------
    def apply_to_window(self, window: SingleWindow, grammar: Any) -> bool:
        """Apply the rule to every cohort of the window once. True if anything changed."""
        changed = False
        i = 0
        while i < len(window.cohorts):
            cohort = window.cohorts[i]
            if self.wordform_filter and cohort.wordform != self.wordform_filter:
                i += 1
                continue
            if self.uses_unify:
                targets, tests_ok = self._unify_targets(window, i, cohort, grammar)
                if not targets:
                    i += 1
                    continue
            else:
                targets = [r for r in cohort.readings if not r.deleted and self._target_matches(r)]
                tests_ok = None
            if not targets and self.type not in ('REMCOHORT', 'ADDCOHORT', 'SETVARIABLE', 'REMVARIABLE'):
                i += 1
                continue
            if tests_ok is None:
                tests_ok = all(t.evaluate(window, i, grammar) for t in self.context_tests)
            if not tests_ok:
                if self.type == 'IFF':      # IFF: SELECT where the contexts hold, REMOVE where they do not
                    changed = self._remove(cohort, targets) or changed
                i += 1
                continue
            did, delta = self._act(window, i, cohort, targets, grammar)
            if did and self.type in ('SUBSTITUTE', 'REPLACE', 'ADD', 'MAP', 'UNMAP', 'COPY', 'APPEND'):
                cohort.dedupe_readings(with_trace=getattr(grammar, 'trace_mode', False))
            changed = changed or did
            i += 1 + delta
        return changed

    def _unify_targets(self, window, i, cohort, grammar):
        """With $$Set / &&Set in the rule each target reading is tried on its own: the contexts have to agree
        with what that reading matched. Returns (readings that pass, True) or ([], None)."""
        from pycg3 import set_def
        good = []
        try:
            for r in cohort.readings:
                if r.deleted:
                    continue
                set_def.set_unif({})
                if self._target_matches(r) and all(t.evaluate(window, i, grammar) for t in self.context_tests):
                    good.append(r)
        finally:
            set_def.set_unif(None)
        return good, True

    def _target_matches(self, reading: Reading) -> bool:
        if isinstance(self.target, SetDefinition):
            res = self.target.matches_reading(reading)
        else:
            res = False
        return (not res) if '!' in self.target_modifiers else res

    def _act(self, window, i, cohort, targets, grammar) -> Tuple[bool, int]:
        t = self.type
        mp = grammar.mapping_prefix if grammar else '@'
        if t == 'SELECT':
            return self._select(cohort, targets), 0
        if t == 'REMOVE':
            return self._remove(cohort, targets), 0
        if t == 'IFF':
            return self._select(cohort, targets), 0
        if t in ('ADD', 'MAP'):
            return self._add(targets, mp, t == 'MAP'), 0
        if t == 'UNMAP':
            did = False
            for r in targets:
                for tag in list(r.mapping_tags):
                    r.remove_tag(tag)
                    did = True
                if did:
                    r.trace.append(self.label)
            return did, 0
        if t == 'REPLACE':
            targets = [r for r in targets if not r.mapped]
            for r in targets:
                r.tags = list(self.action_tags)
                r._tag_set = set(r.tags)
                r._match_cache = None
                r.mapping_tags = {x for x in r.tags if x.startswith(mp)}
                r.changed = True
                r.trace.append(self.label)
            return bool(targets), 0
        if t == 'SUBSTITUTE':
            return self._substitute(targets, mp), 0
        if t == 'APPEND' and self.action_tags:
            nr = Reading(baseform=self.action_tags[0], tags=self.action_tags[1:], parent_cohort=cohort)
            nr.changed = True
            nr.trace.append(self.label)
            cohort.append_reading(nr)
            return True, 0
        if t == 'COPY':
            for r in targets:
                nr = r.clone(parent_cohort=cohort)
                for tag in self.action_tags:
                    nr.add_tag(tag, mapping_prefix=mp)
                nr.trace.append(self.label)
                cohort.append_reading(nr)
            return bool(targets), 0
        if t == 'REMCOHORT':
            window.cohorts.pop(i)
            return True, -1
        if t == 'ADDCOHORT':
            return self._addcohort(window, i)
        if t == 'SETVARIABLE':
            for tag in self.action_tags:
                k, _, v = tag.partition('=')
                window.variables[k] = v or '1'
            return True, 0
        if t == 'REMVARIABLE':
            for tag in self.action_tags:
                window.variables.pop(tag, None)
            return True, 0
        return False, 0

    def _select(self, cohort: Cohort, targets: List[Reading]) -> bool:
        active = [r for r in cohort.readings if not r.deleted]
        if len(active) <= 1 or not targets or len(targets) == len(active):
            return False
        keep = set(map(id, targets))
        for r in active:
            if id(r) not in keep:
                cohort.remove_reading(r, rule_name=self.label)
        for r in targets:
            r.changed = True
            r.trace.append(self.label)
        return True

    def _remove(self, cohort: Cohort, targets: List[Reading]) -> bool:
        active = [r for r in cohort.readings if not r.deleted]
        if len(active) <= 1 or len(targets) >= len(active):
            return False                       # a cohort never loses its last reading
        for r in targets:
            cohort.remove_reading(r, rule_name=self.label)
        return True

    def _add(self, targets: List[Reading], mp: str, is_map: bool) -> bool:
        changed = False
        for r in targets:
            if r.mapped:                 # as in vislcg3, MAP, ADD and REPLACE leave a mapped reading alone
                continue
            did = False
            for tag in self.action_tags:
                if not r.has_tag(tag):
                    r.add_tag(tag, mapping_prefix=mp)
                    did = True
            if did:
                if is_map:
                    r.mapped = True
                r.trace.append(self.label)
                changed = True
        return changed

    def _substitute(self, targets: List[Reading], mp: str) -> bool:
        if self.subst_old is None:
            return False
        new = [x for x in self.action_tags if x != '*']
        changed = False
        for r in targets:
            hits = [k for k, tag in enumerate(r.tags) if self._old_matches(tag)]
            if not hits:
                continue
            first = hits[0]
            out = []
            for k, tag in enumerate(r.tags):
                if k == first:
                    out.extend(new)
                if k not in hits:
                    out.append(tag)
            r.tags = out
            r._tag_set = set(out)
            r._match_cache = None
            r.mapping_tags = {x for x in out if x.startswith(mp)}
            r.changed = True
            r.trace.append(self.label)
            changed = True
        return changed

    def _old_matches(self, tag: str) -> bool:
        probe = Reading(baseform="", tags=[tag])
        return self.subst_old.matches_reading(probe)

    def _addcohort(self, window: SingleWindow, i: int) -> Tuple[bool, int]:
        if not self.action_tags:
            return False, 0
        word = self.action_tags[0]
        base = self.action_tags[1] if len(self.action_tags) > 1 else '""'
        new_c = Cohort(wordform=word, parent_window=window)
        r = Reading(baseform=base, tags=self.action_tags[2:], parent_cohort=new_c)
        r.changed = True
        r.trace.append(self.label)
        new_c.append_reading(r)
        if self.direction == "BEFORE":
            window.cohorts.insert(i, new_c)
            return True, 1
        window.cohorts.insert(i + 1, new_c)
        return True, 0

    def __repr__(self) -> str:
        return f"Rule({self.label} {self.target} {' '.join(map(str, self.context_tests))})"
