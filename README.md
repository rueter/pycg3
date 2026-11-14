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
    - Neighbouring windows: `W` (either side), `<` (previous), `>` (next), as in `(*1W (X))`, `(@-1< (*))`
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

# Windows kept behind and read ahead for tests with W < > (default 2); make every scan cross window edges
pycg3 -g grammar.cg3 -i input.txt --num-windows 3 --always-span
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

## Using it as a library (and from UralicNLP)

pycg3 knows no language. It runs the Constraint Grammar files **you** provide on analyses **you** provide.

```python
from pycg3 import Cg

cg = Cg.from_files("disambiguator.cg3", "functions.cg3")     # grammars, run in the order given

# analyses in the shape pyhfst's lookup gives: one list of [analysis, weight] pairs per word
morphologies = [[["time+N+Sg", 0.0], ["time+V+Inf", 0.0]],
                [["fly+V+Prs+Sg3", 0.0], ["fly+N+Pl", 0.0]]]
result = cg.disambiguate(["Time", "flies"], morphologies)
# [("Time", [CgWord, ...]), ("flies", [CgWord, ...])]
word = result[0][1][0]
word.lemma, word.tags, word.weight, word.morphology, word.sub_readings   # morphology = tags + <W:..>, like UralicNLP's Cg3Word
cg.to_morphologies(result)             # back to pyhfst's shape: the input of whatever comes next
```

- Several grammars run one after the other, each taking the previous one's output (`vislcg3 -g a | vislcg3 -g b`).
  `Cg([text_or_Grammar, ...], names=[...])` takes grammar texts or parsed grammars instead of files.
- `Cg(..., trace=True)` puts the rule labels in `CgWord.trace`. `cg.run_text(cg_stream)` is the plain CG stream in, stream out.
- Compounds (`part#part`) become a reading for the last part with the earlier parts as `sub_readings`. A `+vN` variant
  tag is dropped from the analyses unless you pass `drop_variants=False`.
- An empty word in the list (UralicNLP ends a sentence with one) is skipped together with its analyses.
- Thread-safe: grammars are not changed by running them.
- Getting the analyses (an analyser, a tokeniser) and shipping grammars and FSTs for a language is up to the caller.
  Nothing here depends on `pyhfst`.

```bash
pip install build
python -m build            # pycg3-X.Y.Z-py3-none-any.whl and the sdist, in dist/
```

The wheel is `py3-none-any`: pure Python, so one wheel serves every platform and Python >= 3.9.

---

## Fidelity to vislcg3

pycg3 is checked against the real `vislcg3` (the CG-3 project's source, 1.5-series), not against its manual.
On the Erzya and Moksha `disambiguator.cg3` grammars of GiellaLT (lang-myv: 8 734 + 3 576 cohorts; lang-mdf:
2 725 cohorts, held-out sentences of the UD treebanks), and likewise for `functions.cg3` run after it, the surviving readings, the deleted readings and the
`-t` rule traces come out **identical** to `vislcg3 -t`. What that rests on:

- `runContextualTest` / `runSingleTest` / `doesSetMatchCohort*` are ported with their quirks: a begin cohort
  (`>>>`) before every window and `<<<` on the last cohort; `0*` (also written `*` and `-*`) scans both ways,
  alternating; `NOT` is applied to the set match of every cohort tested, and, in a `NOT` test, to the `BARRIER` match
  too; `*` stops at the first cohort that matches the target; `NEGATE`, `LINK`, `(test) OR (test)`, `C`, `S`, `N`,
  `ALL`, `NONE`, `@n`.
- Running section *k* means running the rules of sections 1..k until nothing changes; only SELECT, REMOVE, IFF
  (and REMCOHORT, MOVE, SWITCH) send a section round again, `ITERATE` / `NOITERATE` override that.
- Readings with the same base form and tag set are merged on input and after a rule changes one (with `-t`
  readings with different traces stay apart); the last reading of a cohort is never removed.
- Sets: `LIST`, `SET` with `OR`, `+`, `-` (on readings) and `^` (the same as `-`), `\`, `∆`, `∩` (on the tags of lists), `$$Set` / `&&Set`
  unification, static tags after the word form, `SETS` headings, CG-2 style rules with the contexts straight
  after the target.

`tools/` holds what was used to get there and to keep it so:

```bash
# any grammar, any input: pycg3 against vislcg3, cohort by cohort (add --trace to compare the traces too)
python3 tools/diff_vislcg3.py --grammar G.cg3 --text-file sentences.txt --tokeniser T.pmhfst --trace
python3 tools/rule_gap.py WORK/real.out WORK/pycg3.out     # which rules fired in one engine and not in the other
RULE_TEXT='REMOVE ... ;' python3 tools/one_rule.py G.cg3 LINE input.cg WORD   # one rule on one window, both engines
python3 tools/run_upstream.py /path/to/cg3/test [T_Name]   # CG-3's own regression tests (see below)
python3 tools/make_fidelity_cases.py                        # rebuild tests/fidelity_cases.json from vislcg3
```

`tests/test_fidelity.py` replays 147 small cases that were run through the real `vislcg3`.

**Dependencies.** `SETPARENT` and `SETCHILD` work: `SETPARENT:name TARGET [IF ...] TO (tests)`, with the `A` flag
(`(**1A X LINK p (>>>))`) for the cohort to attach to, `@0` for the root, the positions `p` `c` `s` `pp` `cc`
with `NONE`/`ALL`, `ALLOWLOOP`, and `$$Sets` shared between the target and the `TO` tests. The output carries `#self->parent`
on every reading once a rule has attached anything. As in vislcg3 a later rule replaces an earlier attachment, a cohort
is never its own parent and never a descendant's child. If the cohort the `TO` test leads to would make a loop, the test is run again
from that cohort and a cohort seen before ends the search, exactly as vislcg3 does; `SETPARENT SAFE` leaves a cohort that already
has a parent alone. On the GiellaLT Southern Sámi grammar, `dependency.cg3` agrees with vislcg3 on all 27,252 cohorts, on North Sámi on all 2,797.

**Looking into the neighbouring windows.** A position with `W`, `<` or `>` (`*1W`, `-1<`, `0*W`, `@1>`, `C*1W` ...) may go on
past the edge of the window into the one before or after it, as in vislcg3: the begin cohort (`>>>`) of the next window is the
cohort after the last one, the last cohort of the previous window the one before the begin cohort. To make that work the engine
runs windows the way vislcg3 does: a window is run when two more have been read (and the begin cohort of a fourth is there),
and two windows already run stay behind it (`Disambiguator(num_windows=2)`, `--num-windows`); a window is handed on once it
falls out of those. A test only sees what is there: windows ahead are as they were read, windows behind as the rules left them.
`always_span=True` (`--always-span`) lets every scan cross window edges. A dependency may attach across windows; from then on
vislcg3 numbers the output globally (`#1001->2003`: window, then place in the window) and a parent in a window that has
already been written is printed as no parent, as vislcg3 does. Relations (`ID:` / `R:`) reach across windows by cohort id.

**Relations and dependencies in the input.** `ADDRELATION`, `SETRELATION`, `REMRELATION` and the plural `*RELATIONS`
rules work, with `TO` and `FROM`, the `r:name` context position (with `ALL` / `NONE`) and `ID:n R:name:m` in the output, in vislcg3's order
(by the hash of the relation name, `cg3_hash`). `#n->m` already present in the input is read when the grammar uses dependencies (it is
renumbered per window, a parent that does not exist leaves the cohort without one, 0 is the root); `REMPARENT` and `SWITCHPARENT WITHCHILD`
work, and `--dep-no-crossing` / `--dep-allow-loops` are the `Disambiguator` options `dep_no_crossing` / `dep_allow_loops`.
Readings that differ only in their mapping tag are printed as one reading, as vislcg3 does.

On the CG-3 project's own tests (`tools/run_upstream.py`) 20 of the 69 pass, among them `T_Dependency_Loops`, `T_SetParentChild`,
`T_SwitchParent`, `T_Dependency_OutOfRange` and `T_Omniscan` (the window-spanning positions).

**Not implemented** (they fail on the CG-3 project's own tests): templates, `WITH`, `MOVE`/`SWITCH`/`SPLITCOHORT`/`MERGECOHORTS`/`COPYCOHORT`,
enclosures/parentheses, `MARK`/`ATTACH`/jumps, regex captures (`$1`) and varstrings, bag of tags, the leftmost/rightmost dependency positions (`llc`, `rrp`, ...), `--unique-tags`, `-e`, `--sections` ranges,
`--split-mappings`, JSON/binary I/O. `disambiguator.bin` (a compiled `CG3B` grammar) cannot be read; use the `.cg3` source.

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

MIT License (see `LICENSE`).


## CITE

Jack Rueter & Olga Erina, pycg3
