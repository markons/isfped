# isfped

An ISPF-style editor clone written in Python with Tkinter.

Line commands are typed directly into the 6-column line-number area, as in ISPF.

## Run

```
python isfped.py [file]
```

Requires Python 3 with Tkinter (developed on Python 3.14).

## Features

- **Line commands:** `I D R C M A B UC LC ( ) X` with counts; block forms `DD CC MM RR XX UCC LCC (( ))`;
  `F L S` on excluded lines; labels `.xxxxx`, and `.n` for line n in primary commands.
- **As in SPFLite:** SORT ignores case; trailing blanks are trimmed on SAVE; primary `UC`/`LC`
  need a line range (`ALL`, `.a` or `.a .b`); a D/C/M/UC/LC count must not run past the last line.
- **Primary commands:** `FIND`, `CHANGE`, `LOCATE`, `RESET`, `EXCLUDE`/`X ALL`, `LEFT`/`RIGHT`,
  `UP`/`DOWN` (`n|MAX|PAGE|HALF|CSR`), `UNDO`/`REDO`, `CANCEL`.
- **Keys:** Home → command line; Tab/Shift-Tab between number area and text; F7/F8 (PgUp/PgDn) scroll.
- **Enter** follows SPFLite: it runs pending commands, otherwise moves to the next line command
  field (it never splits a line). Right Ctrl, keypad Enter and Shift/Ctrl/Alt+Enter act as the
  3270 Enter key. Lines from `I` are temporary until typed on.

## Tests

```
python -m unittest discover -s tests
```

- `tests/test_isfped.py` - editor behaviour: line/primary commands, pending blocks, inserted
  lines, labels, excluded lines, FIND/CHANGE, UNDO, HX, COMPARE, file commands, scrolling.
- `tests/test_vs_spflite.py` - the scenarios in `tests/cases.py` must save the same file as
  SPFLite3. SPFLite's results are recorded in `tests/spflite_results.json`, so SPFLite is not
  needed to run the tests. Deliberate differences run as expected failures.
- `python tests/compare_spflite.py` re-runs the scenarios in SPFLite3 (Windows; default
  `C:\apps\SPFLite\SPFLite3.exe`, override with `SPFLITE_EXE`) and refreshes the recorded results.
