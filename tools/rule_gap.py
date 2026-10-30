#!/usr/bin/env python3
"""rule_gap.py REAL_OUT PYCG3_OUT - which rules vislcg3 applied that pycg3 did not (and the reverse), by rule label,
counted over deleted readings (';' lines). Both outputs must have been made with -t / trace=True."""
import collections
import sys


def deleted(path):
    out, cohort = {}, None
    ci = -1
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith('"<'):
            ci += 1
            cohort = ci
        elif line.startswith(";\t") and not line.startswith(";\t\t") and cohort is not None:
            reading = line[2:]
            parts = reading.split(" ")
            labels = [p for p in parts if p.split(":")[0] in ("REMOVE", "SELECT", "SUBSTITUTE", "MAP", "ADD", "REPLACE", "IFF")]
            core = " ".join(p for p in parts if p not in labels)
            out.setdefault((cohort, core), labels)
    return out


real, py = deleted(sys.argv[1]), deleted(sys.argv[2])
missing = collections.Counter()
extra = collections.Counter()
example = {}
for key, labels in real.items():
    if key not in py and labels:
        missing[labels[-1]] += 1
        example.setdefault(labels[-1], key)
for key, labels in py.items():
    if key not in real and labels:
        extra[labels[-1]] += 1
        example.setdefault(labels[-1], key)
print("deleted by vislcg3 but kept (or differently handled) by pycg3:")
for lab, n in missing.most_common(25):
    print("  %4d  %s   e.g. cohort #%d: %s" % (n, lab, example[lab][0], example[lab][1][:70]))
print("deleted by pycg3 but not by vislcg3:")
for lab, n in extra.most_common(25):
    print("  %4d  %s   e.g. cohort #%d: %s" % (n, lab, example[lab][0], example[lab][1][:70]))
