# isfped

An ISPF-style editor written in Python with Tkinter. Line commands are typed directly into the
6-column line-number area and primary commands on the command line, as in IBM ISPF; where ISPF
and SPFLite differ, isfped mostly follows SPFLite.

The same reference is built in: press **F1** or type `HELP`. Changes are listed in
[CHANGELOG.md](CHANGELOG.md).

## Run

```
python isfped.py [file ...]
```

Each file opens in its own tab. Requires Python 3 with Tkinter (developed on Python 3.14, Windows).

## Screen

```
EDIT   C:\work\data\member.txt                                [Copy path]
Command > ________________________________________________    Scroll > CSR
=<COLS>----+----1----+----2----+----3----+----4----+----5----+----6----+---
****** ***************************** Top of Data **************************
000001 first line of the file
000002 second line
```

- **File row:** the mode (EDIT, VIEW, BROWSE) and the file's full path. Select the path and press
  Ctrl+C, or press *Copy path* (also *File > Copy Full Path*).
- **Command line:** primary commands. *Scroll* is the default amount for UP/DOWN and F7/F8.
- **Line-number area:** line commands; a typed command replaces the number and shows in red.
- **Tabs:** one per file. A tab title ending in `*` has unsaved changes.

## Primary commands

Type on the command line and press Enter.

### Files and tabs

| Command | Action |
|---|---|
| `SAVE` | Save the current file (trailing blanks are trimmed, as in SPFLite) |
| `END` / `EXIT` | Close the file, asking to save changes. The last tab closes the window and the cmd.exe window that started the editor |
| `CANCEL` / `CAN` | Discard changes and close the file |
| `EDIT` / `VIEW` / `BROWSE [file]` | Open another file in its own tab (no file: choose one) |
| `SWAP [NEXT\|PREV\|n]` | Go to the next, previous or n-th tab (also Ctrl+Tab / Ctrl+Shift+Tab) |
| `COPY file BEFORE\|AFTER .label [first last]` | Insert an external text file or its line range |
| `MOVE file BEFORE\|AFTER .label` | Insert an external text file and remove the source file |
| `CREATE file [.start .end \| first last]` | Write the buffer or a line range to a new file |
| `REPLACE file [.start .end \| first last]` | Write the buffer or a line range, creating or replacing the file |

Opening a file that is already open goes to its tab, and an empty new tab is used for the next
file opened.

### Find and change

| Command | Action |
|---|---|
| `FIND` / `F x [NEXT\|PREV\|FIRST\|LAST\|ALL] [CHARS\|WORD\|PREFIX\|SUFFIX] [X\|NX] [col1 col2] [.a .b]` | Search by direction, or count and highlight every hit with `ALL` |
| `CHANGE` / `C` / `CHA` / `CHG a b [...same options]` | Change one occurrence (NEXT by default); `ALL` changes every match |
| `RFIND` / `RF` | Repeat the last FIND (F5) |
| `RCHANGE` / `RCH` | Change the next occurrence with the last CHANGE options (F6) |
| `EXCLUDE` / `X string [ALL]` | Exclude the next line containing string, or every such line |
| `X ALL [.a .b]` | Exclude all lines, or all between two labels |

- `X` / `NX` limit the search to excluded / shown lines; two numbers limit it to columns; two
  labels limit it to a line range.
- `CHARS` matches anywhere, `WORD` whole words, `PREFIX` / `SUFFIX` the start / end of a word.
- **Case:** `F x` and `C a b` ignore upper/lower case. `F 'x'` and `C 'a' b` are case-sensitive.
  Quotes (`'x'` or `"x"`) are also needed for spaces or keywords: `F 'last one'`.
- **String forms:** `C'..'` (case-sensitive), `X'..'` (hex), `T'..'`, `P'..'` (picture).
- **Picture strings** (`P'..'`) match a kind of character at each position:

| Char | Matches | | Char | Matches |
|---|---|---|---|---|
| `=` | any character | | `$` | special (not a blank, letter or digit) |
| `@` | a letter | | `^` or `¬` | anything except a blank |
| `#` | a digit | | `.` | a non-displayable character (tab, control) |
| `-` | anything except a digit | | `<` / `>` | a lowercase / uppercase letter |

  Other characters match themselves in either case: `F P'##-@'`, `F P'B#'` finds `b1`.
  In a CHANGE picture to-string, `=` keeps the found character and `<` / `>` change its case;
  it must be as long as the from-string: `C ALL P'<<<' P'>=<'` turns `abc` into `Abc`.

### Moving around

| Command | Action |
|---|---|
| `UP` / `DOWN [n\|MAX\|PAGE\|HALF\|CSR]` | Scroll n lines (default: the Scroll field). MAX = top / last page, CSR = cursor line to bottom / top. An excluded block counts as one line |
| `LEFT` / `RIGHT [n\|MAX\|PAGE\|HALF]` | Scroll the data n columns (MAX = first / last column) |
| `LOCATE` / `L n` | Scroll to line number n |
| `LOCATE` / `L .lab` | Scroll to a label (`.ZF`/`.ZFIRST`, `.ZL`/`.ZLAST`, `.ZCSR` too) |
| `LOCATE category [FIRST\|LAST\|NEXT\|PREV]` | Find CHANGE, ERROR, EXCLUDED, LABEL, SPECIAL or COMMAND lines |

### Editing the whole file

| Command | Action |
|---|---|
| `SORT [.start .end] [X\|NX] [[A\|D] start_col end_col ...]` | Sort full lines or by up to five column ranges; ascending by default; upper and lower case sort alike |
| `SORT D` | Sort full lines in descending order |
| `DELETE` / `DEL ALL [X\|NX] [.start .end]` | Delete every selected line (X = excluded, NX = shown) |
| `DELETE .start .end` | Delete an inclusive range (line numbers are also accepted) |
| `UC` / `LC ALL \| .a [.b]` | Convert all lines, line .a or lines .a-.b to UPPER / lower case (a range is required) |
| `UNDO [ALL]` / `REDO` | Undo one interaction (or all), redo the last undone one |
| `CUT` / `PASTE` | Cut selected text / paste it |

### Display

| Command | Action |
|---|---|
| `HEX [ON\|OFF]` | Two hex rows (high and low nibble) under every line, updated on each Enter; `HEX` alone = ON. Not saved |
| `COMPARE *` | Show the changes since the file was opened or last saved, inline |
| `COMPARE file` | Compare the buffer with another text file |
| `RESET` / `RES [EXCLUDED] [COMMAND] [FIND] [LABEL] [ALL]` | Show excluded lines, clear pending line commands, hex/COLS/COMPARE rows and the find highlight. `LABEL` / `ALL` also remove labels |
| `HELP` | Show the built-in help |

**Aliases:** CAN = CANCEL; C/CHA/CHG = CHANGE; CRE = CREATE; DEL = DELETE; EX/EXC/X = EXCLUDE;
F = FIND; L/LOC = LOCATE; REP = REPLACE; RES = RESET; RF = RFIND; RCH = RCHANGE;
RETR = RETRIEVE; EXIT = END. Other commands use their full names.

## Line commands

Click a line number (or Tab to it), type the command over it and press Enter, in the number area
or the text area. Several commands can be entered before pressing Enter. `n` is an optional count,
before or after the command (`D3` or `3D`).

| Command | Block form | Action |
|---|---|---|
| `I[n]` | | Insert n temporary lines after this line; untouched ones vanish on the next Enter, Enter on the last typed one adds another |
| `D[n]` | `DD..DD` | Delete |
| `R[n]` | `RR..RR` | Repeat n times |
| `C[n]` | `CC..CC` | Copy (to an A/B/O destination) |
| `M[n]` | `MM..MM` | Move (to an A/B/O destination) |
| `A[n]` / `B[n]` | | Paste the copied/moved lines after / before this line (n times) |
| `O[n]` | `OO..OO` | Overlay the copied/moved lines on this line or block (only blanks are filled) |
| `UC[n]` / `LC[n]` | `UCC` / `LCC` | Upper / lower case |
| `)[n]` / `([n]` | `))` / `((` | Shift right / left n columns (default 2) |
| `>[n]` / `<[n]` | `>>` / `<<` | Data shift right / left (default 2); a word in column 1 stays put |
| `HX[n]` | | Show two hex rows under n lines (removed by RESET) |
| `COLS` | | Show a column ruler row after the line (removed by D or RESET) |
| `MD[n]` | `MDD..MDD` | Make data: COLS, hex and COMPARE rows become ordinary lines of the file |
| `TS[n]` | | Split the line at the text cursor, inserting n blank lines (default 1) |
| `TF[n]` | | Flow this paragraph to column n (default 72) |
| `TE[n]` | | Open a text-entry area; type, then press Enter to flow it |
| `X[n]` | `XX..XX` | Exclude (hide) lines |
| `.label` | | Set a label (`.` + 1-5 letters, not starting with Z), shown in place of the number; type spaces over it to remove it |

- On an excluded block (`- - -`): `F[n]` / `L[n]` show the first / last n lines, `S[n]` shows n
  lines, and `D`, `C`, `M`, `R`, `X`, `UC`, `LC` act on the whole block.
- C or M without a destination keeps the lines for a later A, B or O.
- A D/C/M/UC/LC/MD count must not run past the last line.
- TS, TF and TE must be entered by themselves.
- In primary commands, `.n` means line n (e.g. `DELETE .3 .5`).

## Keys

| Key | Action |
|---|---|
| Enter | Run pending commands; with nothing to run, move to the next line command field (it never splits a line - use TS) |
| Right Ctrl, keypad Enter, Shift/Ctrl/Alt+Enter | 3270 Enter: always processes, the cursor stays put |
| Home | Jump to the command line |
| Tab / Shift+Tab | Move between the line command area and the text |
| PgUp/F7, PgDn/F8 | Scroll up / down 20 lines; an amount on the command line overrides it (`M` + F7 = UP MAX; also n, P, H, C) |
| F1 | Help |
| F3 | END |
| F5 / F6 | Repeat FIND / repeat CHANGE |
| F10 / F11 | Scroll left / right one page |
| F12 | Retrieve the previous command (set `ISPFEditor.PF12_ACTION = "CANCEL"` for Cancel) |
| Ctrl+S / Ctrl+F | Save / Find |
| Ctrl+Tab / Ctrl+Shift+Tab | Next / previous tab |

## Modes

| Mode | Opened with | |
|---|---|---|
| EDIT | `EDIT`, *File > Open (Edit)* | Full editing |
| VIEW | `VIEW`, *File > Open (View)* | Read-only |
| BROWSE | `BROWSE`, *File > Open (Browse)* | Read-only |

## Which features are still missing

Compared with the IBM ISPF editor (z/OS), roughly in order of how much an ISPF user would miss
them.

**Accepted, but only show a message**
- `MODEL` (templates), `HILITE` (syntax colouring), `RECOVERY` (on/off and crash recovery).
- `INDEX` just shows the help; the primary commands `TS` / `TF` (the line commands work).
- The `BOUNDS` line command; there are no bounds at all.

**Line commands**
- `BNDS`, `MASK` (and `I` filling new lines from the mask), `TABS`.
- `=NOTE=`, `==MSG>` and `==ERR>` lines: nothing creates them (`MD` works on COLS, hex and COMPARE
  rows).

**FIND / CHANGE / EXCLUDE**
- Regular expressions (`R'...'`).
- `T'...'` and plain quoted strings are case-sensitive here; in ISPF they ignore case.
- EXCLUDE has no `NEXT`/`PREV`/`FIRST`/`LAST`, columns or `WORD`/`PREFIX`/`SUFFIX`.
- No `FLIP` and no `HIDE X`.

**Hex**
- `HEX DATA` (side-by-side format).
- Typing over the hex digits does not change the data; the rows are rebuilt on Enter.
- Hex is shown for the file's UTF-8 bytes, not EBCDIC.

**Profile and environment**
- No `PROFILE` command and no per-file-type profiles.
- `CAPS`, `NULLS`, `NUMBER` / `RENUM` / `UNNUM` / `AUTONUM` (sequence numbers in columns 73-80),
  `AUTOSAVE`, `STATS`, `PACK`, `IMACRO`, `XTABS`.

**Files and data sets**
- No PDS / member list, member statistics, `SAVE` under another member name, or `SUBMIT`.
- No record format or fixed record length (RECFM F/V, LRECL); files are plain text, opened
  with the system's default encoding, with no EBCDIC code pages.
- `COPY` / `MOVE` / `CREATE` / `REPLACE` work on files, not members.

**Edit macros** (the largest gap)
- No macro language: no `ISREDIT`, REXX or CLIST macros, no initial macro.
- No `DEFINE` / `ALIAS`, `BUILTIN` or `ENVIRON`.

**Screens and keys**
- Tabs replace split screens: no `SPLIT`, no `SWAP LIST`, no PF2 / PF9.
- No `KEYS` / `PFSHOW`: the PF keys are fixed (F1, F3, F5-F8, F10-F12).
- `CUT` / `PASTE` work on the selected text, not ISPF's line clipboards (`CUT .a .b`, named
  clipboards, `PASTE AFTER|BEFORE`).

**Other**
- `UNDO` works within the session; there are no SETUNDO storage options.

## Tests

```
python -m unittest discover -s tests
```

- `tests/test_isfped.py` - editor behaviour: line/primary commands, pending blocks, inserted
  lines, labels, excluded lines, FIND/CHANGE, picture strings, UNDO, HX/HEX, COLS, MD, COMPARE,
  file commands, scrolling, the file path, tabs.
- `tests/test_vs_spflite.py` - the scenarios in `tests/cases.py` must save the same file as
  SPFLite3. SPFLite's results are recorded in `tests/spflite_results.json`, so SPFLite is not
  needed to run the tests. Deliberate differences run as expected failures.
- `python tests/compare_spflite.py` re-runs the scenarios in SPFLite3 (Windows; default
  `C:\apps\SPFLite\SPFLite3.exe`, override with `SPFLITE_EXE`) and refreshes the recorded results.
