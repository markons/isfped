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
  `F L S` on excluded lines; labels `.xxxxx`.
- **Primary commands:** `FIND`, `CHANGE`, `LOCATE`, `RESET`, `EXCLUDE`/`X ALL`, `LEFT`/`RIGHT`,
  `UP`/`DOWN` (`n|MAX|PAGE|HALF|CSR`), `UNDO`/`REDO`, `CANCEL`.
- **Keys:** Home → command line; Tab/Shift-Tab between number area and text; F7/F8 (PgUp/PgDn) scroll.
