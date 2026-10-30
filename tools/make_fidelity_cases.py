#!/usr/bin/env python3
# encoding: UTF-8
"""
make_fidelity_cases.py - (re)build tests/fidelity_cases.json: small grammar+input pairs together with what the real
vislcg3 makes of them. tests/test_fidelity.py then checks that pycg3 gives the same. Needs vislcg3 on the PATH;
the tests themselves do not.

    python3 tools/make_fidelity_cases.py
"""
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "tests", "fidelity_cases.json")
D = 'DELIMITERS = "<.>" ;\nLIST BOS = (>>>) ;\nLIST EOS = (<<<) ;\n'


def cohorts(names, tags=None):
    return "".join('"<%s>"\n\t"%s" T%s\n' % (c, c, c.upper()) for c in names)


FIRE = D + "SECTION\nADD (@fire) (*) IF (%s) ;\n"      # which cohorts does this context hold for?
ABCDE, ABCDEFG = cohorts("abcde"), cohorts("abcdefg")
cases = []


def add(name, grammar, text):
    cases.append({"name": name, "grammar": grammar, "input": text})


# the window edges: a begin cohort in front, <<< on the last cohort
for ctx in ["0 BOS", "-1 BOS", "-2 BOS", "0 EOS", "1 EOS", "2 EOS", "NOT 1 EOS", "NOT -1 BOS", "1* EOS", "-1* BOS", "0* BOS"]:
    add("edge: " + ctx, FIRE % ctx, ABCDE + '"<.>"\n\t"." TS\n')
    add("edge (no delimiter): " + ctx, FIRE % ctx, ABCDE)
# scans, NOT, 0* (both ways, alternating) and the quirks of NOT with scanning and barriers
for pos in ["0*", "1*", "-1*", "*0", "2*", "1**", "(*", "-*"]:
    for neg in ["", "NOT ", "NEGATE "]:
        for k in "ace":
            ctx = "%s%s (T%s)" % (neg, pos if not pos.startswith("(") else pos[1:], k.upper())
            add("scan: " + ctx, FIRE % ctx, ABCDE)
for ctx in ["0* (TB) BARRIER (TD)", "NOT 0* (TB) BARRIER (TD)", "0* (TF) BARRIER (TD)", "NOT 0* (TF) BARRIER (TD)",
            "NOT 1* (TF) BARRIER (TD)", "NOT -1* (TB) BARRIER (TD)", "NOT 1* (TF) BARRIER (TC)", "NOT 1* (TF) BARRIER (TE)",
            "NOT 1* (TF) BARRIER (TB)", "NOT 1* (TG) BARRIER (TD)", "NOT 1* (TF) CBARRIER (TD)", "1* (TF) BARRIER (TC)",
            "1* (TF) BARRIER (TE)", "0* (TB) BARRIER (TF)", "NOT 0* (TB) BARRIER (TF)", "0* (TF) BARRIER EOS OR BOS",
            "1C (TB)", "0 (TA) LINK 1 (TB)", "0 (TA) LINK 1 (TC)", "1 (TB) LINK 1 (TC) LINK 1 (TD)", "NOT 1 (TB) LINK 1 (TC)",
            "((NEGATE -1 BOS OR (TX)) OR (NEGATE 1 EOS OR (TX)))", "(0 (TA) LINK 1 (TB)) OR (0 (TC) LINK 1 (TD))",
            "0 (TA) LINK (1 (TB)) OR (1 (TX))", "@1 (TA)", "@-1 (TG)", "-1 (TB) LINK -1 BOS", "NEGATE -1 (TB) LINK -1 (TA)"]:
    add("barrier/link: " + ctx, FIRE % ctx, ABCDEFG)
# rule behaviour
H = D + "SECTION\n"
inp = '"<a>"\n\t"a" Y\n\t"a" W\n\t"a" Z\n'
add("ADD in a later section does not re-run an earlier REMOVE", H + "REMOVE (@m) ;\nSECTION\nADD (@m) (Y) ;\n", inp)
add("SUBSTITUTE adding a tag does not re-run an earlier REMOVE", H + "REMOVE (m) ;\nSECTION\nSUBSTITUTE (Y) (Y m) TARGET (Y) ;\n", inp)
add("REMOVE does re-run earlier sections", H + "SELECT (W) IF (NOT 1* (Q)) ;\nSECTION\nREMOVE (Q) ;\n",
    '"<a>"\n\t"a" Y\n\t"a" W\n"<b>"\n\t"b" Q\n\t"b" R\n')
add("the last reading is never removed", H + "REMOVE (Y) ;\n", '"<a>"\n\t"a" Y\n\t"a" Y K\n')
add("SELECT on one reading does nothing", H + "SELECT (Y) ;\n", '"<a>"\n\t"a" W\n')
add("identical readings are merged", H + "REMOVE (ZZZ) ;\n", '"<a>"\n\t"a" N Sg\n\t"a" N Sg\n\t"a" V\n')
add("same tags, other order, are merged", H + "REMOVE (ZZZ) ;\n", '"<a>"\n\t"a" N Sg\n\t"a" Sg N\n\t"a" V\n')
add("SUBSTITUTE making a duplicate", H + "SUBSTITUTE (B) (A) TARGET (*) ;\n", '"<a>"\n\t"a" N A\n\t"a" N B\n\t"a" V\n')
add("SUBSTITUTE removing a tag making a duplicate", H + "SUBSTITUTE (B) (*) TARGET (*) ;\n", '"<a>"\n\t"a" N A\n\t"a" N A B\n\t"a" V\n')
add("SUBSTITUTE keeps the place of the old tag", H + "SUBSTITUTE (B) (X Y) TARGET (*) ;\n", '"<a>"\n\t"a" A B C\n\t"a" V\n')
add("MAP once", H + "MAP (@x) (N) ;\nMAP (@y) (N) ;\n", '"<a>"\n\t"a" N\n\t"a" V\n')
add("IFF", H + "IFF (W) (NEGATE 1* (Q)) ;\n", '"<a>"\n\t"a" Y\n\t"a" W\n"<b>"\n\t"b" Q\n\t"b" R\n"<.>"\n\t"." S\n')
add("SETS heading", "SETS\nLIST BOS = (>>>) ;\nLIST EOS = (<<<) ;\nDELIMITERS = \"<.>\" ;\nSECTION\nADD (@fire) (*) IF (-1 BOS) ;\n", ABCDE)
add("CG-2 style contexts after the target", H + "SELECT (W) (1 (Q)) ;\n", '"<a>"\n\t"a" Y\n\t"a" W\n"<b>"\n\t"b" Q\n\t"b" R\n')
add("unification", "DELIMITERS = \"<.>\" ;\nLIST Case = (n sg) (n pl) ;\nSECTION\nSELECT $$Case IF (1 $$Case) ;\n",
    '"<a>"\n\t"a" n sg\n\t"a" n pl\n\t"a" v\n"<b>"\n\t"b" n pl\n\t"b" x\n')
add("set operators", "DELIMITERS = \"<.>\" ;\nLIST A = a b c d ;\nLIST B = c d e f ;\nSECTION\n"
    "ADD (@union) A OR B ;\nADD (@except) A - B ;\nADD (@difference) A \\ B ;\nADD (@symdiff) A ∆ B ;\nADD (@intersect) A ∩ B ;\nADD (@product) A + B ;\n",
    '"<s>"\n' + "".join('\t"s" %s\n' % t for t in ["a", "b c", "c d", "d e", "e f", "f a", "a e"]))
add("static tags after the word form", H + "ADD (@seen) (*) (0 (stat)) ;\n", '"<a>" stat ic\n\t"a" Y\n"<b>"\n\t"b" Y\n')
add("compound readings (sub-readings) travel with their reading", H + "REMOVE (W) ;\n",
    '"<a>"\n\t"a" Y\n\t\t"a1" Y1\n\t"a" W\n\t\t"a2" W1\n')


add("a reading that arrives mapped is not mapped again", H + "MAP (@y) (N) ;\n", '"<a>"\n\t"a" N @x\n\t"a" V\n')
add("ADD still adds to a mapped reading", H + "ADD (@y) (N) ;\n", '"<a>"\n\t"a" N @x\n\t"a" V\n')
for ctx in ["((-1 (TB)) LINK -1 (TA))", "((1 (TB)) LINK 1 (TC)) OR (0 (TX))", "((1 (TX)) LINK 1 (TC)) OR ((1 (TB)) LINK 1 (TX)) OR (-1 (TA))",
            "((1 (TB)) LINK 1 (TC)) LINK 1 (TD)", "((0 (TA)) OR (0 (TB))) LINK 1 (TC)"]:
    add("OR/LINK: " + ctx, FIRE % ctx, ABCDEFG)


def vislcg3(grammar, text):
    d = tempfile.mkdtemp()
    open(d + "/g.cg3", "w", encoding="utf-8").write(grammar)
    open(d + "/i.txt", "w", encoding="utf-8").write(text)
    r = subprocess.run(["vislcg3", "-g", d + "/g.cg3", "-I", d + "/i.txt"], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise SystemExit("vislcg3 refused case:\n%s\n%s" % (grammar, r.stderr))
    return r.stdout


for c in cases:
    c["expected"] = vislcg3(c["grammar"], c["input"])
json.dump(cases, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("wrote %d cases to %s" % (len(cases), OUT))
