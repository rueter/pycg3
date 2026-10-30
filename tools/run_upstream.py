#!/usr/bin/env python3
# encoding: UTF-8
"""
run_upstream.py - run pycg3 on the CG-3 project's own regression tests (test/T_*: grammar.cg3, input.txt,
expected.txt, optional args.txt) and report which pass.

    python3 tools/run_upstream.py /path/to/cg3/test              # all
    python3 tools/run_upstream.py /path/to/cg3/test T_Barrier    # those whose name contains the text, with a diff
"""
import difflib
import io
import os
import resource
import signal
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from pycg3.grammar import GrammarParser
from pycg3.engine import Disambiguator


def run(path):
    args = open(os.path.join(path, "args.txt")).read().strip() if os.path.exists(os.path.join(path, "args.txt")) else ""
    with open(os.path.join(path, "grammar.cg3"), encoding="utf-8") as fh:
        engine = Disambiguator(GrammarParser().parse(fh.read()))
    with open(os.path.join(path, "input.txt"), encoding="utf-8") as fh:
        got = "".join(w.to_text(trace=("-t" in args.split()), pipe_deleted=("-t" in args.split()) or ("-p" in args.split())) + "\n"
                      for w in engine.run_stream(fh))
    want = open(os.path.join(path, "expected.txt"), encoding="utf-8").read()
    norm = lambda t: [l.rstrip() for l in t.split("\n") if l.strip()]
    return args, norm(want), norm(got)


def main():
    root = sys.argv[1]
    only = sys.argv[2] if len(sys.argv) > 2 else ""
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))
    ok, bad, err = [], [], []
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name)
        if not name.startswith("T_") or only not in name or not os.path.exists(os.path.join(path, "grammar.cg3")):
            continue
        signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("took more than 10 s")))
        signal.alarm(10)
        try:
            args, want, got = run(path)
            signal.alarm(0)
        except Exception as e:
            signal.alarm(0)
            err.append((name, "%s: %s" % (type(e).__name__, e)))
            continue
        if want == got:
            ok.append(name)
        else:
            bad.append((name, args, want, got))
    print("pass %d, fail %d, error %d" % (len(ok), len(bad), len(err)))
    for name, args, want, got in bad:
        print("FAIL", name, ("[args: %s]" % args) if args else "")
        if only:
            print("\n".join(difflib.unified_diff(want, got, "expected", "pycg3", lineterm="", n=2)))
    for name, msg in err:
        print("ERROR", name, msg[:120])


if __name__ == "__main__":
    main()
