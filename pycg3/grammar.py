"""Grammar parser for VISL CG-3 (the subset of the syntax that real Giella grammars use)."""

import re
from typing import Dict, List, Optional, Set, Tuple, Any
from pycg3.tag import TagPattern
from pycg3.set_def import SetDefinition, CompositeTag, UnifySet
from pycg3.context import ContextualTest
from pycg3.rule import Rule

BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
SECTION_KEYWORDS = {
    'BEFORE-SECTIONS', 'AFTER-SECTIONS', 'NULL-SECTION',
    'SECTION', 'CONSTRAINTS', 'MAPPINGS', 'CORRECTIONS'
}
RULE_KEYWORDS = {
    'SELECT', 'REMOVE', 'IFF', 'ADD', 'MAP', 'UNMAP', 'REPLACE', 'SUBSTITUTE', 'APPEND', 'COPY',
    'ADDCOHORT', 'REMCOHORT', 'MOVE', 'SWITCH', 'SETVARIABLE', 'REMVARIABLE', 'EXECUTE', 'JUMP',
}
# rule types that take their tags before the target set
ONE_ACTION = {'ADD', 'MAP', 'REPLACE', 'APPEND', 'COPY', 'ADDCOHORT', 'SETVARIABLE', 'REMVARIABLE'}
RULE_FLAGS = {
    'WITHCHILD', 'NOCHILD', 'ITERATE', 'NOITERATE', 'UNSAFE', 'SAFE', 'REVERSE', 'KEEPORDER', 'VARYORDER',
    'ENCL_INNER', 'ENCL_OUTER', 'ENCL_FINAL', 'ENCL_ANY', 'LOOKDELETED', 'LOOKDELAYED', 'LOOKIGNORED',
    'NEAREST', 'ALLOWLOOP', 'DELAYED', 'IMMEDIATE', 'IGNORED', 'RESETX', 'REMEMBERX', 'ALLOWCROSS',
    'ORDERED', 'BEFORE', 'AFTER',
}
# + and - work on readings (a reading in both / in the first and not the second); \ ∆ ^ ∩ work on the tags of the lists
SET_OPS = {'+': 'and', '-': 'minus', '\\': 'tdiff', '^': 'tsym', '∆': 'tsym', '∩': 'tand'}
# digits are optional: (* X) and (-* X) are both 0*, the scan in both directions
POSITION_RE = re.compile(r'^(@?)(\**)(-?)(\d*)(\**)([A-Za-z]*)$')


class GrammarError(ValueError):
    pass


def tokenize(text: str) -> List[Tuple[str, int]]:
    """Split grammar text into (token, line) pairs. Parentheses and ';' are tokens of their own; a token
    that starts with " or / runs to its closing mark (plus any flags such as r or i); '#' at the start of
    a token begins a comment, and /* ... */ is a block comment."""
    tokens: List[Tuple[str, int]] = []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == '\n':
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == '#':
            while i < n and text[i] != '\n':
                i += 1
        elif c == '/' and text.startswith('/*', i):
            j = text.find('*/', i + 2)
            j = n if j < 0 else j + 2
            line += text.count('\n', i, j)
            i = j
        elif c in '();':
            tokens.append((c, line))
            i += 1
        else:
            j = i
            if c == '"':
                j += 1
                while j < n and text[j] != '"':
                    j += 2 if text[j] == '\\' else 1
                j += 1
            elif c == '/' and '/' in text[i + 1:text.find('\n', i) if text.find('\n', i) >= 0 else n]:
                j = text.find('/', i + 1)
                while j > 0 and text[j - 1] == '\\':
                    j = text.find('/', j + 1)
                j += 1
            while j < n and not text[j].isspace() and text[j] not in '();':
                j += 1
            tokens.append((text[i:j], line))
            i = j
    return tokens


class Grammar:
    """A parsed CG-3 grammar."""

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
    """Parses the text of a .cg3 grammar into a Grammar."""

    RULE_KEYWORDS = RULE_KEYWORDS

    def __init__(self):
        self.grammar = Grammar()
        self.current_section = "BEFORE"
        self.active_section_rules: List[Rule] = []
        self._anon = 0
        self._unify_seen = False

    # -- driver -----------------------------------------------------------------------------
    def parse(self, text: str) -> Grammar:
        toks = tokenize(text)
        stmt: List[Tuple[str, int]] = []
        for tok in toks:
            if tok[0] == ';':
                self._statement(stmt)
                stmt = []
                continue
            if not stmt and tok[0].upper() == 'SETS':      # a heading with no ';' of its own
                continue
            if not stmt and tok[0].upper() in SECTION_KEYWORDS:
                self._section(tok[0].upper())
                continue
            stmt.append(tok)
        self._statement(stmt)
        return self.grammar

    def _section(self, kw: str):
        self.current_section = {'BEFORE-SECTIONS': 'BEFORE', 'MAPPINGS': 'BEFORE', 'CORRECTIONS': 'BEFORE',
                                'SECTION': 'SECTION', 'CONSTRAINTS': 'SECTION', 'AFTER-SECTIONS': 'AFTER',
                                'NULL-SECTION': 'NULL'}[kw]
        if self.current_section == 'SECTION':
            self.active_section_rules = []
            self.grammar.sections.append(self.active_section_rules)

    def _statement(self, stmt: List[Tuple[str, int]]):
        if not stmt:
            return
        words = [t for t, _ in stmt]
        kw = words[0].upper()
        line = stmt[0][1]
        g = self.grammar
        if kw == 'DELIMITERS' and '=' in words:
            g.delimiters = self._tag_list_set("_DELIMITERS_", stmt[words.index('=') + 1:], line)
        elif kw == 'SOFT-DELIMITERS' and '=' in words:
            g.soft_delimiters = self._tag_list_set("_SOFT_DELIMITERS_", stmt[words.index('=') + 1:], line)
        elif kw == 'MAPPING-PREFIX' and '=' in words:
            val = words[words.index('=') + 1] if words.index('=') + 1 < len(words) else ''
            if val:
                g.mapping_prefix = val[0]
        elif kw == 'OPTIONS':
            for w in words[1:]:
                if w not in ('+=', '-=', '='):
                    g.options.add(w.lower())
        elif kw in ('LIST', 'OLIST') and len(words) >= 3 and words[2] == '=':
            s = self._tag_list_set(words[1], stmt[3:], line, ordered=(kw == 'OLIST'))
            g.sets[words[1]] = s
        elif kw == 'SET' and len(words) >= 3 and words[2] == '=':
            g.sets[words[1]] = self._set_expression(words[1], stmt[3:], line)
        elif kw in ('SETS', 'STATIC-SETS', 'SUBREADINGS', 'PARENTHESES', 'INCLUDE', 'TEMPLATE', 'ANCHOR',
                    'CMDLINE', 'DELIMITERS', 'SOFT-DELIMITERS', 'MAPPING-PREFIX'):
            return
        else:
            rule = self._rule(stmt)
            if rule is None:
                return
            if self.current_section == "BEFORE":
                g.before_sections.append(rule)
            elif self.current_section == "SECTION":
                self.active_section_rules.append(rule)
            elif self.current_section == "AFTER":
                g.after_sections.append(rule)
            else:
                g.null_section.append(rule)

    # -- sets ---------------------------------------------------------------------------------
    def _new_set(self, name: str, line: int, ordered: bool = False) -> SetDefinition:
        return SetDefinition(name=name, line_number=line, is_ordered=ordered, registry=self.grammar.sets)

    def _tag_list_set(self, name, toks, line, ordered=False) -> SetDefinition:
        """LIST / DELIMITERS body: tags and (composite tags), all alternatives of one set."""
        s = self._new_set(name, line, ordered)
        i = 0
        while i < len(toks):
            t = toks[i][0]
            if t == '(':
                j, depth = i + 1, 1
                inner = []
                while j < len(toks) and depth:
                    if toks[j][0] == '(':
                        depth += 1
                    elif toks[j][0] == ')':
                        depth -= 1
                        if not depth:
                            break
                    inner.append(toks[j][0])
                    j += 1
                if len(inner) == 1:
                    s.add_item(TagPattern(inner[0]))
                elif inner:
                    s.add_item(CompositeTag([TagPattern(x) for x in inner]))
                i = j + 1
            elif t == ')':
                i += 1
            else:
                s.add_item(TagPattern(t))
                i += 1
        return s

    def _group_to_set(self, inner: List[str], line: int) -> SetDefinition:
        s = self._new_set("", line)
        if len(inner) == 1:
            s.add_item(TagPattern(inner[0]))
        elif inner:
            s.add_item(CompositeTag([TagPattern(x) for x in inner]))
        return s

    def _set_expression(self, name: str, toks, line: int) -> SetDefinition:
        """A set expression: operands joined by OR / + / - / \\ / ^ ; '+' and the like bind tighter than OR."""
        words = [t for t, _ in toks]
        s = self._new_set(name, line)
        group: list = []
        op = None
        i = 0
        while i < len(words):
            w = words[i]
            if w == '(':
                depth, j, inner = 1, i + 1, []
                while j < len(words) and depth:
                    if words[j] == '(':
                        depth += 1
                    elif words[j] == ')':
                        depth -= 1
                        if not depth:
                            break
                    inner.append(words[j])
                    j += 1
                operand: Any = self._group_to_set(inner, line)
                i = j + 1
            elif w.upper() == 'OR' or w == '|':
                if group:
                    s.groups.append(group)
                group, op = [], None
                i += 1
                continue
            elif w in SET_OPS:
                op = SET_OPS[w]
                i += 1
                continue
            else:
                if w[:2] in ('$$', '&&') and w[2:] in self.grammar.sets:
                    operand = UnifySet(w[2:], w[:2], self.grammar.sets)
                    self._unify_seen = True
                else:
                    # a set name, else a bare tag used as a one-tag set
                    operand = w if w in self.grammar.sets else self._group_to_set([w], line)
                i += 1
            group.append((op if group else None, operand))
            op = None
        if group:
            s.groups.append(group)
        s.groups = [self._fold_tag_ops(g, line) for g in s.groups]
        if len(s.groups) == 1 and len(s.groups[0]) == 1 and isinstance(s.groups[0][0][1], SetDefinition):
            only = s.groups[0][0][1]
            only.name = only.name or name
            return only
        return s

    def _fold_tag_ops(self, group: list, line: int) -> list:
        """Carry out \\ ∆ ^ ∩ on the tags of the lists they join, leaving a chain of + and - for the rest."""
        def listed(o):
            o = self.grammar.sets.get(o) if isinstance(o, str) else o
            return o if isinstance(o, SetDefinition) and not o.groups else None

        def key(item):
            return item.raw if isinstance(item, TagPattern) else tuple(e.raw for e in item.elements)

        out: list = []
        for op, operand in group:
            if op in ('tdiff', 'tsym', 'tand') and out:
                a, b = listed(out[-1][1]), listed(operand)
                if a is None or b is None:
                    raise GrammarError("\\, ∆, ^ and ∩ need plain lists on both sides (line %d)" % line)
                ka, kb = {key(i) for i in a.items}, {key(i) for i in b.items}
                if op == 'tdiff':
                    items = [i for i in a.items if key(i) not in kb]
                elif op == 'tand':
                    items = [i for i in a.items if key(i) in kb]
                else:
                    items = [i for i in a.items if key(i) not in kb] + [i for i in b.items if key(i) not in ka]
                combined = self._new_set("", line)
                combined.items = items
                out[-1] = (out[-1][0], combined)
            else:
                out.append((op, operand))
        return out

    # -- rules ------------------------------------------------------------------------------------
    def _rule(self, stmt: List[Tuple[str, int]]) -> Optional[Rule]:
        words = [t for t, _ in stmt]
        i = 0
        head = words[0]
        self._unify_seen = False
        rtype, name = None, ""
        if ':' in head and head.split(':', 1)[0].upper() in RULE_KEYWORDS:
            rtype, name = head.split(':', 1)[0].upper(), head.split(':', 1)[1]
        elif head.upper() in RULE_KEYWORDS:
            rtype = head.upper()
        else:
            return None
        line = stmt[0][1]
        i = 1
        flags = set()
        while i < len(words) and words[i].upper() in RULE_FLAGS:
            flags.add(words[i].upper())
            i += 1

        def group_at(i):
            """The tags of the parenthesised group starting at words[i] and the index after it."""
            depth, j, inner = 1, i + 1, []
            while j < len(words) and depth:
                if words[j] == '(':
                    depth += 1
                elif words[j] == ')':
                    depth -= 1
                    if not depth:
                        break
                inner.append(words[j])
                j += 1
            return inner, j + 1

        action_tags: List[str] = []
        subst_old = None
        if rtype == 'SUBSTITUTE':
            if i < len(words) and words[i] == '(':
                inner, i = group_at(i)
                subst_old = self._tag_list_set("", [(w, line) for w in inner], line)
            elif i < len(words):
                subst_old = self._set_expression("", [(words[i], line)], line)
                i += 1
            if i < len(words) and words[i] == '(':
                action_tags, i = group_at(i)
        elif rtype in ONE_ACTION:
            if i < len(words) and words[i] == '(':
                action_tags, i = group_at(i)
            elif i < len(words):
                action_tags = [words[i]]
                i += 1
        direction = "AFTER"
        if rtype in ('ADDCOHORT', 'MOVE') and i < len(words) and words[i].upper() in ('BEFORE', 'AFTER'):
            direction = words[i].upper()
            i += 1

        if i < len(words) and words[i].upper() == 'TARGET':
            i += 1
        # the target is one set expression: operands joined by OR / + / - ...; what follows is IF and the
        # contexts, or (CG-2 style) the contexts straight away
        j = i
        while True:
            if j < len(words) and words[j] == '(':
                j = group_at(j)[1]
            elif j < len(words) and words[j].upper() not in ('IF', 'EXCEPT'):
                j += 1
            else:
                break
            if j < len(words) and (words[j].upper() == 'OR' or words[j] == '|' or words[j] in SET_OPS):
                j += 1
                continue
            break
        target = self._set_expression("", stmt[i:j], line) if j > i else self._group_to_set(['*'], line)
        tests: List[ContextualTest] = []
        k = j + 1 if j < len(words) and words[j].upper() == 'IF' else j
        while k < len(words):
            if words[k] == '(':
                inner, k = group_at(k)
                tests.append(self._context_test(inner, line))
            else:
                k += 1
        rule = Rule(rule_type=rtype, target=target, name=name, line_number=line, context_tests=tests,
                    action_tags=action_tags, subst_old=subst_old)
        rule.direction = direction
        rule.flags = flags
        rule.uses_unify = self._unify_seen
        self._unify_seen = False
        return rule

    # -- contextual tests -----------------------------------------------------------------------------
    def _context_list(self, words: List[str], line: int) -> ContextualTest:
        """(test) OR (test) ..., or one bare test that takes all the words (with its own LINKs)."""
        alts: List[ContextualTest] = []
        i = 0
        while True:
            if i < len(words) and words[i] == '(':
                depth, j, inner = 1, i + 1, []
                while j < len(words) and depth:
                    if words[j] == '(':
                        depth += 1
                    elif words[j] == ')':
                        depth -= 1
                        if not depth:
                            break
                    inner.append(words[j])
                    j += 1
                alts.append(self._context_test(inner, line))
                i = j + 1
                if i < len(words) and words[i].upper() == 'LINK':      # (test) LINK test: carry on from where it matched
                    tail = alts[-1]
                    while tail.linked_test is not None and not tail.ors:
                        tail = tail.linked_test
                    nxt = self._context_list(words[i + 1:], line)
                    if tail.ors:
                        for alt in tail.ors:
                            end = alt
                            while end.linked_test is not None:
                                end = end.linked_test
                            end.linked_test = nxt
                    else:
                        tail.linked_test = nxt
                    i = len(words)
            else:
                alts.append(self._context_test(words[i:], line))
                i = len(words)
            if i < len(words) and words[i].upper() == 'OR':
                i += 1
                continue
            break
        if len(alts) == 1:
            return alts[0]
        test = ContextualTest(target=self._group_to_set(['*'], line))
        test.ors = alts
        return test

    def _context_test(self, words: List[str], line: int) -> ContextualTest:
        """words are the tokens inside one ( ... ): [NOT|NEGATE] position set [BARRIER set] [CBARRIER set] [LINK test].
        A group that begins with ( holds alternatives: (test) OR (test)."""
        if words and words[0] == '(':
            return self._context_list(words, line)
        i = 0
        is_not = is_negate = all_ = none_ = False
        while i < len(words) and words[i].upper() in ('NOT', 'NEGATE', 'ALL', 'NONE'):
            kw = words[i].upper()
            is_not = is_not or kw == 'NOT'
            is_negate = is_negate or kw == 'NEGATE'
            all_ = all_ or kw == 'ALL'
            none_ = none_ or kw == 'NONE'
            i += 1
        pos = words[i] if i < len(words) else '0'
        i += 1
        offset, scan_first, scan_all, careful, absolute, self_, no_barrier = 0, False, False, False, False, False, False
        m = POSITION_RE.match(pos)
        if m:
            absolute = bool(m.group(1))
            offset = (-1 if m.group(3) else 1) * int(m.group(4) or 0)
            before, after = m.group(2), m.group(5)
            stars = len(before) + len(after)
            scan_all, scan_first = stars >= 2, stars == 1
            flags = m.group(6)
            careful, self_, no_barrier = 'C' in flags, 'S' in flags, 'N' in flags
            if 'self-no-barrier' in self.grammar.options and self_:
                no_barrier = not no_barrier

        def collect(i, stop):
            """Tokens (with parentheses kept whole) up to a stop keyword at depth 0."""
            depth, out = 0, []
            while i < len(words):
                w = words[i]
                if depth == 0 and w.upper() in stop:
                    break
                if w == '(':
                    depth += 1
                elif w == ')':
                    depth -= 1
                out.append((w, line))
                i += 1
            return out, i

        stop = {'BARRIER', 'CBARRIER', 'LINK'}
        target_toks, i = collect(i, stop)
        target = self._set_expression("", target_toks, line) if target_toks else self._group_to_set(['*'], line)
        barrier = cbarrier = linked = None
        while i < len(words):
            kw = words[i].upper()
            if kw == 'BARRIER':
                toks, i = collect(i + 1, stop)
                barrier = self._set_expression("", toks, line)
            elif kw == 'CBARRIER':
                toks, i = collect(i + 1, stop)
                cbarrier = self._set_expression("", toks, line)
            elif kw == 'LINK':
                linked = self._context_list(words[i + 1:], line)
                break
            else:
                i += 1
        return ContextualTest(target=target, offset=offset, scan_first=scan_first, scan_all=scan_all, careful=careful,
                              not_=is_not, negate=is_negate, absolute=absolute, self_=self_, no_barrier=no_barrier,
                              all_=all_, none_=none_, barrier=barrier, cbarrier=cbarrier, linked_test=linked,
                              raw_pos=pos)
