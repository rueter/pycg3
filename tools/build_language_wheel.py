#!/usr/bin/env python3
# encoding: UTF-8
"""
build_language_wheel.py - make the wheel pycg3-lang-CODE: the analyser FST and the Constraint Grammars of one
GiellaLT language, found by pycg3 (and so by UralicNLP) through the entry point group "pycg3.languages".

    python3 tools/build_language_wheel.py --lang myv --out /somewhere/wheels
    python3 tools/build_language_wheel.py --lang mdf --stages disambiguator --version 2026.10.30

Takes from lang-CODE (default /Users/jackrueter/Desktop/Github/giellalt/lang-CODE, or --src):
    src/fst/analyser-disamb-gt-desc.hfstol      (--analyser to take another)
    src/cg3/<stage>.cg3                         for each of --stages, in the order given (default: disambiguator,functions;
                                                dependency is not run by pycg3 yet)
The version is the date (YEAR.MONTH.DAY) unless --version is given. Needs `pip install build`.
The wheel is pure Python with data files, so one wheel (py3-none-any) serves every platform.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

INIT = '''"""The FST and the Constraint Grammars of {code} for pycg3 ({stages})."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "data"


def language():
    from pycg3.languages import LanguageData
    return LanguageData.from_directory(ROOT, "{code}")
'''

PYPROJECT = '''[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "pycg3-lang-{code}"
version = "{version}"
description = "The analyser FST and Constraint Grammars ({stages}) of {code}, for pycg3 / UralicNLP"
requires-python = ">=3.9"
dependencies = ["pycg3>=0.2.0"]
license = "GPL-3.0-or-later"
classifiers = ["Topic :: Text Processing :: Linguistic"]

[project.entry-points."pycg3.languages"]
{code} = "pycg3_lang_{pkg}:language"

[tool.setuptools]
packages = ["pycg3_lang_{pkg}"]

[tool.setuptools.package-data]
pycg3_lang_{pkg} = ["data/*"]
'''


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git(src, *args):
    try:
        return subprocess.run(["git", "-C", src, *args], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", required=True, help="language code, e.g. myv")
    ap.add_argument("--src", help="the lang-CODE checkout (default /Users/jackrueter/Desktop/Github/giellalt/lang-CODE)")
    ap.add_argument("--stages", default="disambiguator,functions", help="comma-separated: disambiguator,functions,dependency")
    ap.add_argument("--analyser", help="the .hfstol to ship (default src/fst/analyser-disamb-gt-desc.hfstol)")
    ap.add_argument("--version", help="default: today's date as YEAR.MONTH.DAY")
    ap.add_argument("--out", required=True, help="directory for the wheel")
    a = ap.parse_args()

    code = a.lang
    pkg = code.replace("-", "_")
    src = a.src or "/Users/jackrueter/Desktop/Github/giellalt/lang-%s" % code
    stages = [s for s in a.stages.split(",") if s]
    analyser = a.analyser or os.path.join(src, "src", "fst", "analyser-disamb-gt-desc.hfstol")
    today = datetime.date.today()
    version = a.version or "%d.%d.%d" % (today.year, today.month, today.day)
    for path in [analyser] + [os.path.join(src, "src", "cg3", s + ".cg3") for s in stages]:
        if not os.path.exists(path):
            sys.exit("missing: " + path)

    work = tempfile.mkdtemp(prefix="pycg3-lang-%s-" % code)
    try:
        package = os.path.join(work, "pycg3_lang_" + pkg)
        data = os.path.join(package, "data")
        os.makedirs(data)
        shutil.copy(analyser, data)
        for s in stages:
            shutil.copy(os.path.join(src, "src", "cg3", s + ".cg3"), data)
        meta = {
            "language": code,
            "analyser": os.path.basename(analyser),
            "stages": stages,
            "version": version,
            "source": {"repository": git(src, "remote", "get-url", "origin"), "commit": git(src, "rev-parse", "HEAD"),
                       "built": today.isoformat()},
            "sha256": {os.path.basename(analyser): sha256(analyser),
                       **{s + ".cg3": sha256(os.path.join(data, s + ".cg3")) for s in stages}},
        }
        with open(os.path.join(data, "metadata.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=1)
        with open(os.path.join(package, "__init__.py"), "w", encoding="utf-8") as fh:
            fh.write(INIT.format(code=code, stages=", ".join(stages)))
        with open(os.path.join(work, "pyproject.toml"), "w", encoding="utf-8") as fh:
            fh.write(PYPROJECT.format(code=code, pkg=pkg, version=version, stages=", ".join(stages)))
        os.makedirs(a.out, exist_ok=True)
        run = subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", os.path.abspath(a.out), work], capture_output=True, text=True)
        if run.returncode != 0:
            sys.exit("build failed (pip install build?):\n" + run.stdout[-1500:] + run.stderr[-1500:])
        print(run.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
