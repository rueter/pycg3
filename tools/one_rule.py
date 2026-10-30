#!/usr/bin/env python3
"""one_rule.py GRAMMAR LINE INPUT WORD - run only the rule that starts on LINE of GRAMMAR (plus all the sets) with both
vislcg3 and pycg3 on the window of INPUT that contains the cohort "<WORD>", and show what each did to that window."""
import io
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pycg3.grammar import GrammarParser
from pycg3.engine import Disambiguator

g_path, line_no, in_path, word = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
lines = open(g_path, encoding="utf-8").read().split("\n")
sec = next(i for i, l in enumerate(lines) if l.strip() == "SECTION")
# the statement starting on line_no, up to its ';'
stmt, i = [], line_no - 1
while True:
    stmt.append(lines[i])
    if ";" in lines[i].split("#")[0]:
        break
    i += 1
if os.environ.get("RULE_TEXT"):          # try a variant of the rule instead
    stmt = [os.environ["RULE_TEXT"]]
grammar = "\n".join(lines[:sec]) + "\nSECTION\n" + "\n".join(stmt) + "\n"
# the window with the word
wins, cur = [], []
for l in open(in_path, encoding="utf-8"):
    if l.startswith(":") and cur and cur[-1].startswith('"<'):
        pass
    cur.append(l)
    if l.startswith('"<.>"') or l.startswith('"<!>"') or l.startswith('"<?>"'):
        wins.append(cur)
        cur = []
if cur:
    wins.append(cur)
win = next(w for w in wins if any(l.strip() == '"<%s>"' % word for l in w))
text = "".join(win)
d = tempfile.mkdtemp()
open(d + "/g.cg3", "w", encoding="utf-8").write(grammar)
open(d + "/i.txt", "w", encoding="utf-8").write(text)
real = subprocess.run(["vislcg3", "-g", d + "/g.cg3", "-I", d + "/i.txt", "-t"], capture_output=True, text=True)
e = Disambiguator(GrammarParser().parse(grammar), trace=True)
py = "".join(w.to_text(trace=True, pipe_deleted=True) + "\n" for w in e.run_stream(io.StringIO(text)))
print("rule:", " ".join(stmt).strip()[:300])
def show(t):
    out, on = [], False
    for l in t.split("\n"):
        if l.startswith('"<'):
            on = l.strip() == '"<%s>"' % word
        if on and not l.startswith(":"):
            out.append(l[:150])
    return out
print("--- vislcg3 (%s)" % real.stderr.strip()[:100]); print("\n".join(show(real.stdout)))
print("--- pycg3");  print("\n".join(show(py)))
