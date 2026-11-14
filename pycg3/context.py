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
    __slots__ = ('test', 'not_', 'matched_target', 'matched_tests', 'did_test', 'in_barrier', 'window', 'index',
                 'rejected')

    def __init__(self, test=None, not_=False, in_barrier=False, window=None, index=0):
        self.test = test
        self.not_ = not_
        self.matched_target = False
        self.matched_tests = False
        self.did_test = False
        self.in_barrier = in_barrier
        self.window = window
        self.index = index
        self.rejected = False       # SETPARENT: the chain failed on a candidate that cannot be attached to


class ContextualTest:
    """One contextual test with its barriers and LINKed tests."""

    __slots__ = ('target', 'offset', 'scan_first', 'scan_all', 'careful', 'not_', 'negate', 'absolute',
                 'self_', 'no_barrier', 'all_', 'none_', 'barrier', 'cbarrier', 'linked_test', 'raw_pos', 'ors', 'sub',
                 'dep', 'attach', 'relation', 'span_left', 'span_right', 'span_both')

    def __init__(self, target: SetDefinition, offset: int = 0, scan_first: bool = False, scan_all: bool = False,
                 careful: bool = False, not_: bool = False, negate: bool = False, absolute: bool = False,
                 self_: bool = False, no_barrier: bool = False, all_: bool = False, none_: bool = False,
                 barrier: Optional[SetDefinition] = None, cbarrier: Optional[SetDefinition] = None,
                 linked_test: Optional['ContextualTest'] = None, raw_pos: str = "", sub: Optional[int] = None,
                 dep: Optional[str] = None, attach: bool = False, relation: Optional[str] = None,
                 span_left: bool = False, span_right: bool = False, span_both: bool = False):
        self.span_left = span_left      # < : the test may go on into the previous window
        self.span_right = span_right    # > : ... into the next window
        self.span_both = span_both      # W : ... into either
        self.relation = relation    # r:name - the cohorts the relation `name` points to (r:* any relation)
        self.dep = dep              # p parent, c children, s siblings, pp ancestors, cc descendants (dependency tests)
        self.attach = attach        # the A flag: this test's cohort is the one a SETPARENT / SETCHILD attaches to
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
        self.sub = sub
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
        att = _ATTACH
        if att is not None and ctx.test is not None and not ctx.in_barrier:
            # the end of the chain: the cohort to attach to must be a possible one, or the scan goes on
            cand = att.marked if att.marked is not None else window.virtual(index)
            att.matched = True
            if not att.valid(cand):
                att.rejections += 1
                return False
            att.final = cand
        return True
    if not ctx.did_test:
        ctx.matched_tests = _run_contextual_test(window, index, linked)
        ctx.did_test = True
    return ctx.matched_tests


class AttachState:
    """What a SETPARENT / SETCHILD rule is attaching while its TO tests run: the tests report the cohort to attach
    to, and a candidate that would make a loop (or is the cohort itself) counts as a test that did not match, so a
    scan goes on to the next cohort (as in vislcg3)."""
    __slots__ = ('window', 'cohort', 'as_child', 'allow_loop', 'marked', 'final', 'matched', 'rejections',
                 'allow_cross', 'block_crossing', 'block_loops', 'check')

    def __init__(self, window, cohort, as_child=True, allow_loop=False, allow_cross=False, block_crossing=False,
                 block_loops=True, check=True):
        self.window = window
        self.cohort = cohort          # the cohort the rule is on
        self.as_child = as_child      # SETPARENT: it becomes the child of the cohort found; SETCHILD: the parent
        self.allow_loop = allow_loop or not block_loops
        self.allow_cross = allow_cross
        self.block_crossing = block_crossing
        self.block_loops = block_loops
        self.check = check            # relations may point anywhere, the cohort itself included
        self.marked: Optional[Cohort] = None  # the cohort whose test has the A flag
        self.final: Optional[Cohort] = None   # the cohort the last LINKed test ended on
        self.matched = False                  # the tests led somewhere, even if only to a cohort that cannot be attached
        self.rejections = 0                   # how many candidates were turned down as self or loop

    def _crosses(self, parent, child) -> bool:
        """wouldParentChildCross, quirks included: it only looks at the parent's parent and what that one hangs on."""
        a, b = self.window.index_of(parent), self.window.index_of(child)
        if a < 0 or b < 0:                      # (a dependency from one window to another is not tested for crossing)
            return False
        mn, mx = min(a, b), max(a, b)
        if mx - mn < 2:
            return False
        grand = parent.dep_parent
        if grand is not None and grand.dep_parent is not None:
            top = self.window.index_of(grand.dep_parent)
            if top < mn or top > mx:
                return True
        return False

    def valid(self, other: Cohort) -> bool:
        if not self.check:
            return True
        if other is self.cohort or other.parent_window is None:
            return False
        # the child must not be an ancestor of the parent
        child, parent = (self.cohort, other) if self.as_child else (other, self.cohort)
        if not self.allow_loop and child.dep_parent is not parent:
            node, seen = parent, set()
            while node is not None and id(node) not in seen:          # a loop higher up in the tree (in the input) does not block
                if node is child:
                    return False
                seen.add(id(node))
                node = node.dep_parent
        if self.block_crossing and not self.allow_cross and self._crosses(parent, child):
            return False
        return True


_ATTACH: Optional[AttachState] = None
_SEEN_BARRIER = False                # a BARRIER / CBARRIER stopped a scan (the SETPARENT loop does not go on after one)
_ALWAYS_SPAN = False                 # --always-span: scans go across window boundaries whatever the position says


def reset_seen_barrier() -> None:
    global _SEEN_BARRIER
    _SEEN_BARRIER = False


def seen_barrier() -> bool:
    return _SEEN_BARRIER


def set_always_span(flag: bool) -> None:
    global _ALWAYS_SPAN
    _ALWAYS_SPAN = bool(flag)


def set_attach(state: Optional[AttachState]) -> None:
    global _ATTACH
    _ATTACH = state


def _helper(window, index, reading, target: SetDefinition, ctx: Optional[_Ctx]) -> bool:
    """doesSetMatchCohort_helper"""
    ret = False
    any_sub = False
    if ctx is not None and ctx.test is not None and ctx.test.sub is not None and not ctx.in_barrier:
        if ctx.test.sub == '*':
            any_sub = reading is not None and hasattr(reading, 'sub_chain')
        elif hasattr(reading, 'sub_reading'):
            reading = reading.sub_reading(ctx.test.sub)
    if any_sub:
        hit = target.matches_reading(reading) or any(target.matches_reading(r) for r in reading.sub_chain())
    else:
        hit = reading is not None and target.matches_reading(reading)
    if hit:
        ret = True
        if ctx is not None:
            ctx.matched_target = True
    if ret and ctx is not None and ctx.not_:
        ret = not ret
    att = _ATTACH
    live = att is not None and ctx is not None and ctx.test is not None and not ctx.in_barrier
    if ret and live and ctx.test.attach:
        att.marked = window.virtual(index)
    if ret and ctx is not None and not ctx.in_barrier:
        before = att.rejections if live else 0
        ret = _test_linked(window, index, ctx)
        if not ret and live and (att.rejections != before or ctx.rejected):
            ctx.matched_target = False          # a chain that failed on a cohort that cannot be attached to does not stop a scan
            ctx.rejected = True                 # (the other readings of the cohort reuse the answer of the first one)
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


def _hit_barrier() -> None:
    global _SEEN_BARRIER
    _SEEN_BARRIER = True


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
            _hit_barrier()
            rvs |= TRV_BREAK | TRV_BARRIER
            rvs &= ~TRV_BREAK_DEFAULT
    if test.cbarrier is not None:
        bctx = _Ctx(test=None, not_=test.not_, in_barrier=True, window=window, index=index)
        if _match_careful(window, index, test.cbarrier, bctx):
            _hit_barrier()
            rvs |= TRV_BREAK | TRV_BARRIER
            rvs &= ~TRV_BREAK_DEFAULT
    if ctx.matched_target and ret:
        rvs |= TRV_BREAK
    if not broken and (rvs & TRV_BARRIER) and test.self_ and test.no_barrier:
        rvs &= ~(TRV_BREAK | TRV_BARRIER)
    return index, ret, rvs


# -- a whole test (runContextualTest) ---------------------------------------------------------------
def _dep_candidates(cohort: Cohort, kind: str, test=None, window=None) -> list:
    """The cohorts a dependency position leads to: p parent, c children, s siblings, pp ancestors, cc descendants."""
    if kind == 'r':
        ids = []
        for name, targets in cohort.relations.items():
            if test.relation == '*' or name == test.relation:
                ids.extend(t for t in targets if t not in ids)
        by_number = {}
        for w in window.chain():
            by_number[w.begin.global_number] = w.begin
            for c in w.cohorts:
                by_number[c.global_number] = c
        return [by_number[t] for t in ids if t in by_number]
    if kind == 'p':
        return [cohort.dep_parent] if cohort.dep_parent is not None else []
    if kind == 'c':
        return list(cohort.dep_children)
    if kind == 's':
        parent = cohort.dep_parent
        return [c for c in parent.dep_children if c is not cohort] if parent is not None else []
    if kind == 'pp':
        out, node = [], cohort.dep_parent
        while node is not None and node not in out:
            out.append(node)
            node = node.dep_parent
        return out
    out, stack = [], list(reversed(cohort.dep_children))          # cc: all descendants
    while stack:
        node = stack.pop()
        if node not in out:
            out.append(node)
            stack.extend(reversed(node.dep_children))
    return out


def _run_dep_test(window: SingleWindow, position: int, test: ContextualTest) -> bool:
    """A test whose position is a dependency one: (p ...) (c ...) (s ...) (pp ...) (cc ...). It holds if any of the
    cohorts it leads to matches; ALL needs every one to, NONE needs that none does (and holds when there are none)."""
    if position < 0 or position > len(window.cohorts):
        return bool(test.none_) != bool(test.negate)
    candidates = _dep_candidates(window.virtual(position), test.dep, test, window)
    matched = good = 0
    for cand in candidates:
        idx = window.index_of(cand)
        if idx < 0:
            continue
        _, ret, _ = _single(window, idx, test, 0)
        if ret:
            matched += 1
            if not (test.all_ or test.none_):
                break
        else:
            good = 1
            if test.all_:
                break
    if test.none_:
        retval = matched == 0
    elif test.all_:
        retval = bool(candidates) and not good and matched == len(candidates)
    else:
        retval = matched > 0
        if not candidates and test.not_ and test.linked_test is None:
            retval = True               # NOT p (*) holds for a cohort that has no parent: there is nothing the set could match
    return (not retval) if test.negate else retval


def _cohort_in_window(window: SingleWindow, position: int, test: ContextualTest):
    """getCohortInWindow: the window and virtual index the position of the test leads to from `position`. Going past
    the edge of the window goes on into the neighbour (index 0, its begin cohort, to the right; the last cohort to the
    left) if the test has W, > or <. The index is None when nothing is there."""
    pos = position + test.offset
    if test.absolute and (test.span_left or test.span_right):
        if window.previous is not None and test.span_left:
            window = window.previous
        elif window.next is not None and test.span_right:
            window = window.next
        else:
            return window, pos, None
    if test.absolute:
        pos = window.size + test.offset if test.offset < 0 else test.offset
    if pos >= 0:
        if pos >= window.size and (test.span_right or test.span_both) and window.next is not None:
            window = window.next
            pos = 0
    elif (test.span_left or test.span_both) and window.previous is not None:
        window = window.previous
        pos = window.size - 1
    return window, pos, (pos if 0 <= pos < window.size else None)


def _may_span(test: ContextualTest, left: bool) -> bool:
    return _ALWAYS_SPAN or test.span_both or (test.span_left if left else test.span_right)


def _step(window: SingleWindow, index: int, step: int, test: ContextualTest):
    """The next cohort to the left (step -1) or right: TopologyLeftIter / TopologyRightIter. None at the end of what the
    test may look at: a window edge it may not cross, or the end of the windows."""
    if step < 0:
        if index == 0:
            if window.previous is None or not _may_span(test, True):
                return None
            return window.previous, window.previous.size - 1
        return window, index - 1
    if index == window.size - 1:
        if window.next is None or not _may_span(test, False):
            return None
        return window.next, 0
    return window, index + 1


def _run_contextual_test(window: SingleWindow, position: int, test: ContextualTest) -> bool:
    if test.ors:
        found = any(_run_contextual_test(window, position, alt) for alt in test.ors)
        return (not found) if test.negate else found
    if test.dep:
        return _run_dep_test(window, position, test)
    org_window = window
    retval = True
    window, pos, cohort = _cohort_in_window(window, position, test)

    if cohort is None:
        retval = False
    elif test.offset == 0 and test.is_scan:                      # 0*: both directions, alternating
        left = right = window
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
            while left is not None or right is not None:
                if left is not None:
                    rvs = 0
                    cohort, retval, rvs = _single(left, lpos - i, test, rvs)
                    if (rvs & TRV_BREAK) and retval:
                        break
                    elif rvs & TRV_BREAK:
                        left = None
                        if test.not_:
                            right = None
                    elif lpos - i == 0:
                        if _may_span(test, True):
                            left = left.previous
                            if left is not None:
                                lpos = i + left.size
                        else:
                            left = None
                if right is not None:
                    rvs = 0
                    cohort, retval, rvs = _single(right, rpos + i, test, rvs)
                    if (rvs & TRV_BREAK) and retval:
                        break
                    elif rvs & TRV_BREAK:
                        right = None
                        if test.not_:
                            left = None
                    elif rpos + i == right.size - 1:
                        if _may_span(test, False):
                            right = right.next
                            rpos = -i - 1
                        else:
                            right = None
                i += 1
    else:                                                        # one direction (or just the one cohort)
        step = -1 if test.offset < 0 else (1 if test.offset > 0 else 0)
        at = (window, cohort)
        seen = 0
        rvs = 0
        nc = cohort
        if test.self_:
            seen += 1
            nc, retval, rvs = _single(org_window, position, test, rvs)
            if not retval and (rvs & TRV_BREAK_DEFAULT):
                rvs &= ~(TRV_BREAK | TRV_BREAK_DEFAULT)
        if not (rvs & TRV_BREAK):
            while at is not None:
                seen += 1
                nc, retval, rvs = _single(at[0], at[1], test, rvs)
                if test.all_ and not retval:
                    nc = None
                    break
                if test.none_ and retval:
                    nc = None
                    break
                if rvs & TRV_BREAK:
                    break
                at = _step(at[0], at[1], step, test) if step else None
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


def order_key(cohort: Cohort):
    """Where a cohort stands among all cohorts: its window, then its place in the window."""
    w = cohort.parent_window
    return (w.number, w.index_of(cohort)) if w is not None else (0, -1)
