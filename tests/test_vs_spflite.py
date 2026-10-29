"""isfped must save the same file as SPFLite3 for every scenario in cases.py.

The SPFLite results are recorded in spflite_results.json (refresh them with
compare_spflite.py), so these tests don't need SPFLite. Scenarios where isfped
knowingly differs are listed in KNOWN_DIFFERENCES and run as expected failures.
"""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cases  # noqa: E402
from harness import run_case  # noqa: E402

RESULTS = json.loads((HERE / "spflite_results.json").read_text(encoding="utf-8"))

# case name -> why isfped's result differs from SPFLite's (expected failures)
KNOWN_DIFFERENCES = {
}

# Scenarios SPFLite cannot run faithfully from a macro: the recorded result is
# not what a user typing the same commands gets, so it is no reference.
# (isfped's behaviour for these is covered in test_isfped.py.)
MACRO_LIMITS = {
    "X then D on block": "LINE 'D' .n hits one line, not the excluded block",
    "XX then CC on block A": "LINE 'C' .n hits one line, not the excluded block",
    "X ALL, F on block shows first": "LINE 'F2' is rejected on the excluded block",
    "X ALL, L on block shows last": "LINE 'L3' is rejected on the excluded block",
    "X ALL, FIND ALL, DELETE ALL X": "FIND ALL in a macro does not show excluded lines",
    "labels DELETE range": "DELETE .a .b in a macro deleted one line, against "
                           "SPFLite's own documentation",
    "pseudo labels DELETE .3 .5": "DELETE .a .b in a macro deleted one line, against "
                                  "SPFLite's own documentation",
    "C then RCHANGE": "the cursor does not move in macro mode, so RCHANGE stays put",
    "FIND then C NEXT": "the cursor does not move in macro mode",
    "UNDO line command": "UNDO is not supported in macro mode",
    "UNDO twice": "UNDO is not supported in macro mode",
}


class MatchesSPFLite(unittest.TestCase):
    pass


def _make(name, lines, steps):
    def test(self):
        expected = RESULTS[name]["output"]
        ours, statuses = run_case(lines, steps)
        log = "\n".join(f"  SPFLite rc={rc} {cmd} -> {msg}"
                        for rc, cmd, msg in RESULTS[name]["log"])
        self.assertEqual(ours, expected,
                         f"\n{log}\n  isfped: " + " / ".join(map(str, statuses)))
    if name in MACRO_LIMITS:
        test = unittest.skip("no SPFLite reference: " + MACRO_LIMITS[name])(test)
    elif name in KNOWN_DIFFERENCES:
        test = unittest.expectedFailure(test)
    test.__doc__ = name
    return test


for _name, _lines, _steps in cases.CASES:
    if _name in RESULTS:
        _attr = "test_" + "".join(ch if ch.isalnum() else "_" for ch in _name)
        setattr(MatchesSPFLite, _attr, _make(_name, _lines, _steps))


if __name__ == "__main__":
    unittest.main()
