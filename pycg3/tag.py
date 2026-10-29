"""Tag representation and matching for VISL CG-3."""

import re
from functools import lru_cache
from typing import Optional, Union, List

@lru_cache(maxsize=4096)
def get_compiled_regex(pattern: str, flags: int = 0) -> re.Pattern:
    return re.compile(pattern, flags)


def is_wordform(tag: str) -> bool:
    """Returns True if the tag is a wordform like \"<word>\"."""
    return tag.startswith('"<') and tag.endswith('>"')


def is_baseform(tag: str) -> bool:
    """Returns True if the tag is a baseform like \"word\" (quoted, not bracketed)."""
    return tag.startswith('"') and tag.endswith('"') and not (tag.startswith('"<') and tag.endswith('>"'))


def extract_form(tag: str) -> str:
    """Extract inner content from quoted wordform \"<word>\" -> word, or baseform \"word\" -> word."""
    if is_wordform(tag):
        return tag[2:-2]
    if tag.startswith('"') and tag.endswith('"') and len(tag) >= 2:
        return tag[1:-1]
    return tag


class TagPattern:
    """Represents a tag pattern (literal, regex, wildcard, or special tag) used in Sets and Rules."""

    __slots__ = (
        'raw',
        'is_regex',
        'is_any',
        'is_failfast',
        'is_case_insensitive',
        'is_wordform',
        'is_baseform',
        'literal',
        '_regex',
        'last_match'
    )

    def __init__(self, raw: str):
        self.raw = raw
        self.is_any = (raw == '*' or raw == '(*)')
        self.is_failfast = raw.startswith('!') and len(raw) > 1

        pattern_str = raw[1:] if self.is_failfast else raw
        self.is_wordform = is_wordform(pattern_str)
        self.is_baseform = is_baseform(pattern_str)
        self.is_regex = False
        self.is_case_insensitive = False
        self.literal = pattern_str
        self._regex: Optional[re.Pattern] = None
        self.last_match: Optional[re.Match] = None

        # Check for quoted string with trailing flags: e.g. "pattern"r, "pattern"ri, "pattern"i
        if pattern_str.startswith('"') and '"' in pattern_str[1:]:
            last_quote = pattern_str.rfind('"')
            flags = pattern_str[last_quote + 1:].lower()
            inner = pattern_str[1:last_quote]
            if 'r' in flags:
                self.is_regex = True
                if 'i' in flags:
                    self.is_case_insensitive = True
                self._init_regex(inner, flags)
            elif 'i' in flags:
                self.is_case_insensitive = True
                self.literal = inner
            else:
                self.literal = pattern_str

        # Check for /pattern/flags or ~/pattern/flags
        elif (pattern_str.startswith('/') or pattern_str.startswith('~/')) and '/' in pattern_str[2:]:
            start = 2 if pattern_str.startswith('~/') else 1
            last_slash = pattern_str.rfind('/')
            flags = pattern_str[last_slash + 1:].lower()
            inner = pattern_str[start:last_slash]
            self.is_regex = True
            if 'i' in flags:
                self.is_case_insensitive = True
            self._init_regex(inner, flags)

        # Check for r"pattern"
        elif (pattern_str.startswith('r"') or pattern_str.startswith("r'")) and (pattern_str.endswith('"') or pattern_str.endswith("'")):
            self.is_regex = True
            inner = pattern_str[2:-1]
            self._init_regex(inner)

    def _init_regex(self, inner: str, flags_str: str = ""):
        flags = 0
        if self.is_case_insensitive or 'i' in flags_str:
            flags |= re.IGNORECASE
        try:
            self._regex = get_compiled_regex(inner, flags)
        except re.error:
            self.is_regex = False
            self._regex = None

    def matches_tag(self, tag: str) -> bool:
        """Check if this pattern matches an individual tag string."""
        if self.is_any:
            return True

        if self.is_regex and self._regex is not None:
            # Match directly or strip quotes if baseform
            m = self._regex.search(tag)
            if not m and (tag.startswith('"') and tag.endswith('"')):
                m = self._regex.search(tag[1:-1])
            if m:
                self.last_match = m
                return True
            return False

        if self.is_case_insensitive:
            # Case-insensitive comparison
            target = tag[1:-1] if (tag.startswith('"') and tag.endswith('"')) else tag
            return target.lower() == self.literal.lower() or tag.lower() == self.raw.lower()

        if self.raw == tag:
            return True

        return False

    def __repr__(self) -> str:
        return f"TagPattern({self.raw})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TagPattern):
            return self.raw == other.raw
        if isinstance(other, str):
            return self.raw == other
        return False

    def __hash__(self) -> int:
        return hash(self.raw)
