"""Execution engine for VISL CG-3."""

import sys
from typing import Iterator, Optional, TextIO, Union
from pycg3.grammar import Grammar
from pycg3.cohort import SingleWindow
from pycg3.stream import parse_stream


class Disambiguator:
    """Executes a VISL CG-3 grammar over a stream of SingleWindows."""

    def __init__(self, grammar: Grammar, max_iterations: int = 50, trace: bool = False):
        self.grammar = grammar
        grammar.trace_mode = trace          # as with vislcg3 -t, readings that rules hit differently stay apart
        self.max_iterations = max_iterations

    def run_window(self, window: SingleWindow, num_sections: Optional[int] = None) -> SingleWindow:
        """Run all sections on a single window."""
        window.mark_end()
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
        Memory footprint remains minimal (one window at a time).
        """
        mp = self.grammar.mapping_prefix if self.grammar else '@'
        for window in parse_stream(stream, delimiters_set=self.grammar.delimiters, mapping_prefix=mp):
            yield self.run_window(window, num_sections=num_sections)

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
        out_parts = []
        for win in self.run_stream(stream, num_sections=num_sections):
            out_parts.append(win.to_text(show_rules=show_rules, trace=trace, pipe_deleted=pipe_deleted))
        return "\n".join(out_parts) + ("\n" if out_parts else "")
