"""Contextual tests, ported from vislcg3's runContextualTest / runSingleTest / doesSetMatchCohort*.

The odd corners are deliberate: they are what the real engine does and real grammars depend on them.
  * the window has a begin cohort (index 0, tag >>>) in front of the real cohorts; the last real cohort answers to <<<
  * 0* scans both ways, alternating: one to the left, one to the right, two to the left, ...
  * NOT is applied to the set match of every cohort tested - and to the BARRIER match of a NOT test as well
  * a scan with * stops at the first cohort that matches the target (even if a LINKed test then fails)
"""

from typing import Any, Optional, Tuple
from pycg3.cohort import SingleWindow, Cohort
from pycg3.set_def import SetDefinition

TRV_BREAK, TRV_BARRIER, TRV_BREAK_DEFAULT = 1, 2, 4


class _Ctx:
    """The dSMC_Context of the C++ code: state shared by the set matches of one cohort test."""
    __slots__ = ('test', 'not_', 'matched_target', 'matched_tests', 'did_test', 'in_barrier', 'window', 'index')

    def __init__(self, test=None, not_=False, in_barrier=False, window=None, index=0):
        self.test = test
        self.not_ = not_
        self.matched_target = False
        self.matched_tests = False
        self.did_test = False
        self.in_barrier = in_barrier
        self.window = window
        self.index = index


class ContextualTest:
    """One contextual test with its barriers and LINKed tests."""

    __slots__ = ('target', 'offset', 'scan_first', 'scan_all', 'careful', 'not_', 'negate', 'absolute',
                 'self_', 'no_barrier', 'all_', 'none_', 'barrier', 'cbarrier', 'linked_test', 'raw_pos', 'ors')

    def __init__(self, target: SetDefinition, offset: int = 0, scan_first: bool = False, scan_all: bool = False,
                 careful: bool = False, not_: bool = False, negate: bool = False, absolute: bool = False,
                 self_: bool = False, no_barrier: bool = False, all_: bool = False, none_: bool = False,
                 barrier: Optional[SetDefinition] = None, cbarrier: Optional[SetDefinition] = None,
                 linked_test: Optional['ContextualTest'] = None, raw_pos: str = ""):
        self.target = target
        self.offset = offset
        self.scan_first = scan_first
        self.scan_all = scan_all
        self.careful = careful
        self.not_ = not_
        self.negate = negate
        self.absolute = absolute
        self.self_ = self_
        self.no_barrier = no_barrier
        self.all_ = all_
        self.none_ = none_
        self.barrier = barrier
        self.cbarrier = cbarrier
        self.linked_test = linked_test
        self.raw_pos = raw_pos
        self.ors: list = []        # (test) OR (test): holds if any alternative does

    @property
    def is_scan(self) -> bool:
        return self.scan_first or self.scan_all

    # -- entry point -------------------------------------------------------------------------
    def evaluate(self, window: SingleWindow, cohort_idx: int, grammar: Any = None, reading: Any = None) -> bool:
        """True if the test holds for the real cohort at window.cohorts[cohort_idx]."""
        return _run_contextual_test(window, cohort_idx + 1, self)

    def __repr__(self) -> str:
        return "(%s%s%s)" % ("NEGATE " if self.negate else "", "NOT " if self.not_ else "", self.raw_pos)


# -- set matching (doesSetMatchCohortNormal / Careful) -------------------------------------------
def _test_linked(window: SingleWindow, index: int, ctx: _Ctx) -> bool:
    """doesSetMatchCohort_testLinked"""
    linked = ctx.test.linked_test if ctx.test is not None else None
    if linked is None:
        return True
    if not ctx.did_test:
        ctx.matched_tests = _run_contextual_test(window, index, linked)
        ctx.did_test = True
    return ctx.matched_tests


def _helper(window, index, reading, target: SetDefinition, ctx: Optional[_Ctx]) -> bool:
    """doesSetMatchCohort_helper"""
    ret = False
    if target.matches_reading(reading):
        ret = True
        if ctx is not None:
            ctx.matched_target = True
    if ret and ctx is not None and ctx.not_:
        ret = not ret
    if ret and ctx is not None and not ctx.in_barrier:
        ret = _test_linked(window, index, ctx)
    return ret


def _wread(cohort):
    """The reading that stands for the cohort itself: its word form and the static tags after it."""
    if cohort._wread is None:
        from pycg3.cohort import Reading
        cohort._wread = Reading(baseform="", tags=list(cohort.untouchable_tags), parent_cohort=cohort)
    return cohort._wread


def _match_normal(window, index, target: SetDefinition, ctx: _Ctx) -> bool:
    cohort = window.virtual(index)
    ret = False
    if cohort.untouchable_tags and not ctx.in_barrier:
        ret = _helper(window, index, _wread(cohort), target, ctx)
        if ret and ctx.did_test:
            return ret
    for reading in cohort.readings:
        if reading.deleted:
            continue
        if _helper(window, index, reading, target, ctx):
            ret = True
        if ret and (ctx.test is None or ctx.test.linked_test is None or ctx.did_test):
            return ret
    if not ctx.matched_target and ctx.not_:
        ret = _test_linked(window, index, ctx)
    return ret


def _match_careful(window, index, target: SetDefinition, ctx: _Ctx) -> bool:
    cohort = window.virtual(index)
    ret = False
    for reading in cohort.readings:
        if reading.deleted:
            continue
        ret = _helper(window, index, reading, target, ctx)
        if not ret:
            break
    if not ctx.matched_target and ctx.not_:
        ret = _test_linked(window, index, ctx)
    return ret


# -- one cohort (runSingleTest) ------------------------------------------------------------------
def _single(window: SingleWindow, index: int, test: ContextualTest, rvs: int) -> Tuple[Optional[int], bool, int]:
    """Returns (cohort index or None, retval, rvs)."""
    if index < 0 or index > len(window.cohorts):
        return None, False, rvs | TRV_BREAK
    ctx = _Ctx(test=test, not_=test.not_, window=window, index=index)
    if test.careful:
        ret = _match_careful(window, index, test.target, ctx)
        if not ctx.matched_target and test.scan_first:
            ctx.did_test = True
            _match_normal(window, index, test.target, ctx)
    else:
        ret = _match_normal(window, index, test.target, ctx)

    if ctx.matched_target and test.scan_first:
        rvs |= TRV_BREAK
    elif not (test.scan_all or test.scan_first):
        rvs |= TRV_BREAK | TRV_BREAK_DEFAULT
    broken = bool(rvs & TRV_BREAK)

    if test.barrier is not None:
        bctx = _Ctx(test=None, not_=test.not_, in_barrier=True, window=window, index=index)
        if _match_normal(window, index, test.barrier, bctx):
            rvs |= TRV_BREAK | TRV_BARRIER
            rvs &= ~TRV_BREAK_DEFAULT
    if test.cbarrier is not None:
        bctx = _Ctx(test=None, not_=test.not_, in_barrier=True, window=window, index=index)
        if _match_careful(window, index, test.cbarrier, bctx):
            rvs |= TRV_BREAK | TRV_BARRIER
            rvs &= ~TRV_BREAK_DEFAULT
    if ctx.matched_target and ret:
        rvs |= TRV_BREAK
    if not broken and (rvs & TRV_BARRIER) and test.self_ and test.no_barrier:
        rvs &= ~(TRV_BREAK | TRV_BARRIER)
    return index, ret, rvs


# -- a whole test (runContextualTest) ---------------------------------------------------------------
def _run_contextual_test(window: SingleWindow, position: int, test: ContextualTest) -> bool:
    if test.ors:
        found = any(_run_contextual_test(window, position, alt) for alt in test.ors)
        return (not found) if test.negate else found
    size = len(window.cohorts) + 1                     # begin cohort + real cohorts
    retval = True
    if test.absolute:
        pos = size + test.offset if test.offset < 0 else test.offset
    else:
        pos = position + test.offset
    cohort: Optional[int] = pos if 0 <= pos < size else None

    if cohort is None:
        retval = False
    elif test.offset == 0 and test.is_scan:                      # 0*: both directions, alternating
        left = right = True
        lpos = rpos = pos
        rvs = 0
        if test.self_:
            cohort, retval, rvs = _single(window, cohort, test, rvs)
            if not retval and (rvs & TRV_BREAK_DEFAULT):
                rvs &= ~(TRV_BREAK | TRV_BREAK_DEFAULT)
        if (rvs & TRV_BREAK) and retval:
            pass
        else:
            i = 1
            done = False
            while (left or right) and not done:
                if left:
                    rvs = 0
                    cohort, retval, rvs = _single(window, lpos - i, test, rvs)
                    if (rvs & TRV_BREAK) and retval:
                        break
                    elif rvs & TRV_BREAK:
                        left = False
                        if test.not_:
                            right = False
                    elif lpos - i == 0:
                        left = False
                if right:
                    rvs = 0
                    cohort, retval, rvs = _single(window, rpos + i, test, rvs)
                    if (rvs & TRV_BREAK) and retval:
                        break
                    elif rvs & TRV_BREAK:
                        right = False
                        if test.not_:
                            left = False
                    elif rpos + i == size - 1:
                        right = False
                i += 1
    else:                                                        # one direction (or just the one cohort)
        step = -1 if test.offset < 0 else (1 if test.offset > 0 else 0)
        idx = cohort
        seen = 0
        rvs = 0
        nc: Optional[int] = cohort
        if test.self_:
            seen += 1
            nc, retval, rvs = _single(window, position, test, rvs)
            if not retval and (rvs & TRV_BREAK_DEFAULT):
                rvs &= ~(TRV_BREAK | TRV_BREAK_DEFAULT)
        if not (rvs & TRV_BREAK):
            while idx is not None and 0 <= idx < size:
                seen += 1
                nc, retval, rvs = _single(window, idx, test, rvs)
                if test.all_ and not retval:
                    nc = None
                    break
                if test.none_ and retval:
                    nc = None
                    break
                if rvs & TRV_BREAK:
                    break
                idx = idx + step if step else None
        if seen == 0:
            retval = False
        if not retval and test.none_:
            retval = True
            nc = cohort
        cohort = nc

    if cohort is None:
        retval = False
    if cohort is None and test.not_ and test.linked_test is None:
        retval = not retval
    if test.negate:
        retval = not retval
    return retval
