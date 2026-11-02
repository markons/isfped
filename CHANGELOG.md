# Changelog

## 1.2.0 - 2026-11-02

### New

- **Tabs: several files at once.** `python isfped.py a.txt b.txt` opens each file in its own tab.
  - `EDIT` / `VIEW` / `BROWSE [file]` open another file in a new tab (no file: a file dialog);
    *File > Open* and *Recent Files* do the same.
  - An empty, unused tab is used for the next file; opening a file that is already open goes to
    its tab.
  - `SWAP NEXT|PREV|n` or Ctrl+Tab / Ctrl+Shift+Tab switch tabs; END (F3) closes a tab.
    *File > New Tab*, *Close Tab* and *Exit* are in the menu.
  - Each tab has its own undo, labels, excluded lines, HEX setting, scroll amount and command
    history. A tab title ending in ` *` has unsaved changes; the window title names the file.
  - Closing the window asks about every tab with unsaved changes.
- **Full path of the file**, in a row above the command line together with the mode. It is
  read-only but selectable (Ctrl+C); the *Copy path* button and *File > Copy Full Path* copy it
  to the clipboard.
- **`HEX ON|OFF`** primary command (`HEX` alone = ON, `HEX VERT` accepted): two hex rows (high
  and low nibble) under every data line, rebuilt from the data on each Enter. The rows are not
  saved and do not mark the file as changed; the hex rows of an excluded line are excluded with
  it; HEX stays on for the next file opened in the tab. `HEX DATA` reports "not supported".
- **`MD` / `MDn` / `MDD..MDD`** line commands (make data): COLS rulers, hex rows and COMPARE's
  removed lines become ordinary lines of the file. On a data line MD changes nothing.
- **`COLS`** line command: a `=COLS>` ruler row (`----+----1----+----2...`) after the line,
  scrolling with the data. Not saved; D or RESET removes it, `LOCATE SPECIAL` finds it.
- **Picture strings** `P'...'` in FIND, CHANGE and EXCLUDE: `=` any, `@` letter, `#` digit,
  `-` non-digit, `$` special, `^` or `¬` non-blank, `.` non-displayable, `<` lowercase,
  `>` uppercase; other characters match themselves in either case. In a CHANGE picture
  to-string, `=` keeps the found character and `<` / `>` change its case (same length needed).
  RCHANGE repeats it.
- HELP: END/EXIT, RFIND, RETRIEVE, a *Files and tabs* section and the tab keys.
- README rewritten as a reference following the built-in help; this changelog.

### Fixed

- **The command window was not closed on exit** when isfped was started through a launcher
  (`py isfped.py`, a venv's `python.exe`): only a direct `cmd.exe` parent was closed. The search
  now passes Python launchers. CANCEL, *Exit* and the window's close button also close it now,
  not only END - always when the last tab closes. A PowerShell window is left open on purpose.
- **Any line command dropped COMPARE's markings**, so the removed lines COMPARE showed silently
  became data and were saved. They now stay display rows.
- `python isfped.py file` ignored the file (the README promised it).
- Case-insensitive FIND/EXCLUDE could highlight the wrong span when case folding changes the
  length of the text (e.g. `ß` -> `ss`); they now use the same matching as CHANGE.
- FIND and EXCLUDE no longer match on HX/COLS rows (CHANGE already skipped them).

### Changed

- RESET removes hex, COLS and COMPARE rows without marking the file as changed.
- The END prompt names the file ("Save changes to x.txt before exiting?").
- File > Open asks for the file, then opens it in a tab (see above).

### Internals

- `INFO_PREFIXES` (`=HEX> `, `=COLS>`) marks display-only rows everywhere `=HEX> ` was checked.
- `cols_ruler()` builds the ruler for the header and for COLS rows.
- `_search_pattern()` compiles one regex for every FIND/CHANGE/EXCLUDE string (plain, exact or
  picture); `_picture_replace()` applies a picture to-string.
- `_rebuild_rows()` adds/removes display rows as one undo step while keeping labels, excluded
  lines, inserted lines, COMPARE marks, the find highlight, pending commands and the screen on
  their rows. HEX ON/OFF and RESET use it; `_sync_hex_rows()` runs on every Enter.
- `_compare_tags()` / `_set_compare_tags()` carry COMPARE marks across a rebuild.
- `ISPFEditor(root, parent=None, app=None)`: without `parent`/`app` it fills the window alone
  (as the tests use it); `EditorApp` owns the window, the menu and a `ttk.Notebook` of editors.
  `build_menubar()` builds the menu for both; window-level keys come from `_root_keys()`.
- `_command_shell_pid()` finds the cmd.exe to close; `_close()` closes a tab or the window.
- Tests: 221 -> 251 (COLS, picture strings, HEX, MD, file path, tabs, closing the command
  window); `tests/harness.py` has an `AppDriver` for the tabbed window.

## 1.1.0 - 2026-10-29

Regression tests, bug fixes and SPFLite behaviour.

- A regression suite (`tests/`) drives the editor like a user and compares 107 scenarios with
  SPFLite3; SPFLite's results are recorded, so the tests run without it.
- Fixed: a file ending in a newline no longer shows an extra empty last line (SORT moved it to
  the top), and the final newline is kept on SAVE; TS/TF/TE are refused together with other line
  commands; FIND/CHANGE PREFIX/SUFFIX match the start/end of a word, not whole words; the cursor
  is at the top after opening, so the first FIND does not wrap; a typed RETRIEVE brings back the
  previous command, not itself; data shift `<` `>` follows ISPF/SPFLite (a word in column 1
  stays put).
- As in SPFLite: SORT ignores case; trailing blanks are trimmed on SAVE; primary UC/LC need a
  line range (`ALL`, `.a` or `.a .b`); a D/C/M/UC/LC count must not run past the last line;
  `.n` line-number pseudo labels in primary commands.

## Initial commit - 2026-10-28

Initial version: ISPF-style Tkinter editor.
