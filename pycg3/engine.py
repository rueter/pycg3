"""Execution engine for VISL CG-3."""

import sys
from typing import Iterator, Optional, TextIO, Union
from pycg3.grammar import Grammar
from pycg3.cohort import SingleWindow
from pycg3.stream import parse_stream


class Disambiguator:
    """Executes a VISL CG-3 grammar over a stream of SingleWindows."""

    def __init__(self, grammar: Grammar, max_iterations: int = 50):
        self.grammar = grammar
        self.max_iterations = max_iterations

    def run_window(self, window: SingleWindow, num_sections: Optional[int] = None) -> SingleWindow:
        """Run all sections on a single window."""
        # 1. BEFORE-SECTIONS
        for rule in self.grammar.before_sections:
            rule.apply_to_window(window, self.grammar)

        # 2. SECTIONS
        sections_to_run = self.grammar.sections
        if num_sections is not None:
            sections_to_run = sections_to_run[:num_sections]

        for section_rules in sections_to_run:
            iteration = 0
            while iteration < self.max_iterations:
                iteration += 1
                section_changed = False
                for rule in section_rules:
                    rule_changed = rule.apply_to_window(window, self.grammar)
                    if rule_changed:
                        section_changed = True
                if not section_changed:
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
