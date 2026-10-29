"""Grammar parser for VISL CG-3."""

import re
from typing import Dict, List, Optional, Tuple, Any, Set
from pycg3.tag import TagPattern
from pycg3.set_def import SetDefinition, CompositeTag, SetItem
from pycg3.context import ContextualTest
from pycg3.rule import Rule
from pycg3.stream import split_tags


BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
SECTION_KEYWORDS = {
    'BEFORE-SECTIONS', 'AFTER-SECTIONS', 'NULL-SECTION',
    'SECTION', 'CONSTRAINTS', 'MAPPINGS', 'CORRECTIONS'
}


def strip_comments(text: str) -> str:
    """Strip single-line and multi-line comments from grammar text."""
    text = BLOCK_COMMENT_RE.sub('', text)
    lines = []
    for line in text.splitlines():
        in_quote = False
        quote_char = ''
        clean_chars = []
        for i, c in enumerate(line):
            if in_quote:
                clean_chars.append(c)
                if c == quote_char and (i == 0 or line[i-1] != '\\'):
                    in_quote = False
            else:
                if c in ('"', "'"):
                    in_quote = True
                    quote_char = c
                    clean_chars.append(c)
                elif c == '#':
                    break
                else:
                    clean_chars.append(c)
        lines.append(''.join(clean_chars))
    return '\n'.join(lines)


def split_statements(text: str) -> List[str]:
    """
    Split grammar text into individual statements.
    Statements end with semicolon ; OR are standalone section keywords.
    """
    statements = []
    current: List[str] = []
    in_quote = False
    quote_char = ''
    i = 0
    n = len(text)

    while i < n:
        c = text[i]
        if in_quote:
            current.append(c)
            if c == quote_char and (i == 0 or text[i-1] != '\\'):
                in_quote = False
            i += 1
        else:
            if c in ('"', "'"):
                in_quote = True
                quote_char = c
                current.append(c)
                i += 1
            elif c == ';':
                stmt = ''.join(current).strip()
                if stmt:
                    statements.append(stmt)
                current.clear()
                i += 1
            elif c == '\n' or c == '\r':
                cur_text = ''.join(current).strip()
                words = cur_text.split()
                if len(words) >= 1 and words[0].upper() in SECTION_KEYWORDS:
                    if len(words) <= 2:
                        statements.append(cur_text)
                        current.clear()
                    else:
                        statements.append(' '.join(words[:1]))
                        current = list(' '.join(words[1:]))
                current.append(c)
                i += 1
            else:
                current.append(c)
                i += 1

    remaining = ''.join(current).strip()
    if remaining:
        words = remaining.split()
        if len(words) >= 1 and words[0].upper() in SECTION_KEYWORDS:
            statements.append(' '.join(words[:1]))
            rest = ' '.join(words[1:]).strip()
            if rest:
                statements.append(rest)
        else:
            statements.append(remaining)

    return statements


def parse_contextual_test(token_str: str, grammar: Optional['Grammar'] = None) -> ContextualTest:
    """Parse a single contextual test string like 'NOT 1* (findme) BARRIER (block)'."""
    text = token_str.strip()
    if text.startswith('(') and text.endswith(')'):
        text = text[1:-1].strip()

    tokens = split_tags(text)
    if not tokens:
        return ContextualTest(target='*')

    is_not = False
    is_negate = False
    if tokens[0].upper() == 'NOT':
        is_not = True
        tokens = tokens[1:]
    elif tokens[0].upper() == 'NEGATE':
        is_negate = True
        tokens = tokens[1:]

    if not tokens:
        return ContextualTest(target='*', is_not=is_not, is_negate=is_negate)

    pos_token = tokens[0]
    tokens = tokens[1:]

    offset = 0
    is_scan = False
    is_careful = False
    is_self_barrier = False
    is_self_no_barrier = False
    is_absolute = False
    dep_dir = None

    pos_upper = pos_token.upper()

    if pos_token.startswith('@'):
        is_absolute = True
        try:
            offset = int(pos_token[1:])
        except ValueError:
            offset = 1
    elif pos_upper in ('P', 'C', 'S', 'LL', 'RL'):
        dep_dir = pos_upper.lower()
    else:
        if 'SN' in pos_upper:
            is_self_no_barrier = True
            pos_upper = pos_upper.replace('SN', '')
        elif 'S' in pos_upper:
            is_self_barrier = True
            pos_upper = pos_upper.replace('S', '')

        if grammar and 'self-no-barrier' in grammar.options:
            if is_self_no_barrier:
                is_self_no_barrier = False
                is_self_barrier = True
            elif is_self_barrier:
                is_self_barrier = False
                is_self_no_barrier = True

        if 'C' in pos_upper or 'A' in pos_upper:
            is_careful = True
            pos_upper = pos_upper.replace('C', '').replace('A', '')

        if '*' in pos_upper:
            is_scan = True
            pos_upper = pos_upper.replace('*', '')

        try:
            offset = int(pos_upper) if pos_upper and pos_upper != '-' else 0
        except ValueError:
            offset = 0

    target = None
    if tokens:
        target_token = tokens[0]
        tokens = tokens[1:]
        if target_token.startswith('(') and target_token.endswith(')'):
            inner = target_token[1:-1].strip()
            inner_tags = split_tags(inner)
            if len(inner_tags) > 1:
                target = CompositeTag([TagPattern(t) for t in inner_tags])
            elif len(inner_tags) == 1:
                target = inner_tags[0]
            else:
                target = '*'
        else:
            target = target_token
    else:
        target = '*'

    barrier = None
    cbarrier = None
    linked_test = None

    idx = 0
    while idx < len(tokens):
        tok = tokens[idx].upper()
        if tok == 'BARRIER' and idx + 1 < len(tokens):
            b_tok = tokens[idx + 1]
            barrier = b_tok[1:-1].strip() if (b_tok.startswith('(') and b_tok.endswith(')')) else b_tok
            idx += 2
        elif tok == 'CBARRIER' and idx + 1 < len(tokens):
            cb_tok = tokens[idx + 1]
            cbarrier = cb_tok[1:-1].strip() if (cb_tok.startswith('(') and cb_tok.endswith(')')) else cb_tok
            idx += 2
        elif tok == 'LINK':
            rest = ' '.join(tokens[idx + 1:])
            linked_test = parse_contextual_test(rest, grammar)
            break
        else:
            idx += 1

    ctest = ContextualTest(
        target=target,
        offset=offset,
        is_scan=is_scan,
        is_careful=is_careful,
        is_not=is_not,
        is_negate=is_negate,
        is_absolute=is_absolute,
        barrier=barrier,
        cbarrier=cbarrier,
        linked_test=linked_test,
        raw_pos=pos_token
    )
    ctest.is_self_barrier = is_self_barrier
    ctest.is_self_no_barrier = is_self_no_barrier
    ctest.dep_dir = dep_dir
    return ctest


class Grammar:
    """Represents a compiled VISL CG-3 grammar."""

    def __init__(self):
        self.delimiters: Optional[SetDefinition] = None
        self.soft_delimiters: Optional[SetDefinition] = None
        self.mapping_prefix: str = '@'
        self.options: Set[str] = set()
        self.sets: Dict[str, SetDefinition] = {}
        self.before_sections: List[Rule] = []
        self.sections: List[List[Rule]] = []
        self.after_sections: List[Rule] = []
        self.null_section: List[Rule] = []

    def get_set(self, name: str) -> Optional[SetDefinition]:
        return self.sets.get(name)


class GrammarParser:
    """Parses .cg3 grammar file contents into a Grammar object."""

    RULE_KEYWORDS = {
        'SELECT', 'REMOVE', 'IFF', 'ADD', 'MAP', 'UNMAP',
        'REPLACE', 'SUBSTITUTE', 'APPEND', 'COPY',
        'ADDCOHORT', 'REMCOHORT', 'MOVE', 'SWITCH',
        'SETVARIABLE', 'REMVARIABLE', 'EXECUTE', 'JUMP'
    }

    def __init__(self):
        self.grammar = Grammar()
        self.current_section = "BEFORE"
        self.active_section_rules: List[Rule] = []

    def parse(self, text: str) -> Grammar:
        clean_text = strip_comments(text)
        statements = split_statements(clean_text)

        for stmt_idx, stmt in enumerate(statements, start=1):
            self._parse_statement(stmt, stmt_idx)

        # Flush any active section
        if self.current_section == "SECTION" and self.active_section_rules:
            self.grammar.sections.append(self.active_section_rules)
            self.active_section_rules = []

        return self.grammar

    def _parse_statement(self, stmt: str, line_num: int):
        first_token = stmt.split()[0].upper() if stmt.split() else ""

        if first_token in ('BEFORE-SECTIONS', 'MAPPINGS', 'CORRECTIONS'):
            if self.current_section == "SECTION" and self.active_section_rules:
                self.grammar.sections.append(self.active_section_rules)
                self.active_section_rules = []
            self.current_section = "BEFORE"
            return

        elif first_token in ('SECTION', 'CONSTRAINTS'):
            if self.current_section == "SECTION" and self.active_section_rules:
                self.grammar.sections.append(self.active_section_rules)
            self.active_section_rules = []
            self.current_section = "SECTION"
            return

        elif first_token == 'AFTER-SECTIONS':
            if self.current_section == "SECTION" and self.active_section_rules:
                self.grammar.sections.append(self.active_section_rules)
                self.active_section_rules = []
            self.current_section = "AFTER"
            return

        elif first_token == 'NULL-SECTION':
            if self.current_section == "SECTION" and self.active_section_rules:
                self.grammar.sections.append(self.active_section_rules)
                self.active_section_rules = []
            self.current_section = "NULL"
            return

        elif first_token == 'DELIMITERS':
            parts = stmt.split('=', 1)
            if len(parts) == 2:
                s = SetDefinition(name="_DELIMITERS_", line_number=line_num)
                for t in split_tags(parts[1]):
                    s.add_item(TagPattern(t))
                self.grammar.delimiters = s
            return

        elif first_token == 'SOFT-DELIMITERS':
            parts = stmt.split('=', 1)
            if len(parts) == 2:
                s = SetDefinition(name="_SOFT_DELIMITERS_", line_number=line_num)
                for t in split_tags(parts[1]):
                    s.add_item(TagPattern(t))
                self.grammar.soft_delimiters = s
            return

        elif first_token == 'MAPPING-PREFIX':
            parts = stmt.split('=', 1)
            if len(parts) == 2:
                val = parts[1].strip()
                if val:
                    self.grammar.mapping_prefix = val[0]
            return

        elif first_token == 'OPTIONS':
            if '+=' in stmt:
                parts = stmt.split('+=', 1)
                for opt in parts[1].split():
                    self.grammar.options.add(opt.lower())
            return

        elif first_token in ('LIST', 'OLIST'):
            self._parse_list_statement(stmt, line_num, ordered=(first_token == 'OLIST'))
            return

        elif first_token == 'SET':
            self._parse_set_statement(stmt, line_num)
            return

        elif first_token == 'SETS':
            return

        # Check if it's a rule
        rule = self._maybe_parse_rule(stmt, line_num)
        if rule:
            if self.current_section == "BEFORE":
                self.grammar.before_sections.append(rule)
            elif self.current_section == "SECTION":
                self.active_section_rules.append(rule)
            elif self.current_section == "AFTER":
                self.grammar.after_sections.append(rule)
            elif self.current_section == "NULL":
                self.grammar.null_section.append(rule)

    def _parse_list_statement(self, stmt: str, line_num: int, ordered: bool = False):
        tokens = split_tags(stmt)
        if len(tokens) >= 4 and tokens[2] == '=':
            name = tokens[1]
            items = tokens[3:]
            s = SetDefinition(name=name, line_number=line_num, is_ordered=ordered)
            for it in items:
                if it.startswith('(') and it.endswith(')'):
                    inner = split_tags(it[1:-1])
                    s.add_item(CompositeTag([TagPattern(x) for x in inner]))
                else:
                    s.add_item(TagPattern(it))
            self.grammar.sets[name] = s

    def _parse_set_statement(self, stmt: str, line_num: int):
        tokens = split_tags(stmt)
        if len(tokens) >= 4 and tokens[2] == '=':
            name = tokens[1]
            expr_tokens = tokens[3:]
            s = SetDefinition(name=name, line_number=line_num)

            curr_op = '+'
            i = 0
            while i < len(expr_tokens):
                tok = expr_tokens[i]
                if tok in ('+', '-', '_', '^', 'OR', '|', '\\', '∩', '∆'):
                    if tok in ('OR', '|'):
                        curr_op = '+'
                    elif tok == '\\':
                        curr_op = '-'
                    elif tok == '∩':
                        curr_op = '_'
                    elif tok == '∆':
                        curr_op = '^'
                    else:
                        curr_op = tok
                    i += 1
                else:
                    item: Any = None
                    if tok.startswith('(') and tok.endswith(')'):
                        inner = split_tags(tok[1:-1])
                        if len(inner) > 1:
                            item = CompositeTag([TagPattern(x) for x in inner])
                        elif len(inner) == 1:
                            item = TagPattern(inner[0])
                        else:
                            item = TagPattern('*')
                    elif tok in self.grammar.sets:
                        item = self.grammar.sets[tok]
                    else:
                        item = TagPattern(tok)

                    if not s.items:
                        s.add_item(item)
                    else:
                        s.operations.append((curr_op, item))
                    i += 1

            self.grammar.sets[name] = s

    def _maybe_parse_rule(self, stmt: str, line_num: int) -> Optional[Rule]:
        tokens = split_tags(stmt)
        if not tokens:
            return None

        wordform_filter = None
        idx = 0

        if tokens[0].startswith('"<') and tokens[0].endswith('>"'):
            wordform_filter = tokens[0]
            idx += 1

        if idx >= len(tokens):
            return None

        name = ""
        rule_type = ""
        tok = tokens[idx]

        if ':' in tok:
            parts = tok.split(':', 1)
            if parts[0].upper() in self.RULE_KEYWORDS:
                rule_type = parts[0].upper()
                name = parts[1]
            elif parts[1].upper() in self.RULE_KEYWORDS:
                name = parts[0]
                rule_type = parts[1].upper()
        elif tok.upper() in self.RULE_KEYWORDS:
            rule_type = tok.upper()
        else:
            if idx + 1 < len(tokens) and tokens[idx+1].upper() in self.RULE_KEYWORDS:
                name = tok.rstrip(':')
                rule_type = tokens[idx+1].upper()
                idx += 1

        if not rule_type:
            return None

        idx += 1

        target_modifiers = ""
        if idx < len(tokens) and tokens[idx] in ('!', 'c', 'c!', '!c', '*', '*!'):
            target_modifiers = tokens[idx]
            idx += 1

        action_tags = []
        subst_old_tag = None

        if rule_type in ('ADD', 'MAP', 'REPLACE', 'COPY'):
            if idx < len(tokens):
                act_tok = tokens[idx]
                if act_tok.startswith('(') and act_tok.endswith(')'):
                    action_tags = split_tags(act_tok[1:-1])
                else:
                    action_tags = [act_tok]
                idx += 1
        elif rule_type == 'SUBSTITUTE':
            if idx < len(tokens):
                old_tok = tokens[idx]
                subst_old_tag = old_tok[1:-1].strip() if old_tok.startswith('(') and old_tok.endswith(')') else old_tok
                idx += 1
            if idx < len(tokens):
                new_tok = tokens[idx]
                action_tags = split_tags(new_tok[1:-1]) if new_tok.startswith('(') and new_tok.endswith(')') else [new_tok]
                idx += 1
        elif rule_type == 'APPEND':
            if idx < len(tokens):
                act_tok = tokens[idx]
                action_tags = split_tags(act_tok[1:-1]) if act_tok.startswith('(') and act_tok.endswith(')') else [act_tok]
                idx += 1
        elif rule_type == 'ADDCOHORT':
            if idx < len(tokens):
                act_tok = tokens[idx]
                action_tags = split_tags(act_tok[1:-1]) if act_tok.startswith('(') and act_tok.endswith(')') else [act_tok]
                idx += 1

        direction = "AFTER"
        if idx < len(tokens) and tokens[idx].upper() in ('BEFORE', 'AFTER'):
            direction = tokens[idx].upper()
            idx += 1

        target = '*'
        if idx < len(tokens):
            t_tok = tokens[idx]
            if t_tok.startswith('!') and len(t_tok) > 1:
                target_modifiers += '!'
                t_tok = t_tok[1:]

            if t_tok.startswith('(') and t_tok.endswith(')'):
                inner = split_tags(t_tok[1:-1])
                if len(inner) > 1:
                    target = CompositeTag([TagPattern(x) for x in inner])
                elif len(inner) == 1:
                    target = inner[0]
                else:
                    target = '*'
            elif t_tok in self.grammar.sets:
                target = self.grammar.sets[t_tok]
            else:
                target = t_tok
            idx += 1

        context_tests = []
        while idx < len(tokens):
            c_tok = tokens[idx]
            if c_tok.startswith('(') and c_tok.endswith(')'):
                ctest = parse_contextual_test(c_tok, self.grammar)
                context_tests.append(ctest)
            idx += 1

        rule = Rule(
            rule_type=rule_type,
            target=target,
            name=name if name else f"{rule_type}_{line_num}",
            line_number=line_num,
            context_tests=context_tests,
            action_tags=action_tags,
            subst_old_tag=subst_old_tag,
            target_modifiers=target_modifiers,
            wordform_filter=wordform_filter
        )
        rule.direction = direction
        return rule
