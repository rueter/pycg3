#!/usr/bin/env python3
# encoding: UTF-8
"""
diff_vislcg3.py - run pycg3 and the real vislcg3 on the same CG input and compare, sentence by sentence,
the readings that survive.

    python3 tools/diff_vislcg3.py --grammar G.cg3 --input corpus.cg          # an existing CG stream
    python3 tools/diff_vislcg3.py --grammar G.cg3 --text-file sentences.txt --tokeniser T.pmhfst
                                                                              # one sentence per line, tokenised first
    options: --show N (how many differing sentences to print, default 5), --trace (compare the rule traces too),
             --cpu-limit S (CPU seconds for pycg3, default 600), --work DIR (where the files go)
"""
import argparse
import os
import resource
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


def windows(text, keep_deleted=False):
    """[(word list)] one entry per cohort: (wordform, [reading lines]) grouped into sentences by blank/':' lines."""
    out, cur, word = [], [], None
    for line in text.split("\n"):
        if line.startswith('"<'):
            word = [line, []]
            cur.append(word)
        elif line.startswith(("\t", " ")) and word is not None:
            word[1].append(line.rstrip())
        elif line.startswith(";\t") and word is not None and keep_deleted:
            word[1].append(line.rstrip())
    return cur


def strip_trace(line):
    parts = line.split(" ")
    while parts and (parts[-1].startswith(("REMOVE", "SELECT", "SUBSTITUTE", "MAP", "ADD", "REPLACE")) or parts[-1] == ""):
        parts.pop()
    return " ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--grammar", required=True)
    ap.add_argument("--input")
    ap.add_argument("--text-file")
    ap.add_argument("--tokeniser")
    ap.add_argument("--show", type=int, default=5)
    ap.add_argument("--trace", action="store_true")
    ap.add_argument("--cpu-limit", type=int, default=600)
    ap.add_argument("--work", default=tempfile.mkdtemp(prefix="pycg3diff_"))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)

    if a.text_file:
        a.input = os.path.join(a.work, "input.cg")
        with open(a.text_file, "rb") as fh, open(a.input, "wb") as out:
            subprocess.run(["hfst-tokenise", "-g", a.tokeniser], stdin=fh, stdout=out, check=True)

    real_path = os.path.join(a.work, "real.out")
    with open(a.input, "rb") as fh, open(real_path, "wb") as out:
        subprocess.run(["vislcg3", "-g", a.grammar, "-t"], stdin=fh, stdout=out, stderr=subprocess.DEVNULL, check=True)

    resource.setrlimit(resource.RLIMIT_CPU, (a.cpu_limit, a.cpu_limit))
    from pycg3.grammar import GrammarParser
    from pycg3.engine import Disambiguator
    with open(a.grammar, encoding="utf-8") as fh:
        engine = Disambiguator(GrammarParser().parse(fh.read()), trace=True)
    py_path = os.path.join(a.work, "pycg3.out")
    with open(a.input, encoding="utf-8") as fh, open(py_path, "w", encoding="utf-8") as out:
        for win in engine.run_stream(fh):
            out.write(win.to_text(trace=True, pipe_deleted=True) + "\n")

    real = windows(open(real_path, encoding="utf-8").read(), keep_deleted=False)
    py = windows(open(py_path, encoding="utf-8").read(), keep_deleted=False)
    norm = (lambda l: l) if a.trace else strip_trace
    n_cohorts, bad, bad_readings = 0, [], 0
    if len(real) != len(py):
        print("cohort counts differ: vislcg3 %d, pycg3 %d" % (len(real), len(py)))
    for i, (r, p) in enumerate(zip(real, py)):
        n_cohorts += 1
        rr = [norm(x) for x in r[1]]
        pp = [norm(x) for x in p[1]]
        if rr != pp:
            bad.append((i, r[0], rr, pp))
            bad_readings += 1
    print("cohorts compared: %d, identical: %d (%.1f%%), different: %d" % (
        n_cohorts, n_cohorts - len(bad), 100.0 * (n_cohorts - len(bad)) / max(1, n_cohorts), len(bad)))
    for i, w, rr, pp in bad[:a.show]:
        print("\n#%d %s" % (i, w))
        print("  vislcg3:", *rr, sep="\n    ")
        print("  pycg3:  ", *pp, sep="\n    ")
    print("\nfiles in", a.work)


if __name__ == "__main__":
    main()
