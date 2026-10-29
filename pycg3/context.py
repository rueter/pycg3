"""Contextual test evaluation for VISL CG-3."""

import re
from typing import List, Optional, Any, Tuple
from pycg3.cohort import Cohort, Reading, SingleWindow
from pycg3.set_def import SetDefinition


class ContextualTest:
    """Represents a single contextual test or link chain."""

    __slots__ = (
        'is_not',
        'is_negate',
        'is_scan',
        'is_careful',
        'is_self_barrier',
        'is_self_no_barrier',
        'is_absolute',
        'offset',
        'target',
        'barrier',
        'cbarrier',
        'linked_test',
        'dep_dir',
        'raw_pos'
    )

    def __init__(
        self,
        target: Any,
        offset: int = 0,
        is_scan: bool = False,
        is_careful: bool = False,
        is_not: bool = False,
        is_negate: bool = False,
        is_absolute: bool = False,
        barrier: Optional[Any] = None,
        cbarrier: Optional[Any] = None,
        linked_test: Optional['ContextualTest'] = None,
        raw_pos: str = ""
    ):
        self.target = target
        self.offset = offset
        self.is_scan = is_scan
        self.is_careful = is_careful
        self.is_not = is_not
        self.is_negate = is_negate
        self.is_absolute = is_absolute
        self.is_self_barrier = False
        self.is_self_no_barrier = False
        self.barrier = barrier
        self.cbarrier = cbarrier
        self.linked_test = linked_test
        self.dep_dir: Optional[str] = None
        self.raw_pos = raw_pos

    def evaluate(
        self,
        window: SingleWindow,
        cohort_idx: int,
        grammar: Any,
        reading: Optional[Reading] = None
    ) -> bool:
        """Evaluate this contextual test relative to cohort at index cohort_idx."""
        res, _ = self._eval_internal(window, cohort_idx, grammar, reading)
        if self.is_negate:
            res = not res
        return res

    def _eval_internal(
        self,
        window: SingleWindow,
        cohort_idx: int,
        grammar: Any,
        reading: Optional[Reading] = None
    ) -> Tuple[bool, Optional[int]]:
        cohorts = window.cohorts
        num_cohorts = len(cohorts)

        # Check self-barrier on origin if requested
        if self.is_self_barrier and not self.is_self_no_barrier:
            if 0 <= cohort_idx < num_cohorts:
                origin_c = cohorts[cohort_idx]
                if self.barrier and self._matches_cohort(self.barrier, origin_c, grammar, False):
                    return False, None
                if self.cbarrier and self._matches_cohort(self.cbarrier, origin_c, grammar, True):
                    return False, None

        # Absolute position: @1 or @-1
        if self.is_absolute:
            target_idx = (self.offset - 1) if self.offset > 0 else (num_cohorts + self.offset)
            if 0 <= target_idx < num_cohorts:
                matches = self._check_target(cohorts[target_idx], grammar)
                if self.is_not:
                    matches = not matches
                if matches:
                    if self.linked_test:
                        link_ok = self.linked_test.evaluate(window, target_idx, grammar)
                        return (link_ok, target_idx if link_ok else None)
                    return True, target_idx
            else:
                if self.is_not and not self.linked_test:
                    return True, None
            return False, None

        # Dependency test
        if self.dep_dir:
            curr_c = cohorts[cohort_idx]
            target_indices = []
            if self.dep_dir == 'p':
                for r in curr_c.active_readings():
                    if r.parent_id is not None:
                        for idx, other_c in enumerate(cohorts):
                            if other_c.global_number == r.parent_id:
                                target_indices.append(idx)
            elif self.dep_dir == 'c':
                for idx, other_c in enumerate(cohorts):
                    for r in other_c.active_readings():
                        if r.parent_id == curr_c.global_number:
                            target_indices.append(idx)
                            break

            for tidx in target_indices:
                matches = self._check_target(cohorts[tidx], grammar)
                if self.is_not:
                    matches = not matches
                if matches:
                    if self.linked_test:
                        if self.linked_test.evaluate(window, tidx, grammar):
                            return True, tidx
                    else:
                        return True, tidx
            if not target_indices and self.is_not and not self.linked_test:
                return True, None
            return False, None

        # Non-scanning test: fixed offset (0, 1, -1, 2, -2)
        if not self.is_scan:
            target_idx = cohort_idx + self.offset
            if 0 <= target_idx < num_cohorts:
                target_c = cohorts[target_idx]
                matches = self._check_target(target_c, grammar)
                if self.is_not:
                    matches = not matches
                if matches:
                    if self.linked_test:
                        link_ok = self.linked_test.evaluate(window, target_idx, grammar)
                        return (link_ok, target_idx if link_ok else None)
                    return True, target_idx
                return False, None
            else:
                # Out of bounds
                if self.is_not and not self.linked_test:
                    return True, None
                return False, None

        # Scanning test: *1, *-1, *0
        step = 1 if self.offset >= 0 else -1
        start_idx = cohort_idx + (self.offset if self.offset != 0 else step)

        curr_idx = start_idx
        while 0 <= curr_idx < num_cohorts:
            curr_c = cohorts[curr_idx]

            # Check barriers
            if self.barrier and self._matches_cohort(self.barrier, curr_c, grammar, careful=False):
                matches = self._check_target(curr_c, grammar)
                if self.is_not:
                    matches = not matches
                if matches:
                    if self.linked_test:
                        if self.linked_test.evaluate(window, curr_idx, grammar):
                            return True, curr_idx
                    else:
                        return True, curr_idx
                if self.is_not and not self.linked_test:
                    return True, None
                return False, None

            if self.cbarrier and self._matches_cohort(self.cbarrier, curr_c, grammar, careful=True):
                matches = self._check_target(curr_c, grammar)
                if self.is_not:
                    matches = not matches
                if matches:
                    if self.linked_test:
                        if self.linked_test.evaluate(window, curr_idx, grammar):
                            return True, curr_idx
                    else:
                        return True, curr_idx
                if self.is_not and not self.linked_test:
                    return True, None
                return False, None

            matches = self._check_target(curr_c, grammar)
            if self.is_not:
                matches = not matches

            if matches:
                if self.linked_test:
                    if self.linked_test.evaluate(window, curr_idx, grammar):
                        return True, curr_idx
                else:
                    return True, curr_idx

            curr_idx += step

        if self.is_not and not self.linked_test:
            return True, None

        return False, None

    def _check_target(self, cohort: Cohort, grammar: Any) -> bool:
        return self._matches_cohort(self.target, cohort, grammar, self.is_careful)

    def _matches_cohort(self, target: Any, cohort: Cohort, grammar: Any, careful: bool) -> bool:
        if isinstance(target, SetDefinition):
            if careful:
                return target.matches_cohort_careful(cohort, grammar)
            else:
                return target.matches_cohort_normal(cohort, grammar)
        elif isinstance(target, str):
            if grammar and target in grammar.sets:
                s = grammar.sets[target]
                return s.matches_cohort_careful(cohort, grammar) if careful else s.matches_cohort_normal(cohort, grammar)
            from pycg3.tag import TagPattern
            pat = TagPattern(target)
            if pat.is_any:
                return True
            readings = cohort.active_readings()
            if not readings and not cohort.untouchable_tags:
                return False
            if careful:
                if not readings:
                    return False
                for r in readings:
                    if not any(pat.matches_tag(t) for t in r.all_tags()):
                        return False
                return True
            else:
                for ut in cohort.untouchable_tags:
                    if pat.matches_tag(ut):
                        return True
                for r in readings:
                    if any(pat.matches_tag(t) for t in r.all_tags()):
                        return True
                return False
        return False

    def __repr__(self) -> str:
        neg = "NEGATE " if self.is_negate else ("NOT " if self.is_not else "")
        scan = "*" if self.is_scan else ""
        care = "C" if self.is_careful else ""
        b = f" BARRIER {self.barrier}" if self.barrier else ""
        cb = f" CBARRIER {self.cbarrier}" if self.cbarrier else ""
        link = f" LINK {self.linked_test}" if self.linked_test else ""
        return f"({neg}{self.offset}{scan}{care} {self.target}{b}{cb}{link})"
