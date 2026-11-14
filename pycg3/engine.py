"""Execution engine for VISL CG-3."""

import sys
from collections import deque
from typing import Iterator, Optional, TextIO, Union
from pycg3.grammar import Grammar
from pycg3.cohort import SingleWindow
from pycg3.stream import parse_stream
from pycg3 import context


class Disambiguator:
    """Executes a VISL CG-3 grammar over a stream of SingleWindows."""

    def __init__(self, grammar: Grammar, max_iterations: int = 50, trace: bool = False,
                 dep_no_crossing: bool = False, dep_allow_loops: bool = False, num_windows: int = 2,
                 always_span: bool = False):
        self.num_windows = num_windows      # --num-windows: windows kept behind and read ahead for tests with W < >
        self.always_span = always_span      # --always-span: every scan goes across window boundaries
        self.grammar = grammar
        grammar.trace_mode = trace          # as with vislcg3 -t, readings that rules hit differently stay apart
        grammar.dep_block_crossing = dep_no_crossing        # --dep-no-crossing
        grammar.dep_block_loops = not dep_allow_loops       # --dep-allow-loops
        self.max_iterations = max_iterations
        self._relation_map: dict = {}         # input ID:n -> cohort, for the R:name:n tags of the input

    def run_window(self, window: SingleWindow, num_sections: Optional[int] = None) -> SingleWindow:
        """Run all sections on a single window."""
        context.set_always_span(self.always_span)
        window.mark_end()
        window.resolve_input_dependencies()
        if getattr(self.grammar, 'has_relations', False):
            window.resolve_input_relations(self._relation_map)
        # 1. BEFORE-SECTIONS
        for rule in self.grammar.before_sections:
            rule.apply_to_window(window, self.grammar)

        # 2. SECTIONS. As in vislcg3, running section k means running the rules of sections 1..k, over and
        # over until a whole pass changes nothing; only then does the next section join in.
        sections_to_run = self.grammar.sections
        if num_sections is not None:
            sections_to_run = sections_to_run[:num_sections]

        rules_so_far: list = []
        for section_rules in sections_to_run:
            rules_so_far = rules_so_far + section_rules
            for _ in range(self.max_iterations):
                changed = False
                for rule in rules_so_far:
                    if rule.apply_to_window(window, self.grammar) and rule.iterates:
                        changed = True
                if not changed:
                    break

        # 3. AFTER-SECTIONS
        for rule in self.grammar.after_sections:
            rule.apply_to_window(window, self.grammar)

        return window

    def run_stream(
        self,
        stream: TextIO,
        num_sections: Optional[int] = None
    ) -> Iterator[SingleWindow]:
        """
        Streamingly process windows from input stream.

        Like vislcg3 this keeps a few windows around the one being run, so that contextual tests with W, < and > can
        look into them: the windows already run (the last `num_windows` of them) and the ones read ahead (`num_windows`
        full ones, and the begin cohort of the one after, which is there as soon as it has been started). A window
        is handed on once it falls out of the windows behind. FLUSH in the input runs and hands on everything.
        """
        mp = self.grammar.mapping_prefix if self.grammar else '@'
        ahead = self.num_windows + 2            # vislcg3 runs a window when this many are waiting, the new one included
        self.grammar.dep_has_spanned = False    # becomes True when a dependency goes from one window to another
        counter = 0
        dep_on = False                          # vislcg3 starts printing #n->m once dependencies are in play (read, or a rule tried to attach)
        waiting: deque = deque()                # read, not run yet
        behind: deque = deque()                 # run, not handed on yet

        def hand(done):
            done.dep_spanned = self.grammar.dep_has_spanned       # numbered globally if a dependency has spanned by the time it is written
            done.dep_print = dep_on                               # ... and only written with #n->m if dependencies were in play by then
            return done

        def run_first(phantom: bool):
            nonlocal dep_on
            out = []
            while len(behind) > self.num_windows:       # vislcg3 writes the window that falls out of the ones behind before it runs the next
                done = behind.popleft()
                if behind:
                    behind[0].previous = None
                out.append(hand(done))
            win = waiting.popleft()
            hidden = None
            if phantom and waiting:                 # the begin cohort of the window being started is already there
                hidden = waiting[-1]
                stub = SingleWindow()
                stub.begin = hidden.begin
                stub.previous, stub.next = waiting[-2] if len(waiting) > 1 else win, None
                stub.previous.next = stub
                waiting[-1] = stub
            if behind:
                win.previous = behind[-1]
                behind[-1].next = win
            self.run_window(win, num_sections=num_sections)
            dep_on = dep_on or win.has_dep
            if hidden is not None:
                waiting[-1] = hidden
                hidden.previous.next = hidden
            win.next = waiting[0] if waiting else None
            behind.append(win)
            return out

        for window in parse_stream(stream, delimiters_set=self.grammar.delimiters, mapping_prefix=mp,
                                    has_relations=getattr(self.grammar, 'has_relations', False),
                                    has_dep=getattr(self.grammar, 'has_dep', False)):
            counter += 1
            if any(c.dep_in is not None for c in window.cohorts):
                dep_on = True
            window.number = counter
            window.mark_end()
            if waiting:
                waiting[-1].next = window
                window.previous = waiting[-1]
            elif behind:
                behind[-1].next = window
                window.previous = behind[-1]
            waiting.append(window)
            flush = window.flush_after
            while len(waiting) >= ahead and not flush:
                yield from run_first(True)
            if flush:
                while waiting:
                    yield from run_first(False)
                while behind:
                    yield hand(behind.popleft())
        while waiting:
            yield from run_first(False)
        while behind:
            yield hand(behind.popleft())

    def run_text(
        self,
        input_text: str,
        num_sections: Optional[int] = None,
        show_rules: bool = False,
        trace: bool = False,
        pipe_deleted: bool = False
    ) -> str:
        """Run grammar on input string and return formatted output string."""
        import io
        stream = io.StringIO(input_text)
        windows = list(self.run_stream(stream, num_sections=num_sections))
        out_parts = [w.to_text(show_rules=show_rules, trace=trace, pipe_deleted=pipe_deleted)
                     for w in windows]
        return "\n".join(out_parts) + ("\n" if out_parts else "")
