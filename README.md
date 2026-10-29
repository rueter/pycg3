# pycg3

A pure Python implementation of **VISL CG-3 (Constraint Grammar 3)**.

`pycg3` implements the Constraint Grammar formalism natively in Python without external C/C++ dependencies. It supports the VISL CG-3 grammar syntax, stream format, disambiguation rules, contextual tests, barriers, and multi-section passes.

---

## Features

- **Pure Python**: Zero native extensions or C/C++ compilation required; runs on standard Python (>= 3.9).
- **Streaming & Memory Efficient**: Uses streaming generators (`SingleWindow` per sentence) and slotted data structures to ensure minimal memory usage and prevent out-of-memory issues on large corpora.
- **CLI & Module Interface**: Can be used both as a CLI tool (`pycg3` / `vislcg3-py`) compatible with `vislcg3` flags, and as a Python library.
- **VISL CG-3 Syntax & Semantics**:
  - Statements: `DELIMITERS`, `SOFT-DELIMITERS`, `MAPPING-PREFIX`, `OPTIONS`, `LIST`, `OLIST`, `SET`.
  - Set operations: union (`+`, `OR`), difference (`-`, `\`), intersection (`_`, `∩`), symmetric difference (`^`, `∆`), composite tags `(tag1 tag2)`.
  - Sections: `BEFORE-SECTIONS`, iterative `SECTION` passes until fixed-point, `AFTER-SECTIONS`, `NULL-SECTION`.
  - Rule types: `SELECT`, `REMOVE`, `IFF`, `ADD`, `MAP`, `UNMAP`, `REPLACE`, `SUBSTITUTE`, `APPEND`, `COPY`, `ADDCOHORT`, `REMCOHORT`, `MOVE`, `SWITCH`, `SETVARIABLE`, `REMVARIABLE`.
  - Contextual tests:
    - Relative positions: `0`, `1`, `-1`, `2`, `-2`
    - Scanning: `*1`, `*-1`, `*0`
    - Absolute positions: `@1`, `@-1`
    - Modifiers: `C` / `c` (careful/all readings), `NOT` (local target inversion), `NEGATE` (chain inversion)
    - Barriers: `BARRIER`, `CBARRIER`, self-barrier options (`self-no-barrier`)
    - Chaining: `LINK`

---

## Installation

```bash
pip install -e .
```

---

## Command-Line Usage

The CLI arguments match the standard `vislcg3` options:

```bash
# Disambiguate input file with grammar
pycg3 -g grammar.cg3 -i input.txt -o output.txt

# Using standard input / output pipes
cat input.txt | pycg3 -g grammar.cg3 > output.txt

# Run a specific number of sections
pycg3 -g grammar.cg3 -i input.txt -s 2

# Trace rule applications
pycg3 -g grammar.cg3 -i input.txt -t

# Show rules mark affected lines (<<<)
pycg3 -g grammar.cg3 -i input.txt -e

# Include deleted readings in output (; prefix)
pycg3 -g grammar.cg3 -i input.txt -p
```

---

## Python API Usage

```python
from pycg3 import GrammarParser, Disambiguator

grammar_code = """
DELIMITERS = "<$.>" ;

LIST Noun = N ;
LIST Verb = V ;

SECTION
SELECT Verb (0 Noun) (-1 ("<to>")) ;
"""

grammar = GrammarParser().parse(grammar_code)
engine = Disambiguator(grammar)

input_text = '''"<to>"
\t"to" PREP
"<run>"
\t"run" N
\t"run" V
"<.>"
\t"." CLB
'''

output = engine.run_text(input_text)
print(output)
```

Output:
```text
"<to>"
	"to" PREP
"<run>"
	"run" V
"<.>"
	"." CLB
```

---

## Memory Efficiency & Testing

In contrast to spawning multiple heavy test processes or loading entire datasets in memory, `pycg3` executes in a single lightweight process using streaming sentence windows.

To run the built-in test suite:
```bash
python3 -m unittest discover tests
```
The entire test suite executes in ~10 milliseconds with negligible RAM usage (< 20 MB).

---

## License

GNU General Public License v3 or later (matching VISL CG-3).
