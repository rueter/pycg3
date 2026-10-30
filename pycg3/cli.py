"""Command-line interface compatible with vislcg3."""

import argparse
import sys
from pycg3 import __version__
from pycg3.grammar import GrammarParser
from pycg3.engine import Disambiguator


def main(args=None):
    parser = argparse.ArgumentParser(
        prog="pycg3",
        description="A pure Python implementation of VISL CG-3 (Constraint Grammar 3)"
    )
    parser.add_argument(
        "-g", "--grammar",
        required=True,
        help="Grammar file to load and apply."
    )
    parser.add_argument(
        "-i", "-I", "--input",
        dest="input_file",
        default=None,
        help="Input file to read (default: stdin)."
    )
    parser.add_argument(
        "-o", "-O", "--output",
        dest="output_file",
        default=None,
        help="Output file to write (default: stdout)."
    )
    parser.add_argument(
        "-e", "--show-rules",
        action="store_true",
        help="Mark modified/selected readings with <<<."
    )
    parser.add_argument(
        "-t", "--trace",
        action="store_true",
        help="Provide trace output of rules that modified/selected readings."
    )
    parser.add_argument(
        "-p", "--pipe-deleted",
        action="store_true",
        help="Output deleted readings prefixed with ;."
    )
    parser.add_argument(
        "-s", "--sections",
        type=int,
        default=None,
        help="Number of sections to execute."
    )
    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"pycg3 {__version__} (compatible with VISL CG-3)",
        help="Show version information and exit."
    )

    parsed = parser.parse_args(args)

    # Read grammar
    try:
        with open(parsed.grammar, "r", encoding="utf-8", errors="replace") as gf:
            grammar_text = gf.read()
    except Exception as e:
        sys.stderr.write(f"Error opening grammar file '{parsed.grammar}': {e}\n")
        sys.exit(1)

    grammar = GrammarParser().parse(grammar_text)
    engine = Disambiguator(grammar, trace=parsed.trace)

    # Input stream
    if parsed.input_file:
        try:
            in_stream = open(parsed.input_file, "r", encoding="utf-8", errors="replace")
        except Exception as e:
            sys.stderr.write(f"Error opening input file '{parsed.input_file}': {e}\n")
            sys.exit(1)
    else:
        in_stream = sys.stdin

    # Output stream
    if parsed.output_file:
        try:
            out_stream = open(parsed.output_file, "w", encoding="utf-8")
        except Exception as e:
            sys.stderr.write(f"Error opening output file '{parsed.output_file}': {e}\n")
            sys.exit(1)
    else:
        out_stream = sys.stdout

    try:
        for win in engine.run_stream(in_stream, num_sections=parsed.sections):
            formatted = win.to_text(
                show_rules=parsed.show_rules,
                trace=parsed.trace,
                pipe_deleted=parsed.pipe_deleted
            )
            out_stream.write(formatted)
            out_stream.write("\n")
            out_stream.flush()
    finally:
        if parsed.input_file:
            in_stream.close()
        if parsed.output_file:
            out_stream.close()


if __name__ == "__main__":
    main()
