"""Stream parsing and serialization for VISL CG-3 format."""

import sys
import re
from typing import Iterator, List, Optional, TextIO, Tuple
from pycg3.cohort import Cohort, Reading, SingleWindow
from pycg3.set_def import SetDefinition


COHORT_RE = re.compile(r'^\s*\"<([^>]+)>\"(.*)$')
READING_RE = re.compile(r'^(\s+)(;?\s*)\"([^\"]*)\"(.*)$')
STREAM_CMD_RE = re.compile(r'^<STREAMCMD:([A-Z]+)(?::([^>]*))?>$')


def split_tags(tag_str: str) -> List[str]:
    """Split a string of tags handling quoted tokens and nested composite tags."""
    tags = []
    current = []
    in_quote = False
    quote_char = ''
    paren_depth = 0
    i = 0
    n = len(tag_str)

    while i < n:
        c = tag_str[i]
        if in_quote:
            current.append(c)
            if c == quote_char and (i == 0 or tag_str[i-1] != '\\'):
                in_quote = False
        else:
            if c in ('"', "'"):
                in_quote = True
                quote_char = c
                current.append(c)
            elif c == '(':
                paren_depth += 1
                current.append(c)
            elif c == ')':
                if paren_depth > 0:
                    paren_depth -= 1
                current.append(c)
            elif c.isspace() and paren_depth == 0:
                if current:
                    tags.append(''.join(current))
                    current.clear()
            else:
                current.append(c)
        i += 1

    if current:
        tags.append(''.join(current))

    return tags


def split_all_mappings(cohort: Cohort, mapping_prefix: str = '@'):
    """
    In VISL CG-3, if a reading has multiple mapping tags (e.g. starting with @),
    it is split into separate readings, one per mapping tag.
    """
    new_readings = []
    for r in cohort.readings:
        mapping_tags = [t for t in r.tags if t.startswith(mapping_prefix)]
        if len(mapping_tags) > 1:
            base_tags = [t for t in r.tags if not t.startswith(mapping_prefix)]
            for mt in mapping_tags:
                nr = Reading(baseform=r.baseform, tags=base_tags + [mt], parent_cohort=cohort)
                nr.deleted = r.deleted
                nr.changed = r.changed
                nr.trace = list(r.trace)
                nr.sub_readings = [s.clone(parent_cohort=cohort) for s in r.sub_readings]
                new_readings.append(nr)
        else:
            new_readings.append(r)
    cohort.readings = new_readings


def parse_stream(
    stream: TextIO,
    delimiters_set: Optional[SetDefinition] = None,
    mapping_prefix: str = '@',
    hard_limit: int = 500
) -> Iterator[SingleWindow]:
    """
    Parse a CG-3 plaintext input stream lazily into SingleWindow objects.
    Yields one SingleWindow at a time, keeping memory minimal.
    """
    current_window = SingleWindow()
    current_cohort: Optional[Cohort] = None
    reading_stack: List[Tuple[int, Reading]] = []
    pending_text: List[str] = []
    line_number = 0
    cohort_counter = 0

    def finish_cohort(c: Cohort):
        split_all_mappings(c, mapping_prefix=mapping_prefix)

    def finish_window():
        nonlocal current_window, current_cohort, reading_stack
        if current_cohort is not None:
            finish_cohort(current_cohort)
            current_window.append_cohort(current_cohort)
            current_cohort = None
            reading_stack.clear()
        if pending_text:
            current_window.text_after.extend(pending_text)
            pending_text.clear()
        win = current_window
        current_window = SingleWindow()
        return win

    for raw_line in stream:
        line_number += 1
        line = raw_line.rstrip('\r\n')
        stripped = line.strip()

        # Handle stream commands
        cmd_match = STREAM_CMD_RE.match(stripped)
        if cmd_match:
            cmd = cmd_match.group(1)
            arg = cmd_match.group(2)
            if cmd == 'FLUSH':
                if current_window.cohorts or current_cohort:
                    win = finish_window()
                    win.flush_after = True
                    yield win
                else:
                    win = SingleWindow()
                    win.text_after.append(line)
                    win.flush_after = True
                    yield win
                continue
            elif cmd == 'EXIT':
                if current_window.cohorts or current_cohort:
                    yield finish_window()
                return
            elif cmd == 'SETVAR':
                if arg:
                    for vpart in arg.split(','):
                        if '=' in vpart:
                            k, v = vpart.split('=', 1)
                            current_window.variables[k] = v
                        else:
                            current_window.variables[vpart] = '1'
                pending_text.append(line)
                continue
            elif cmd == 'REMVAR':
                if arg:
                    for vpart in arg.split(','):
                        current_window.variables.pop(vpart, None)
                pending_text.append(line)
                continue
            else:
                pending_text.append(line)
                continue

        # Cohort line
        cohort_match = COHORT_RE.match(line)
        if cohort_match:
            if current_cohort is not None:
                finish_cohort(current_cohort)
                current_window.append_cohort(current_cohort)
                is_delim = False
                if delimiters_set and delimiters_set.matches_cohort_normal(current_cohort):
                    is_delim = True
                current_cohort = None
                reading_stack.clear()

                if is_delim or len(current_window.cohorts) >= hard_limit:
                    yield finish_window()

            word = cohort_match.group(1)
            rest = cohort_match.group(2).strip()
            wordform_tag = f'"<{word}>"'
            untouchable = split_tags(rest) if rest else []

            cohort_counter += 1
            current_cohort = Cohort(
                wordform=wordform_tag,
                untouchable_tags=untouchable,
                text_before=list(pending_text),
                line_number=line_number,
                global_number=cohort_counter
            )
            pending_text.clear()
            continue

        # Reading line
        if (line.startswith(' ') or line.startswith('\t')) and current_cohort is not None:
            r_match = READING_RE.match(line)
            if r_match:
                indent_str = r_match.group(1)
                del_str = r_match.group(2).strip()
                base = r_match.group(3)
                rest_tags = r_match.group(4).strip()

                indent_level = len(indent_str.replace('\t', '    '))
                baseform_tag = f'"{base}"'
                tags = split_tags(rest_tags) if rest_tags else []

                reading = Reading(baseform=baseform_tag, tags=tags, parent_cohort=current_cohort)
                if del_str.startswith(';'):
                    reading.deleted = True

                while reading_stack and indent_level <= reading_stack[-1][0]:
                    reading_stack.pop()

                if reading_stack:
                    parent_reading = reading_stack[-1][1]
                    parent_reading.sub_readings.append(reading)
                else:
                    if reading.deleted:
                        current_cohort.deleted_readings.append(reading)
                    else:
                        current_cohort.append_reading(reading)

                reading_stack.append((indent_level, reading))
                continue

        pending_text.append(line)

    if current_cohort is not None:
        finish_cohort(current_cohort)
        current_window.append_cohort(current_cohort)
    if pending_text:
        current_window.text_after.extend(pending_text)
    if current_window.cohorts or current_window.text_after:
        yield current_window
