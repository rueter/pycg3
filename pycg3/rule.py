"""Rule representation and execution for VISL CG-3."""

from typing import List, Optional, Any, Set, Tuple
from pycg3.cohort import Cohort, Reading, SingleWindow
from pycg3.context import ContextualTest
from pycg3.set_def import SetDefinition


class Rule:
    """Represents a single CG-3 rule."""

    __slots__ = (
        'type',
        'name',
        'line_number',
        'target',
        'target_modifiers',
        'context_tests',
        'action_tags',
        'subst_old_tag',
        'wordform_filter',
        'direction',  # 'BEFORE' or 'AFTER' for ADDCOHORT / MOVE
        'sub_reading_target',
        'is_careful'
    )

    def __init__(
        self,
        rule_type: str,
        target: Any,
        name: str = "",
        line_number: int = 0,
        context_tests: Optional[List[ContextualTest]] = None,
        action_tags: Optional[List[str]] = None,
        subst_old_tag: Optional[str] = None,
        target_modifiers: str = "",
        wordform_filter: Optional[str] = None
    ):
        self.type = rule_type.upper()
        self.name = name if name else str(line_number)
        self.line_number = line_number
        self.target = target
        self.target_modifiers = target_modifiers
        self.context_tests: List[ContextualTest] = list(context_tests) if context_tests is not None else []
        self.action_tags: List[str] = list(action_tags) if action_tags is not None else []
        self.subst_old_tag = subst_old_tag
        self.wordform_filter = wordform_filter
        self.direction = "AFTER"
        self.sub_reading_target = None
        self.is_careful = ('c' in target_modifiers.lower()) or (self.type == 'SELECT' and 'c' in target_modifiers.lower())

    def apply_to_window(self, window: SingleWindow, grammar: Any) -> bool:
        """Apply rule across the window. Returns True if any change was made."""
        changed = False
        cohorts = window.cohorts
        num_cohorts = len(cohorts)

        # Iterate through cohorts
        # For cohort manipulation like REMCOHORT / ADDCOHORT / MOVE, we handle index carefully
        c_idx = 0
        while c_idx < len(window.cohorts):
            cohort = window.cohorts[c_idx]

            # Check wordform filter if rule has one: e.g. "<word>" SELECT ...
            if self.wordform_filter and cohort.wordform != self.wordform_filter:
                c_idx += 1
                continue

            # Evaluate context tests
            tests_pass = True
            for test in self.context_tests:
                if not test.evaluate(window, c_idx, grammar):
                    tests_pass = False
                    break

            if self.type == 'IFF':
                # IFF acts as SELECT if tests pass, REMOVE if tests fail
                if tests_pass:
                    if self._apply_select(cohort, grammar):
                        changed = True
                else:
                    if self._apply_remove(cohort, grammar):
                        changed = True
                c_idx += 1
                continue

            if not tests_pass:
                c_idx += 1
                continue

            # Tests passed! Apply rule action
            rule_changed, index_delta = self._apply_action(window, c_idx, grammar)
            if rule_changed:
                changed = True
            c_idx += (1 + index_delta)

        return changed

    def _apply_action(self, window: SingleWindow, c_idx: int, grammar: Any) -> Tuple[bool, int]:
        cohort = window.cohorts[c_idx]

        if self.type == 'SELECT':
            return self._apply_select(cohort, grammar), 0

        elif self.type == 'REMOVE':
            return self._apply_remove(cohort, grammar), 0

        elif self.type == 'ADD' or self.type == 'MAP':
            return self._apply_add(cohort, grammar), 0

        elif self.type == 'UNMAP':
            return self._apply_unmap(cohort, grammar), 0

        elif self.type == 'REPLACE':
            return self._apply_replace(cohort, grammar), 0

        elif self.type == 'SUBSTITUTE':
            return self._apply_substitute(cohort, grammar), 0

        elif self.type == 'APPEND':
            return self._apply_append(cohort, grammar), 0

        elif self.type == 'COPY':
            return self._apply_copy(cohort, grammar), 0

        elif self.type == 'REMCOHORT':
            window.cohorts.pop(c_idx)
            return True, -1

        elif self.type == 'ADDCOHORT':
            return self._apply_addcohort(window, c_idx, grammar)

        elif self.type == 'SETVARIABLE':
            for tag in self.action_tags:
                if '=' in tag:
                    k, v = tag.split('=', 1)
                    window.variables[k] = v
                else:
                    window.variables[tag] = '1'
            return True, 0

        elif self.type == 'REMVARIABLE':
            for tag in self.action_tags:
                window.variables.pop(tag, None)
            return True, 0

        return False, 0

    def _matches_reading(self, reading: Reading, grammar: Any) -> bool:
        if isinstance(self.target, SetDefinition):
            res = self.target.matches_reading(reading, grammar)
        elif isinstance(self.target, str):
            if grammar and self.target in grammar.sets:
                res = grammar.sets[self.target].matches_reading(reading, grammar)
            else:
                from pycg3.tag import TagPattern
                pat = TagPattern(self.target)
                res = any(pat.matches_tag(t) for t in reading.all_tags())
        else:
            res = False
        return (not res) if ('!' in self.target_modifiers) else res

    def _apply_select(self, cohort: Cohort, grammar: Any) -> bool:
        active = cohort.active_readings()
        if len(active) <= 1:
            return False

        matching = [r for r in active if self._matches_reading(r, grammar)]
        if not matching:
            return False

        # If careful (c) and matching would delete everything, don't apply
        if self.is_careful and len(matching) == 0:
            return False

        # If matching is identical to active, no change needed
        if len(matching) == len(active):
            return False

        for r in active:
            if r not in matching:
                cohort.remove_reading(r, rule_name=self.name)
        for r in matching:
            r.changed = True
            r.trace.append(self.name)
        return True

    def _apply_remove(self, cohort: Cohort, grammar: Any) -> bool:
        active = cohort.active_readings()
        if not active:
            return False

        matching = [r for r in active if self._matches_reading(r, grammar)]
        if not matching:
            return False

        # If careful (c) or default CG-3 protection: do not remove ALL readings
        if (self.is_careful or True) and len(matching) >= len(active):
            # Cannot delete all readings in cohort
            return False

        for r in matching:
            cohort.remove_reading(r, rule_name=self.name)
        return True

    def _apply_add(self, cohort: Cohort, grammar: Any) -> bool:
        changed = False
        for r in cohort.active_readings():
            if self._matches_reading(r, grammar):
                for tag in self.action_tags:
                    if not r.has_tag(tag):
                        r.add_tag(tag, mapping_prefix=grammar.mapping_prefix if grammar else '@')
                        changed = True
                if changed:
                    r.trace.append(self.name)
        return changed

    def _apply_unmap(self, cohort: Cohort, grammar: Any) -> bool:
        changed = False
        mp = grammar.mapping_prefix if grammar else '@'
        for r in cohort.active_readings():
            if self._matches_reading(r, grammar):
                maps = list(r.mapping_tags)
                for tag in maps:
                    r.remove_tag(tag)
                    changed = True
                if changed:
                    r.trace.append(self.name)
        return changed

    def _apply_replace(self, cohort: Cohort, grammar: Any) -> bool:
        changed = False
        mp = grammar.mapping_prefix if grammar else '@'
        for r in cohort.active_readings():
            if self._matches_reading(r, grammar):
                r.tags = list(self.action_tags)
                r._tag_set = set(r.tags)
                r.mapping_tags = {t for t in r.tags if t.startswith(mp)}
                r.changed = True
                r.trace.append(self.name)
                changed = True
        return changed

    def _apply_substitute(self, cohort: Cohort, grammar: Any) -> bool:
        if not self.subst_old_tag:
            return False
        changed = False
        mp = grammar.mapping_prefix if grammar else '@'
        for r in cohort.active_readings():
            if self._matches_reading(r, grammar) and r.has_tag(self.subst_old_tag):
                r.replace_tag(self.subst_old_tag, self.action_tags, mapping_prefix=mp)
                r.trace.append(self.name)
                changed = True
        return changed

    def _apply_append(self, cohort: Cohort, grammar: Any) -> bool:
        # action_tags contains [baseform, tag1, tag2...]
        if not self.action_tags:
            return False
        base = self.action_tags[0]
        tags = self.action_tags[1:]
        nr = Reading(baseform=base, tags=tags, parent_cohort=cohort)
        nr.changed = True
        nr.trace.append(self.name)
        cohort.append_reading(nr)
        return True

    def _apply_copy(self, cohort: Cohort, grammar: Any) -> bool:
        changed = False
        mp = grammar.mapping_prefix if grammar else '@'
        for r in list(cohort.active_readings()):
            if self._matches_reading(r, grammar):
                nr = r.clone(parent_cohort=cohort)
                for t in self.action_tags:
                    nr.add_tag(t, mapping_prefix=mp)
                nr.changed = True
                nr.trace.append(self.name)
                cohort.append_reading(nr)
                changed = True
        return changed

    def _apply_addcohort(self, window: SingleWindow, c_idx: int, grammar: Any) -> Tuple[bool, int]:
        # action_tags: ["<word>", "base", tag1, ...]
        if not self.action_tags:
            return False, 0
        word = self.action_tags[0]
        base = self.action_tags[1] if len(self.action_tags) > 1 else '""'
        tags = self.action_tags[2:] if len(self.action_tags) > 2 else []

        new_c = Cohort(wordform=word, parent_window=window)
        r = Reading(baseform=base, tags=tags, parent_cohort=new_c)
        r.changed = True
        r.trace.append(self.name)
        new_c.append_reading(r)

        if self.direction == "BEFORE":
            window.cohorts.insert(c_idx, new_c)
            return True, 1
        else:
            window.cohorts.insert(c_idx + 1, new_c)
            return True, 0

    def __repr__(self) -> str:
        ctx = " ".join(str(c) for c in self.context_tests)
        return f"Rule({self.name}: {self.type} {self.target} {ctx})"
