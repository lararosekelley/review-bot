"""Run the mining pipeline end to end.

usage: run_all.py CODE_ROOT --public NAME... [--private NAME...] [--no-fetch]
CODE_ROOT holds checkouts of the mined repos. Public curation lives in
eval/mine/curation/, private curation in eval/cases-private/curation/.
"""
import argparse
import subprocess
import sys
from pathlib import Path

OWNER = "lararosekelley"
EVAL = Path(__file__).resolve().parent.parent
MINE = EVAL / "mine"
RAW = EVAL / "raw"


def run(script, *args):
    subprocess.run([sys.executable, "-I", str(MINE / script), *map(str, args)], check=True)


def main():
    parser = argparse.ArgumentParser(usage=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--public", nargs="+", default=[])
    parser.add_argument("--private", nargs="*", default=[])
    parser.add_argument("--no-fetch", action="store_true")
    args = parser.parse_args()
    root = args.root
    for name in args.public + args.private:
        slug = f"{OWNER}/{name}"
        if not args.no_fetch:
            run("fetch_prs.py", RAW, slug)
            run("fetch_comments.py", RAW, slug, 1)
        run("mine_fixes.py", root / name, RAW / name)
        private = name in args.private
        out = EVAL / ("cases-private" if private else "cases")
        curation = (out / "curation" if private else MINE / "curation") / f"{name}.json"
        if curation.exists():
            run("build_cases.py", root / name, slug, RAW / name, curation, out)
    run("write_index.py", EVAL / "cases", EVAL / "cases-private")


if __name__ == "__main__":
    main()
