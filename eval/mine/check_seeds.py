"""Check that each seeded case still builds and passes its repo's tests.

    python3 -I eval/mine/check_seeds.py [CASE ...]

A seed that the tests catch is not a defect a reviewer has to find, so it does
not belong in the case set. Each case is checked out as a replay would see it,
in a scratch directory, and its `seed.check` command runs there at low priority.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "harness"))
import replay  # noqa: E402
import units  # noqa: E402


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cases", nargs="*", type=Path, help="case files (default: every seeded case)")
    p.add_argument("--src-root", type=Path, default=Path.home() / "Code/personal")
    p.add_argument("--cache", type=Path, default=Path.home() / ".cache/review-bot-eval/seed-check",
                   help="build caches, kept between runs and shared per repo")
    args = p.parse_args()

    failed = []
    with tempfile.TemporaryDirectory(prefix="seed-check-") as work:
        for unit in units.load(args.cases).values():
            if not unit.get("seed"):
                continue
            repo_dir = replay.checkout(unit, args.src_root, Path(work))
            target = args.cache / unit["repo"].replace("/", "__")
            env = {**os.environ, "CARGO_TARGET_DIR": str(target / "cargo")}
            cmd = ["nice", "-n", "19", "ionice", "-c3", "sh", "-c", unit["seed"]["check"]]
            proc = subprocess.run(cmd, cwd=repo_dir, env=env, capture_output=True, text=True)
            ok = proc.returncode == 0
            print(f"{unit['id']}: {'ok' if ok else 'FAILED'}")
            if not ok:
                failed.append(unit["id"])
                print((proc.stdout + proc.stderr)[-3000:])
    if failed:
        sys.exit(f"{len(failed)} seeded case(s) fail their checks: {', '.join(failed)}")


if __name__ == "__main__":
    main()
