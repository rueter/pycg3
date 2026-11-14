"""Rule representation and execution for VISL CG-3."""

from typing import List, Optional, Any, Tuple
from pycg3.cohort import Cohort, Reading, SingleWindow
from pycg3.context import ContextualTest
from pycg3.set_def import SetDefinition, CompositeTag, _is_literal
from pycg3.tag import is_baseform


class Rule:
    """A single CG-3 rule: TYPE[:name] [flags] [action] [TARGET] set [IF test...]."""

    __slots__ = (
        'type', 'name', 'label', 'line_number', 'target', 'target_modifiers', 'context_tests',
        'action_tags', 'subst_old', 'subst_old_tag', 'wordform_filter', 'direction', 'flags', 'is_careful',
        'uses_unify', 'sub', '_maps', 'copy_except', 'dep_tests',
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
        self._maps = None
        self.sub = None             # SUB:n - the target set is matched against the n-th sub-reading
        self.copy_except = None     # COPY (tags) EXCEPT set TARGET ... - the copy leaves out the tags in this set
        self.dep_tests: List[ContextualTest] = []      # SETPARENT / SETCHILD ... TO (tests)

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
        if self._maps is None:
            self._maps = self._mentions_mapping_tag(grammar)
        mp = grammar.mapping_prefix if grammar else '@'
        while i < len(window.cohorts):
            cohort = window.cohorts[i]
            if self.wordform_filter and cohort.wordform != self.wordform_filter:
                i += 1
                continue
            if self._maps and any(len(r.mapping_tags) > 1 for r in cohort.readings if not r.deleted):
                # vislcg3 makes one reading of each mapping tag when a rule's target matches one of them
                if any(self._target_matches(r) for r in cohort.readings if not r.deleted and len(r.mapping_tags) > 1):
                    cohort.split_mappings(mp)
            if self.uses_unify and self.type in ('SETPARENT', 'SETCHILD'):
                targets = [r for r in cohort.readings if not r.deleted]      # _set_dependency binds the $$Sets itself
                tests_ok = True
                if not targets:
                    i += 1
                    continue
            elif self.uses_unify:
                targets, tests_ok = self._unify_targets(window, i, cohort, grammar)
                if not targets:
                    i += 1
                    continue
            else:
                targets = [r for r in cohort.readings if not r.deleted and self._target_matches(r)]
                tests_ok = None
            if not targets and self.type not in ('SETVARIABLE', 'REMVARIABLE'):     # ADDCOHORT / REMCOHORT need a target too
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

    def _mentions_mapping_tag(self, grammar) -> bool:
        """Does the target set of this rule name a mapping tag (@SUBJ ...)?"""
        prefix = grammar.mapping_prefix if grammar else '@'
        seen: set = set()

        def walk(obj) -> bool:
            if obj is None or isinstance(obj, (int, float)) or id(obj) in seen:
                return False
            if isinstance(obj, str):
                obj = (grammar.sets.get(obj) if grammar else None)
                if obj is None or id(obj) in seen:
                    return False
            seen.add(id(obj))
            if hasattr(obj, 'raw'):                                   # TagPattern
                return obj.raw.lstrip('!').startswith(prefix)
            if hasattr(obj, 'elements'):                              # CompositeTag
                return any(walk(e) for e in obj.elements)
            if hasattr(obj, 'registry') and hasattr(obj, 'kind'):     # $$Set / &&Set
                return walk(obj.registry.get(obj.name))
            if hasattr(obj, 'groups'):                                # SetDefinition
                if any(walk(i) for i in obj.items):
                    return True
                return any(walk(operand) for chain in obj.groups for _, operand in chain)
            if hasattr(obj, 'linked_test'):                           # ContextualTest
                return (walk(obj.target) or walk(obj.barrier) or walk(obj.cbarrier) or walk(obj.linked_test)
                        or any(walk(t) for t in obj.ors))
            return False

        return walk(self.target)           # only the target: a mapping tag in a context does not split anything

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
        if self.sub is not None:
            reading = reading.sub_reading(self.sub)
            if reading is None:
                return False
        if isinstance(self.target, SetDefinition):
            res = self.target.matches_reading(reading)
        else:
            res = False
        return (not res) if '!' in self.target_modifiers else res

    def _act(self, window, i, cohort, targets, grammar) -> Tuple[bool, int]:
        t = self.type
        mp = grammar.mapping_prefix if grammar else '@'
        if t in ('SETPARENT', 'SETCHILD'):
            return self._set_dependency(window, i, cohort, targets, grammar), 0
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
                if self.copy_except is not None:
                    keep = [t for t in nr.tags
                            if not self.copy_except.matches_reading(Reading(baseform=nr.baseform, tags=[t]))]
                    nr.tags = keep
                    nr._tag_set = set(keep)
                    nr.mapping_tags = {t for t in keep if t.startswith(mp)}
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

    def _set_dependency(self, window, i, cohort, targets, grammar) -> bool:
        """SETPARENT: the cohort becomes a child of the cohort the TO tests lead to; SETCHILD: the other way round.
        The cohort it leads to is the one of the test with the A flag, else where the last LINKed test ended;
        a candidate that would make a loop is skipped (the scan goes on), and an earlier attachment is replaced."""
        from pycg3 import set_def
        if not self.dep_tests:
            return False
        as_child = self.type == 'SETPARENT'
        lead = targets[0] if targets else None      # the reading that gets the label
        if self.uses_unify:
            # $$Sets bind on the first reading that matches the target and have to agree in the contexts and the TO
            # tests as well; vislcg3 does not go on to the next reading with a binding of its own
            found = None
            for r in targets:
                set_def.set_unif({})
                try:
                    if not self._target_matches(r):
                        continue
                    if all(t.evaluate(window, i, grammar) for t in self.context_tests):
                        found = self._dep_search(window, i, cohort, grammar)
                finally:
                    set_def.set_unif(None)
                lead = r
                break
        else:
            found = self._dep_search(window, i, cohort, grammar)
        if found is None:
            return False
        other = window.virtual(found)
        child, parent = (cohort, other) if as_child else (other, cohort)
        if child.dep_parent is not parent:           # vislcg3 labels the readings even when it attaches to the same parent again
            if child.dep_parent is not None:
                child.dep_parent.dep_children.remove(child)
            child.dep_parent = parent
            parent.dep_children.append(child)
            parent.dep_children.sort(key=window.index_of)
        window.has_dep = True
        if lead is not None:
            lead.trace.append(self.label)           # vislcg3 labels the first reading that matched, not all of them
        return True

    def _dep_search(self, window, i, cohort, grammar):
        """The index of the cohort the TO tests lead to for the cohort at window index i, or None."""
        from pycg3 import context
        state = context.AttachState(window, cohort, as_child=self.type == 'SETPARENT',
                                    allow_loop='ALLOWLOOP' in self.flags)
        found = None
        try:
            for n, test in enumerate(self.dep_tests):
                state.marked = state.final = None
                context.set_attach(state if n == 0 else None)
                if n == 0:
                    if not test.evaluate(window, i, grammar):
                        if state.matched and len(self.dep_tests) == 1:
                            window.has_dep = True   # led only to cohorts it cannot attach to: vislcg3 still prints dependencies
                        return None
                    found = state.final
                elif found is None or not context._run_contextual_test(window, found, test):
                    return None                     # TO (a)(b): b is tested from the cohort a led to, and only has to hold
        finally:
            context.set_attach(None)
        return found

    def _select(self, cohort: Cohort, targets: List[Reading]) -> bool:
        active = [r for r in cohort.readings if not r.deleted]
        if len(active) <= 1 or not targets or len(targets) == len(active):
            return False
        keep = set(map(id, targets))
        for r in active:
            if id(r) not in keep:
                cohort.remove_reading(r, rule_name="" if self.sub is not None else self.label)
        for r in targets:
            r.changed = True
            self._trace_holder(r).trace.append(self.label)
        return True

    def _trace_holder(self, reading: Reading) -> Reading:
        """With SUB:n vislcg3 -t writes the rule on the line of the sub-reading it matched."""
        if self.sub is not None:
            return reading.sub_reading(self.sub) or reading
        return reading

    def _remove(self, cohort: Cohort, targets: List[Reading]) -> bool:
        active = [r for r in cohort.readings if not r.deleted]
        if len(active) <= 1 or len(targets) >= len(active):
            return False                       # a cohort never loses its last reading
        for r in targets:
            if self.sub is not None:
                cohort.remove_reading(r)
                self._trace_holder(r).trace.append(self.label)
            else:
                cohort.remove_reading(r, rule_name=self.label)
        return True

    def _ordered_action_tags(self, mp: str) -> List[str]:
        """The order vislcg3 puts added tags in: the plain ones as written, then the mapping tags, last one first."""
        mapping = [t for t in self.action_tags if t.startswith(mp)]
        if len(mapping) < 2:
            return self.action_tags
        return [t for t in self.action_tags if not t.startswith(mp)] + [mapping[-1]] + mapping[:-1]

    def _add(self, targets: List[Reading], mp: str, is_map: bool) -> bool:
        changed = False
        for r in targets:
            if r.mapped:                 # as in vislcg3, MAP, ADD and REPLACE leave a mapped reading alone
                continue
            did = False
            for tag in self._ordered_action_tags(mp):
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
            # a base form in the new list ("lemma" Tag ...) is the reading's base form, not one more tag
            plain = []
            for x in new:
                if is_baseform(x):
                    r.baseform = x
                else:
                    plain.append(x)
            for k, tag in enumerate(r.tags):
                if k == first:
                    out.extend(plain)
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
