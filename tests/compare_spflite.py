"""Run every scenario in tests/cases.py through isfped and SPFLite3 and report
where the saved files differ.

    python tests/compare_spflite.py            # all cases
    python tests/compare_spflite.py "C ALL"    # cases whose name contains "C ALL"

SPFLite's results are stored in tests/spflite_results.json, which the unit
tests (test_vs_spflite.py) use, so they run without SPFLite installed.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases  # noqa: E402
import spflite_oracle  # noqa: E402
from harness import run_case  # noqa: E402

RESULTS = HERE / "spflite_results.json"


def main(argv):
    if not spflite_oracle.available():
        sys.exit(f"SPFLite not found at {spflite_oracle.SPFLITE}")
    selected = [c for c in cases.CASES if not argv or any(a in c[0] for a in argv)]
    stored = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    same = differ = 0
    try:
        for name, lines, steps in selected:
            try:
                spf, log = spflite_oracle.run(lines, steps)
            except RuntimeError:
                try:    # SPFLite is sometimes slow to start: one more try
                    spf, log = spflite_oracle.run(lines, steps, timeout=40)
                except RuntimeError as exc:
                    print(f"ERROR   {name}: {exc}")
                    continue
            stored[name] = {"input": lines, "commands": spflite_oracle.to_commands(steps),
                            "output": spf, "log": log}
            ours, statuses = run_case(lines, steps)
            if ours == spf:
                same += 1
                print(f"SAME    {name}")
            else:
                differ += 1
                print(f"DIFFER  {name}")
                print(f"   SPFLite: {spf}")
                print(f"   isfped : {ours}")
                for rc, cmd, msg in log:
                    print(f"   spf  rc={rc} {cmd} -> {msg}")
                for status in statuses:
                    print(f"   isfped  {status}")
            sys.stdout.flush()
    finally:
        spflite_oracle.cleanup()
        RESULTS.write_text(json.dumps(stored, indent=1, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(f"\n{same} same, {differ} different, of {len(selected)}")


if __name__ == "__main__":
    main(sys.argv[1:])
