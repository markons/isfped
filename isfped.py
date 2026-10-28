#!/usr/bin/env python3
"""
ISPF Editor - Python/Tkinter Implementation
Line commands are entered DIRECTLY on the line number gutter.
"""

import re
import json
import os
import textwrap
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from difflib import SequenceMatcher
from collections import defaultdict
from tkinter import filedialog, messagebox, simpledialog

# Line command syntax: optional count before or after the command (D3, 3D, ))4)
LINE_CMD_RE = re.compile(
    r"^(\d*)(UCC|LCC|UC|LC|DD|CC|MM|RR|XX|OO|<<|>>|HX|TS|TF|TE|\(\(|\)\)|[IDRCMABOXFLS<>()])(\d*)$")
# Block commands and the single-line command they act like
BLOCK_CMDS = {"DD": "D", "CC": "C", "MM": "M", "RR": "R", "XX": "X",
              "UCC": "UC", "LCC": "LC", "((": "(", "))": ")",
              "<<": "<", ">>": ">", "OO": "O"}
# Line label: period followed by 1-5 letters, so it fits the 6-column number area
# (labels starting with Z are reserved)
LABEL_RE = re.compile(r"^\.[A-Z]{1,5}$")
FIELD_WIDTH = 6
EXCLUDED_FIELD = "- - - "
LABEL_MARK = "lbl."     # Tk mark per label: lbl.NAME
EXCLUDE_MARK = "xcl."   # Tk mark per excluded line: xcl.<n>


class ISPFEditor:
    PF12_ACTION = "RETRIEVE"  # Change to "CANCEL" for the alternate ISPF setup.

    def __init__(self, root):
        self.root = root
        self.root.title("ISPF Editor - Python/Tk")
        self.root.geometry("900x600")

        # Editor state
        self.filename = None
        self._dirty = False
        self._last_find = None
        self._last_change = None
        self._baseline_lines = [""]
        self._recent_files_path = Path(__file__).with_name(".pyspf_recent_files.json")
        self._recent_files = self._load_recent_files()
        self.compare_filename = None
        self.compare_selected_menu_index = None
        self._error_lines = set()
        self.scroll_mode = "CSR"
        self._command_history = []
        self._history_index = 0
        self.mode = "EDIT"          # EDIT, BROWSE, VIEW
        self.clipboard_line = None  # For CUT/PASTE primary commands
        self.line_clipboard = []    # Lines from C/M line commands, for A/B
        self.hex_mode = False
        self._text_entry = None   # (first line, number of blank entry lines)
        self._processing = False    # Guard against re-entrant calls
        self._gutter_fields = []    # What each gutter line shows (number/label/excluded)
        self._markers = []          # (Label widget, last line) for excluded blocks
        self._snapshots = {}        # hash(content) -> (labels, excluded), for undo/redo
        self._mark_seq = 0

        self._build_ui()
        self._bind_keys()
        self.refresh_gutter()
        self.root.after_idle(self._update_ispf_header)
        # Like ISPF, start on the command line; also when the window itself gets focus
        self.cmd_entry.focus_set()
        self.root.bind("<FocusIn>", self._on_root_focus)

    def _on_root_focus(self, event):
        if event.widget is self.root:
            self.cmd_entry.focus_set()

    def _set_scroll_mode(self, event=None):
        value = self.scroll_entry.get().strip().upper()
        aliases = {"P": "PAGE", "H": "HALF", "C": "CSR", "M": "MAX"}
        value = aliases.get(value, value)
        if value not in ("PAGE", "HALF", "CSR", "MAX") and not value.isdigit():
            self.scroll_entry.delete(0, tk.END)
            self.scroll_entry.insert(0, self.scroll_mode)
            self.status.config(text="Scroll: enter PAGE, HALF, CSR, MAX, or a number")
            return "break"
        self.scroll_mode = value
        self.scroll_entry.delete(0, tk.END)
        self.scroll_entry.insert(0, value)
        self.status.config(text=f"Scroll set to {value}")
        return "break"

    def _update_ispf_header(self, event=None):
        """Refresh the ISPF-style column ruler and Top of Data divider."""
        if not hasattr(self, "text") or not self.text.winfo_exists():
            return
        columns = self._visible_columns()
        first = self._left_column()
        ruler = []
        for column in range(first, first + columns):
            if column % 10 == 0:
                ruler.append(str((column // 10) % 10))
            elif column % 5 == 0:
                ruler.append("+")
            else:
                ruler.append("-")
        self.ruler_data.config(text="".join(ruler))

        width = FIELD_WIDTH + columns
        caption = " Top of Data "
        remaining = max(width - len(caption), 0)
        left = remaining // 2
        right = remaining - left
        divider = "*" * left + caption + "*" * right
        self.boundary_gutter.config(text=divider[:FIELD_WIDTH])
        self.boundary_data.config(text=divider[FIELD_WIDTH:])

    def _on_text_xscroll(self, first, last):
        self.xscroll.set(first, last)
        self._update_ispf_header()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        """Build the complete editor interface."""
        # Command line (top)
        self.cmd_frame = tk.Frame(self.root)
        self.cmd_frame.pack(fill=tk.X, padx=2, pady=2)
        tk.Label(self.cmd_frame, text="Command >", font=("Courier", 10)).pack(side=tk.LEFT)
        self.cmd_entry = tk.Entry(self.cmd_frame, font=("Courier", 10))
        self.cmd_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cmd_entry.bind("<Return>", self.process_primary_command)
        tk.Label(self.cmd_frame, text="Scroll >", font=("Courier", 10)).pack(side=tk.LEFT, padx=(8, 2))
        self.scroll_entry = tk.Entry(self.cmd_frame, width=5, font=("Courier", 10),
                                     justify=tk.CENTER)
        self.scroll_entry.insert(0, self.scroll_mode)
        self.scroll_entry.pack(side=tk.RIGHT)
        self.scroll_entry.bind("<Return>", self._set_scroll_mode)

        # ISPF-style fixed header rows, aligned with the gutter and data area.
        self.ruler_frame = tk.Frame(self.root, bg="white")
        self.ruler_frame.pack(fill=tk.X, padx=2)
        self.ruler_gutter = tk.Label(self.ruler_frame, text="=<COLS>", width=FIELD_WIDTH,
                                     font=("Courier", 10), bg="white", anchor=tk.W,
                                     padx=3, bd=0)
        self.ruler_gutter.pack(side=tk.LEFT)
        self.ruler_data = tk.Label(self.ruler_frame, text="", font=("Courier", 10),
                                   bg="white", anchor=tk.W, padx=0, bd=0)
        self.ruler_data.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.boundary_frame = tk.Frame(self.root, bg="white")
        self.boundary_frame.pack(fill=tk.X, padx=2)
        self.boundary_gutter = tk.Label(self.boundary_frame, text="******", width=FIELD_WIDTH,
                                        font=("Courier", 10), bg="white", anchor=tk.W,
                                        padx=3, bd=0)
        self.boundary_gutter.pack(side=tk.LEFT)
        self.boundary_data = tk.Label(self.boundary_frame, text="", font=("Courier", 10),
                                      bg="white", anchor=tk.W, padx=0, bd=0)
        self.boundary_data.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Main area
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Line number gutter - EDITABLE for direct command entry
        self.line_numbers = tk.Text(self.main_frame, width=FIELD_WIDTH,
                                    bg="lightgray", fg="black", font=("Courier", 10),
                                    padx=3, wrap=tk.NONE,
                                    insertbackground="black", selectbackground="lightblue",
                                    height=1)  # Height will be managed by pack
        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        self.line_numbers.tag_configure("xhide", elide=True)
        # Characters the user typed in the gutter - these ARE the line command
        self.line_numbers.tag_configure("typed", foreground="red")

        # Enter processes the line commands; typing overwrites like ISPF
        self.line_numbers.bind("<Return>", self.process_line_command)
        self.line_numbers.bind("<KP_Enter>", self.process_line_command)
        self.line_numbers.bind("<Key>", self._gutter_overtype)
        self.line_numbers.bind("<BackSpace>", self._gutter_backspace)
        self.line_numbers.bind("<Delete>", self._gutter_delete)

        # Text area
        self.text = tk.Text(self.main_frame, wrap=tk.NONE, undo=True,
                            font=("Courier", 10), bg="white", fg="black")
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.text.tag_configure("xhide", elide=True)
        self.text.tag_configure("found", background="yellow", foreground="black")
        self.text.tag_configure("hexprefix", elide=True)
        self.text.tag_configure("hexinfo", foreground="blue")
        self.text.tag_configure("compare_added", foreground="dark green")
        self.text.tag_configure("compare_removed", foreground="dark red")

        # Scrollbars - gutter and text scroll together
        self.yscroll = tk.Scrollbar(self.main_frame, command=self.text.yview)
        self.yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.config(yscrollcommand=self._on_text_yscroll)
        self.line_numbers.config(yscrollcommand=self._on_gutter_yscroll)

        self.xscroll = tk.Scrollbar(self.root, command=self.text.xview, orient=tk.HORIZONTAL)
        self.xscroll.pack(fill=tk.X)
        self.text.config(xscrollcommand=self._on_text_xscroll)

        # Status line
        self.status = tk.Label(self.root, text="", anchor=tk.W, relief=tk.SUNKEN,
                               font=("Courier", 9))
        self.status.pack(fill=tk.X)

        # Menu bar
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Open (Edit)", command=lambda: self.open_file("EDIT"))
        file_menu.add_command(label="Open (Browse)", command=lambda: self.open_file("BROWSE"))
        file_menu.add_command(label="Open (View)", command=lambda: self.open_file("VIEW"))
        file_menu.add_separator()
        self.recent_files_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self.recent_files_menu)
        self._refresh_recent_files_menu()
        file_menu.add_command(label="Select File to Compare...", command=self.select_compare_file)
        file_menu.add_command(label="Compare with Selected File", command=self.compare_selected_file,
                              state=tk.DISABLED)
        self.compare_selected_menu_index = file_menu.index(tk.END)
        file_menu.add_separator()
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_command(label="Save As...", command=self.save_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        self.file_menu = file_menu

        edit_menu = tk.Menu(menubar, tearoff=0)
        edit_menu.add_command(label="Find (FIND)", command=lambda: self.find_text())
        edit_menu.add_command(label="Change (CHANGE)", command=lambda: self.change_text())
        edit_menu.add_separator()
        edit_menu.add_command(label="Upper Case (UC)", command=lambda: self.change_case("upper"))
        edit_menu.add_command(label="Lower Case (LC)", command=lambda: self.change_case("lower"))
        edit_menu.add_separator()
        edit_menu.add_command(label="Undo", command=self.undo)
        edit_menu.add_command(label="Redo", command=self.redo)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Help", command=self.show_help)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

    def _bind_keys(self):
        """Bind keyboard events."""
        self.text.bind("<KeyRelease>", self.update_status)
        # Keep gutter line count in sync with the text (pending commands are preserved)
        self.text.bind("<<Modified>>", self._on_text_modified)
        self.text.bind("<Configure>", self._on_text_configure)
        # Enter in the text area runs pending line commands (otherwise a newline)
        self.text.bind("<Return>", self._text_return)
        self.text.bind("<KP_Enter>", self._text_return)
        # Ctrl+Z / Ctrl+Y: restore labels and excluded lines after the text is undone
        # (runs before Tk's own undo, so the page shown now can be kept)
        self.text.bind("<<Undo>>", self._on_undo_redo)
        self.text.bind("<<Redo>>", self._on_undo_redo)
        self.text.bind("<Button-1>", self.update_status)
        self.text.bind("<ButtonRelease-1>", self.update_status)
        # ISPF-style navigation: Home -> command line, Tab moves between
        # line command area and text area
        for widget in (self.root, self.text, self.line_numbers, self.cmd_entry):
            widget.bind("<Home>", self._home_to_command)
            # PgUp/F7 and PgDn/F8 scroll 20 lines (replaces Tk's own paging)
            for key in ("<Prior>", "<F7>"):
                widget.bind(key, lambda e: self._scroll_key("UP"))
            for key in ("<Next>", "<F8>"):
                widget.bind(key, lambda e: self._scroll_key("DOWN"))
            widget.bind("<F1>", lambda e: self._invoke_pf(self.show_help))
            widget.bind("<F3>", lambda e: self._invoke_pf(self.end_editor))
            widget.bind("<F5>", lambda e: self._invoke_pf(self.repeat_find))
            widget.bind("<F6>", lambda e: self._invoke_pf(self.repeat_change))
            widget.bind("<F10>", lambda e: self._invoke_pf(lambda: self.scroll_horizontal("LEFT", "PAGE")))
            widget.bind("<F11>", lambda e: self._invoke_pf(lambda: self.scroll_horizontal("RIGHT", "PAGE")))
            widget.bind("<F12>", lambda e: self._invoke_pf(self._pf12))
        self.text.bind("<Tab>", self._tab_from_text)
        self.text.bind("<Shift-Tab>", self._backtab_from_text)
        self.line_numbers.bind("<Tab>", self._tab_from_gutter)
        self.line_numbers.bind("<Shift-Tab>", self._backtab_from_gutter)
        self.cmd_entry.bind("<Tab>", self._tab_from_command)
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-f>", lambda e: self.find_text())

    @staticmethod
    def _invoke_pf(action):
        action()
        return "break"

    def _pf12(self):
        if self.PF12_ACTION.upper() == "CANCEL":
            self.cancel_editor()
        else:
            self.retrieve_command()

    def retrieve_command(self):
        if not self._command_history:
            self.status.config(text="No command to retrieve")
            return
        self._history_index = (self._history_index - 1) % len(self._command_history)
        command = self._command_history[self._history_index]
        self.cmd_entry.delete(0, tk.END)
        self.cmd_entry.insert(0, command)
        self.cmd_entry.icursor(tk.END)
        self.cmd_entry.focus_set()

    def cancel_editor(self):
        if not self._dirty or messagebox.askyesno("Cancel", "Discard changes and exit?"):
            self.root.destroy()

    @staticmethod
    def _close_command_window():
        """Close a parent cmd.exe window on END; detach otherwise."""
        if os.name == "nt":
            try:
                import ctypes
                from ctypes import wintypes

                class PROCESSENTRY32W(ctypes.Structure):
                    _fields_ = [
                        ("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD),
                        ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD),
                        ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD),
                        ("pcPriClassBase", wintypes.LONG),
                        ("dwFlags", wintypes.DWORD),
                        ("szExeFile", wintypes.WCHAR * 260),
                    ]

                kernel = ctypes.windll.kernel32
                kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
                kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
                kernel.Process32FirstW.argtypes = [wintypes.HANDLE,
                                                   ctypes.POINTER(PROCESSENTRY32W)]
                kernel.Process32FirstW.restype = wintypes.BOOL
                kernel.Process32NextW.argtypes = [wintypes.HANDLE,
                                                  ctypes.POINTER(PROCESSENTRY32W)]
                kernel.Process32NextW.restype = wintypes.BOOL
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle.restype = wintypes.BOOL
                kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel.OpenProcess.restype = wintypes.HANDLE
                kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
                kernel.TerminateProcess.restype = wintypes.BOOL
                snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)
                parent_name = ""
                if snapshot != ctypes.c_void_p(-1).value:
                    entry = PROCESSENTRY32W()
                    entry.dwSize = ctypes.sizeof(entry)
                    if kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
                        while True:
                            if entry.th32ProcessID == os.getppid():
                                parent_name = entry.szExeFile.lower()
                                break
                            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                                break
                    kernel.CloseHandle(snapshot)

                if parent_name == "cmd.exe":
                    process = kernel.OpenProcess(0x0001, False, os.getppid())
                    if process:
                        kernel.TerminateProcess(process, 0)
                        kernel.CloseHandle(process)
                else:
                    kernel.FreeConsole()
            except (AttributeError, OSError):
                pass

    def end_editor(self):
        """ISPF END: finish editing, offering to save pending changes."""
        if self._get_pending_commands():
            self.process_line_command()
            if self._get_pending_commands():
                self.status.config(text="Resolve pending line commands before END")
                return
            self._dirty = True
        if self.mode == "EDIT" and self._dirty:
            answer = messagebox.askyesnocancel("End", "Save changes before exiting?")
            if answer is None:
                return
            if answer and not self.save_file():
                return
        self._close_command_window()
        self.root.destroy()

    # ------------------------------------------------------------------
    # Line state: labels and excluded lines
    # Both are stored as Tk marks so they move with their line while typing.
    # ------------------------------------------------------------------
    def _mark_line(self, mark):
        return int(self.text.index(mark).split(".")[0])

    def get_labels(self):
        """{LABEL: line_number}"""
        return {m[len(LABEL_MARK):]: self._mark_line(m)
                for m in self.text.mark_names() if m.startswith(LABEL_MARK)}

    @property
    def line_labels(self):
        return self.get_labels()

    def set_labels(self, labels):
        for m in self.text.mark_names():
            if m.startswith(LABEL_MARK):
                self.text.mark_unset(m)
        for name, line in labels.items():
            self.text.mark_set(LABEL_MARK + name, f"{line}.0")

    def get_excluded(self):
        """Set of excluded (hidden) line numbers."""
        widget = self.text._w
        script = (
            f"set result [list]; foreach mark [{widget} mark names] "
            f"{{if {{[string match {{{EXCLUDE_MARK}*}} $mark]}} "
            f"{{lappend result [lindex [split [{widget} index $mark] .] 0]}}}}; "
            "set result"
        )
        return {int(line) for line in self.text.tk.splitlist(self.text.tk.call("eval", script))}

    def set_excluded(self, lines):
        """Update exclusion marks by delta, issuing batched Tcl operations."""
        desired = {int(line) for line in lines}
        widget = self.text._w
        script = (
            f"set result [list]; foreach mark [{widget} mark names] "
            f"{{if {{[string match {{{EXCLUDE_MARK}*}} $mark]}} "
            f"{{lappend result [list $mark [lindex [split [{widget} index $mark] .] 0]]}}}}; "
            "set result"
        )
        current = {}
        duplicate_marks = []
        for pair in self.text.tk.splitlist(self.text.tk.call("eval", script)):
            mark, line = self.text.tk.splitlist(pair)
            line = int(line)
            if line in current:
                duplicate_marks.append(mark)
            else:
                current[line] = mark

        remove = duplicate_marks + [mark for line, mark in current.items() if line not in desired]
        if remove:
            mark_list = tk._join(remove)
            self.text.tk.call(
                "eval", f"foreach mark {{{mark_list}}} {{{widget} mark unset $mark}}"
            )

        add = sorted(desired - current.keys())
        if add:
            flat = []
            for line in add:
                self._mark_seq += 1
                flat.extend((f"{EXCLUDE_MARK}{self._mark_seq}", f"{line}.0"))
            pairs = tk._join(flat)
            self.text.tk.call(
                "eval", f"foreach {{mark index}} {{{pairs}}} {{{widget} mark set $mark $index}}"
            )

    def _get_line_state(self):
        return self.get_labels(), self.get_excluded()

    def _set_line_state(self, state):
        labels, excluded = state
        self.set_labels(labels)
        self.set_excluded(excluded)

    def _snapshot(self):
        """Remember labels/excluded lines for the current content (for undo/redo)."""
        self._snapshots[hash(self.text.get("1.0", "end-1c"))] = self._get_line_state()
        while len(self._snapshots) > 500:
            self._snapshots.pop(next(iter(self._snapshots)))

    def _on_undo_redo(self, event=None):
        view = self._get_view()
        self.root.after_idle(lambda: self._restore_line_state(view))

    def _restore_line_state(self, view=None):
        state = self._snapshots.get(hash(self.text.get("1.0", "end-1c")))
        if state:
            self._set_line_state(state)
        self.refresh_gutter()
        if view:
            self._set_view(view)

    def _commit_text(self, content, state):
        """Replace the buffer and set labels/excluded lines, as one undo step."""
        self._snapshot()
        self._replace_text(content)
        self._set_line_state(state)
        self._snapshot()

    def _resolve_target(self, target):
        """Line number for a LOCATE/FIND target: a number or a .label."""
        n = self._text_line_count()
        if target.isdigit():
            return max(1, min(int(target), n))
        name = target.upper().lstrip(".")
        if not target.startswith(".") or not name:
            return None
        if name in ("ZF", "ZFIRST"):
            return 1
        if name in ("ZL", "ZLAST"):
            return n
        if name == "ZCSR":
            return self._current_line(self.text)
        return self.get_labels().get(name)

    @staticmethod
    def _runs(lines):
        """Group line numbers into consecutive (first, last) runs."""
        runs = []
        for line in sorted(lines):
            if runs and line == runs[-1][1] + 1:
                runs[-1][1] = line
            else:
                runs.append([line, line])
        return [tuple(r) for r in runs]

    # ------------------------------------------------------------------
    # Keyboard Navigation
    # ------------------------------------------------------------------
    SCROLL_KEY_LINES = "20"
    SCROLL_AMOUNTS = ("M", "MAX", "P", "PAGE", "H", "HALF", "C", "CSR")

    def _scroll_key(self, direction):
        """PgUp/F7, PgDn/F8: scroll using command-line or Scroll field value.

        An amount on the command line overrides the Scroll field: M + F7 = UP MAX.
        """
        amount = self.cmd_entry.get().strip().upper()
        if amount.isdigit() or amount in self.SCROLL_AMOUNTS:
            self.cmd_entry.delete(0, tk.END)
        else:
            amount = self.scroll_mode
        self.scroll_vertical(direction, amount)
        return "break"

    def _home_to_command(self, event=None):
        """Home jumps to the start of the command line (like ISPF)."""
        self.cmd_entry.focus_set()
        self.cmd_entry.icursor(0)
        return "break"

    def _visible_rows(self):
        """Line numbers that have a visible row (excluded blocks show their first line)."""
        excluded = self.get_excluded()
        return [i for i in range(1, self._text_line_count() + 1)
                if i not in excluded or i - 1 not in excluded]

    def _row_of(self, line):
        """The visible row a line belongs to (first line of its excluded block)."""
        excluded = self.get_excluded()
        while line in excluded and line - 1 in excluded:
            line -= 1
        return line

    def _focus_gutter(self, line):
        line = self._row_of(max(1, min(line, self._text_line_count())))
        self.line_numbers.focus_set()
        self.line_numbers.mark_set(tk.INSERT, f"{line}.0")
        self.line_numbers.see(tk.INSERT)

    def _focus_text(self, line):
        line = max(1, min(line, self._text_line_count()))
        self.text.focus_set()
        self.text.mark_set(tk.INSERT, f"{line}.0")
        self.text.see(tk.INSERT)
        self.update_status()

    def _focus_row(self, line):
        """Text of the line, or its gutter if the line is excluded (no text shown)."""
        if line in self.get_excluded():
            self._focus_gutter(line)
        else:
            self._focus_text(line)

    def _current_line(self, widget):
        return int(widget.index(tk.INSERT).split(".")[0])

    def _next_row(self, line, step):
        rows = self._visible_rows()
        candidates = [r for r in rows if (r > line if step > 0 else r < line)]
        if not candidates:
            return line
        return candidates[0] if step > 0 else candidates[-1]

    def _tab_from_gutter(self, event=None):
        """Tab: line command area -> text of the same line."""
        line = self._row_of(self._current_line(self.line_numbers))
        if line in self.get_excluded():
            self._focus_gutter(self._next_row(line, 1))
        else:
            self._focus_text(line)
        return "break"

    def _backtab_from_gutter(self, event=None):
        """Shift+Tab: line command area -> text of the previous line."""
        line = self._row_of(self._current_line(self.line_numbers))
        self._focus_row(self._next_row(line, -1))
        return "break"

    def _tab_from_text(self, event=None):
        """Tab: text -> line command area of the next line."""
        line = self._row_of(self._current_line(self.text))
        self._focus_gutter(self._next_row(line, 1))
        return "break"

    def _backtab_from_text(self, event=None):
        """Shift+Tab: text -> line command area of the same line."""
        self._focus_gutter(self._current_line(self.text))
        return "break"

    def _first_row_on_page(self):
        """First fully visible row at the top of the text area."""
        line = self._row_of(int(self.text.index("@0,0").split(".")[0]))
        info = self.line_numbers.dlineinfo(f"{line}.0")
        if info and info[1] < 0:  # top row only half visible
            line = self._next_row(line, 1)
        return line

    def _tab_from_command(self, event=None):
        """Tab: command line -> line command area of the first visible line."""
        self._focus_gutter(self._first_row_on_page())
        return "break"

    # ------------------------------------------------------------------
    # Line Number Gutter - Direct Command Entry
    # ------------------------------------------------------------------
    def _text_line_count(self):
        return int(self.text.index("end-1c").split(".")[0])

    def _is_compare_line(self, line_number):
        """Whether a red compare row is editor-only baseline display data."""
        try:
            return "compare_removed" in self.text.tag_names(f"{line_number}.0")
        except tk.TclError:
            return False

    def _is_compare_row(self, line_number):
        """Whether a row is visually marked by COMPARE, including real additions."""
        try:
            tags = self.text.tag_names(f"{line_number}.0")
            return "compare_added" in tags or "compare_removed" in tags
        except tk.TclError:
            return False

    def refresh_gutter(self, event=None, keep=None):
        """Redraw the gutter (numbers, labels, excluded blocks) and hide excluded lines.

        keep: optional {line_number: command} to leave displayed (pending commands).
        """
        keep = keep or {}
        line_count = self._text_line_count()
        excluded = {line for line in self.get_excluded() if line <= line_count}
        runs = self._runs(excluded)
        run_starts = {s for s, _ in runs}
        label_at = {}
        for name, line in sorted(self.get_labels().items()):
            label_at.setdefault(line, name)

        fields = []
        content_lines = self.text.get("1.0", "end-1c").split("\n")
        self.text.tag_remove("hexprefix", "1.0", tk.END)
        self.text.tag_remove("hexinfo", "1.0", tk.END)
        for i in range(1, line_count + 1):
            if content_lines[i - 1].startswith("=HEX> "):
                # The marker is hidden so the hexadecimal digits begin at the
                # same screen column as the source line above them.
                self.text.tag_add("hexprefix", f"{i}.0", f"{i}.6")
                self.text.tag_add("hexinfo", f"{i}.0", f"{i}.end")
                fields.append(" " * FIELD_WIDTH)
            elif "compare_removed" in self.text.tag_names(f"{i}.0"):
                fields.append(" " * FIELD_WIDTH)
            elif i in run_starts:
                fields.append(EXCLUDED_FIELD)
            elif i in label_at:
                fields.append(f".{label_at[i]}".ljust(FIELD_WIDTH))
            else:
                fields.append(f"{i:06d}")
        self._gutter_fields = fields

        g = self.line_numbers
        g.config(state=tk.NORMAL)
        cursor_line = self._current_line(g)
        g.delete("1.0", tk.END)
        g.insert("1.0", "\n".join(fields))
        # Keep the cursor on its line (re-inserting leaves it at the end of the file)
        g.mark_set(tk.INSERT, f"{min(cursor_line, line_count)}.0")
        # Pending commands are shown (and re-read) as typed characters
        for i, cmd in keep.items():
            if i <= line_count:
                g.delete(f"{i}.0", f"{i}.end")
                g.insert(f"{i}.0", cmd.upper(), "typed", " " * max(0, FIELD_WIDTH - len(cmd)), ())
        self._apply_tail_space()

        # Excluded block: text shows one empty row (covered by a marker), the gutter
        # shows the block's first field; both hide the rest so rows stay aligned
        self.text.tag_remove("xhide", "1.0", tk.END)
        for s, e in runs:
            self.text.tag_add("xhide", f"{s}.0", f"{e}.end")
            if e > s:
                g.tag_add("xhide", f"{s}.end", f"{e}.end")
        if self._current_line(self.text) in excluded:
            visible = [r for r in range(1, line_count + 1) if r not in excluded]
            if visible:
                self.text.mark_set(tk.INSERT, f"{visible[0]}.0")
        self._build_markers(runs)
        self.text.update_idletasks()
        self._sync_scroll(self.text, g)

    def _build_markers(self, runs):
        """One '- - - n Line(s) not Displayed' bar per excluded block."""
        for label, _ in self._markers:
            label.destroy()
        self._markers = []
        for s, e in runs:
            label = tk.Label(self.text, text=f"{'- ' * 12} {e - s + 1} Line(s) not Displayed",
                             font=("Courier", 10), bg="white", fg="gray35", anchor=tk.W,
                             bd=0, padx=0, pady=0, highlightthickness=0)
            label.bind("<Button-1>", lambda ev, s=s: self._focus_gutter(s))
            self._markers.append((label, e))
        self.root.after_idle(self._place_markers)

    def _place_markers(self):
        inset = int(self.text.cget("borderwidth")) + int(self.text.cget("highlightthickness"))
        for label, last in self._markers:
            try:
                info = self.text.dlineinfo(f"{last}.end")
            except tk.TclError:
                info = None
            if info:
                label.place(x=inset, y=info[1], relwidth=1, width=-2 * inset, height=info[3])
            else:
                label.place_forget()

    def _apply_tail_space(self):
        """Blank space below the last line, so LOCATE can put any line at the top."""
        line_height = self.text.dlineinfo("@0,0")
        line_height = line_height[3] if line_height else 16
        space = max(self.text.winfo_height() - line_height - 4, 0)
        for widget in (self.text, self.line_numbers):
            widget.tag_configure("tail", spacing3=space)
            widget.tag_remove("tail", "1.0", tk.END)
            widget.tag_add("tail", "end-1c linestart", tk.END)

    def _on_text_configure(self, event=None):
        self._apply_tail_space()
        self._place_markers()
        self._update_ispf_header()

    def _text_return(self, event=None):
        """Enter in the text area: run pending line commands like ISPF, else a newline."""
        if self._text_entry:
            self._finish_text_entry()
            return "break"
        if self._get_pending_commands():
            return self.process_line_command()
        return None

    def _text_entry_default_count(self, line):
        """Approximate ISPF TE's default space-to-bottom on the visible page."""
        info = self.text.dlineinfo(f"{line}.0")
        line_height = info[3] if info else 16
        y = info[1] if info else 0
        return max(1, (self.text.winfo_height() - max(y, 0)) // max(line_height, 1))

    def _finish_text_entry(self):
        """Flow the TE entry area into paragraph lines and leave text-entry mode."""
        if not self._text_entry:
            return
        start, count = self._text_entry
        lines = self.text.get("1.0", "end-1c").split("\n")
        first = start - 1
        entry = lines[first:first + count]
        if not entry:
            self._text_entry = None
            return
        typed = " ".join(part.strip() for part in entry if part.strip())
        if typed:
            prefix = lines[first - 1] if first else ""
            indent = len(prefix) - len(prefix.lstrip())
            flowed = textwrap.wrap(typed, width=max(72, indent + 1),
                                   initial_indent=" " * indent,
                                   subsequent_indent=" " * indent,
                                   break_long_words=False,
                                   break_on_hyphens=False) or [" " * indent]
        else:
            flowed = entry
        new_lines = lines[:first] + flowed + lines[first + count:]
        delta = len(flowed) - count
        labels, excluded = self._get_line_state()

        def remap_line(line):
            index = line - 1
            if index < first:
                return line
            if index >= first + count:
                return index + delta + 1
            return first + 1

        new_labels = {name: remap_line(line) for name, line in labels.items()}
        new_excluded = {remap_line(line) for line in excluded}
        self._text_entry = None
        self._commit_text("\n".join(new_lines), (new_labels, new_excluded))
        self.refresh_gutter()
        self._focus_text(min(first + 1, self._text_line_count()))
        self.status.config(text="Text entry finished and flowed")

    def _on_text_modified(self, event=None):
        """Text changed: rebuild the gutter if the number of lines changed."""
        if not self.text.edit_modified():
            return
        if not self._processing:
            self._dirty = True
        self.text.edit_modified(False)
        if self._processing:
            return
        gutter_lines = int(self.line_numbers.index("end-1c").split(".")[0])
        if gutter_lines != self._text_line_count():
            self.refresh_gutter(keep=self._get_pending_commands())

    def _on_text_yscroll(self, first, last):
        self.yscroll.set(first, last)
        self._sync_scroll(self.text, self.line_numbers)
        self._place_markers()

    def _on_gutter_yscroll(self, first, last):
        # Gutter scrolled on its own (mouse wheel, cursor keys) - drag the text along
        self._sync_scroll(self.line_numbers, self.text)

    def _row_index(self, widget, line):
        """Index of the visible row for a line: the text shows an excluded block
        at its last line's newline, the gutter at its first line."""
        line = self._row_of(line)
        if widget is self.text and line in self.get_excluded():
            last = line
            while last + 1 in self.get_excluded():
                last += 1
            return f"{last}.end"
        return f"{line}.0"

    def _sync_scroll(self, source, target):
        """Scroll target so it shows the same top row as source, to the pixel.

        Syncing by line (not by scroll fraction) - the fractions of the two
        widgets differ slightly, which made them push each other around.
        """
        if getattr(self, "_syncing", False):
            return
        self._syncing = True
        try:
            line = int(source.index("@0,0").split(".")[0])
            src_info = source.dlineinfo(self._row_index(source, line))
            target_index = self._row_index(target, line)
            target.yview(target_index)
            tgt_info = target.dlineinfo(target_index)
            if src_info and tgt_info and src_info[1] != tgt_info[1]:
                target.yview_scroll(tgt_info[1] - src_info[1], "pixels")
        finally:
            self._syncing = False

    def _gutter_overtype(self, event):
        """Typing in the gutter: overtype, and remember exactly which chars were typed.

        The first key on an untouched field blanks it and starts at column 0, so
        it doesn't matter where in the number you clicked.
        """
        if len(event.char) != 1 or not event.char.isprintable():
            return None
        g = self.line_numbers
        if g.tag_ranges(tk.SEL):
            if "\n" in g.get(tk.SEL_FIRST, tk.SEL_LAST):
                return "break"
            g.delete(tk.SEL_FIRST, tk.SEL_LAST)
        line = g.index(tk.INSERT).split(".")[0]
        if not g.tag_nextrange("typed", f"{line}.0", f"{line}.end"):
            g.delete(f"{line}.0", f"{line}.end")
            g.insert(f"{line}.0", " " * FIELD_WIDTH)
            g.mark_set(tk.INSERT, f"{line}.0")
        if g.compare(tk.INSERT, "<", "insert lineend"):
            g.delete(tk.INSERT)
        g.insert(tk.INSERT, event.char, "typed")
        g.see(tk.INSERT)
        return "break"

    def _gutter_backspace(self, event):
        """Don't let BackSpace join gutter lines (keeps gutter aligned with text)."""
        g = self.line_numbers
        if g.tag_ranges(tk.SEL):
            if "\n" in g.get(tk.SEL_FIRST, tk.SEL_LAST):
                return "break"
            return None
        if g.compare(tk.INSERT, "==", "insert linestart"):
            return "break"
        return None

    def _gutter_delete(self, event):
        """Don't let Delete join gutter lines."""
        g = self.line_numbers
        if g.tag_ranges(tk.SEL):
            if "\n" in g.get(tk.SEL_FIRST, tk.SEL_LAST):
                return "break"
            return None
        if g.compare(tk.INSERT, "==", "insert lineend"):
            return "break"
        return None

    def _get_pending_commands(self):
        """Commands typed in the gutter: {line_number: command}.

        Only typed characters count (not leftover digits of the number).
        A label whose field was blanked out gives "." (remove label).
        """
        g = self.line_numbers
        typed = defaultdict(str)
        ranges = g.tag_ranges("typed")
        for start, end in zip(ranges[::2], ranges[1::2]):
            typed[int(str(start).split(".")[0])] += g.get(start, end)
        pending = {line: cmd.replace(" ", "") for line, cmd in typed.items()
                   if line <= len(self._gutter_fields) and cmd.strip()}
        content = g.get("1.0", "end-1c").split("\n")
        for line, orig in enumerate(self._gutter_fields, 1):
            if orig.startswith(".") and line not in pending and not content[line - 1].strip():
                pending[line] = "."
        return pending

    def process_line_command(self, event=None):
        """Process line commands typed directly on the gutter."""
        if self._processing:
            return "break"
        self._processing = True
        try:
            commands = self._get_pending_commands()
            if not commands:
                if event is not None and event.widget is self.line_numbers:
                    # Enter with nothing typed: move to the next line number
                    line = self._row_of(self._current_line(self.line_numbers))
                    self._focus_gutter(self._next_row(line, 1))
                else:
                    self.status.config(text="No line commands entered")
                return "break"
            if self.mode != "EDIT":
                self.status.config(text="Line commands only available in EDIT mode")
                self.refresh_gutter()
                return "break"

            self._cursor_line = None
            message, keep = self.apply_line_commands(commands)
            if message.startswith("Invalid line command"):
                self._error_lines = {int(n) for n in re.findall(r"line (\d+):", message)} or set(commands)
            elif not keep:
                self._error_lines.clear()
            # Rebuilding the gutter (hidden lines, tail space) must not move the screen
            top = self.text.index("@0,0 linestart")
            self.refresh_gutter(keep=keep)
            self.text.yview(top)
            self.text.update_idletasks()
            self._sync_scroll(self.text, self.line_numbers)
            self._place_markers()
            if self._text_entry:
                self._focus_text(self._text_entry[0])
            if self._cursor_line and not self._text_entry and event is not None and event.widget is self.line_numbers:
                # Like an empty Enter, move on to the next line number (after I: the
                # new line; if the cursor's line was deleted, the line now in its place)
                line, kept = self._cursor_line
                self._focus_gutter(self._next_row(self._row_of(line), 1) if kept else line)
            self.status.config(text=message)
        finally:
            self._processing = False
        return "break"  # prevents a newline from being inserted in the gutter

    def apply_line_commands(self, commands):
        """Apply all line commands at once, like ISPF does on Enter.

        commands: {line_number: command}. Returns (status message,
        {line_number: command} still pending, e.g. an unmatched DD).
        """
        lines = self.text.get("1.0", "end-1c").split("\n")
        n = len(lines)
        # Everything below is 0-based
        labels = {name: line - 1 for name, line in self.get_labels().items()}
        excluded = {line - 1 for line in self.get_excluded() if line <= n}
        block_end = {s: e for s, e in self._runs(excluded)}  # excluded block first -> last

        # --- Parse -----------------------------------------------------
        parsed, errors, info, label_cmds = [], [], [], []
        for ln in sorted(commands):
            raw = commands[ln].upper()
            if raw.startswith("."):
                if raw != "." and not LABEL_RE.match(raw):
                    errors.append(f"line {ln}: {commands[ln]} (label = . + 1-5 letters)")
                elif raw.startswith(".Z"):
                    errors.append(f"line {ln}: labels starting with Z are reserved")
                else:
                    label_cmds.append((ln - 1, raw[1:]))
                continue
            if raw in ("COLS", "BOUNDS"):
                info.append(f"{raw} not supported (simplified)")
                continue
            m = LINE_CMD_RE.match(raw)
            if not m or (m.group(1) and m.group(3)):
                errors.append(f"line {ln}: {commands[ln]}")
                continue
            op = m.group(2)
            if op in ("F", "L", "S") and ln - 1 not in block_end:
                errors.append(f"line {ln}: {op} only works on excluded lines")
                continue
            parsed.append((ln - 1, op, int(m.group(1) or m.group(3) or 0)))

        if errors:
            return "Invalid line command - " + ", ".join(errors), commands

        # --- Pair block commands, normalise to (op, start, end, count) -----
        # A command on an excluded block applies to the whole block.
        ops, open_blocks = [], {}
        for idx, op, cnt in parsed:
            if op in BLOCK_CMDS:
                if op in open_blocks:
                    start, start_cnt = open_blocks.pop(op)
                    if op in ("<<", ">>") and start_cnt and cnt and start_cnt != cnt:
                        if start_cnt != 2 and cnt != 2:
                            return (f"Data shift {op[0]} has conflicting amounts "
                                    f"on lines {start + 1} and {idx + 1}"), commands
                    if op in ("<<", ">>"):
                        shift = (start_cnt if cnt == 2 else cnt if start_cnt == 2
                                 else cnt or start_cnt or 2)
                    else:
                        shift = cnt or start_cnt
                    ops.append((BLOCK_CMDS[op], start, block_end.get(idx, idx), shift))
                else:
                    open_blocks[op] = (idx, cnt)
            elif op in ("D", "C", "M", "UC", "LC", "X", "HX"):
                end = min(idx + max(cnt, 1) - 1, n - 1)
                ops.append((op, idx, max(end, block_end.get(idx, idx)), 1))
            elif op in ("TS", "TF", "TE"):
                ops.append((op, idx, idx, cnt))
            else:  # I, R, A, B, (, ), F, L, S
                ops.append((op, idx, block_end.get(idx, idx), cnt))

        if open_blocks:
            names = ", ".join(sorted(open_blocks))
            return f"Block command {names} incomplete - enter the matching pair", commands

        if any(op in ("TS", "TF", "TE") for _, op, _, _ in ops) and len(ops) > 1:
            return "TS, TF and TE must be entered by themselves", commands

        sources = [o for o in ops if o[0] in ("C", "M")]
        dests = [o for o in ops if o[0] in ("A", "B")]
        overlay_dests = [o for o in ops if o[0] == "O"]
        if len(sources) > 1 or len(dests) + len(overlay_dests) > 1:
            return "Only one C/M source and one A/B/O destination allowed", commands
        if (dests or overlay_dests) and not sources and not self.line_clipboard:
            return "A/B/O needs a C or M (nothing copied yet)", commands

        # In ISPF, C/M is a pending source selection until its A/B/O target is
        # entered. Keep the source command visible and leave the buffer alone
        # across this Enter so the target can be typed in another line field.
        if sources and not dests and not overlay_dests:
            op = sources[0][0]
            # Keep the source marked, but advance the command-field cursor so
            # successive Enter presses move through the destination rows.
            self._cursor_line = (self._current_line(self.line_numbers), True)
            return (f"{op} pending - enter A, B, or O destination", commands)

        # --- Apply -------------------------------------------------------
        delete = set()
        before, after = defaultdict(list), defaultdict(list)
        msgs = []
        for op, s, e, cnt in ops:
            rng = range(s, e + 1)
            if op == "D":
                delete.update(rng)
                msgs.append(f"Deleted {len(rng)} line(s)")
            elif op == "I":
                after[e].extend([""] * max(cnt, 1))
                msgs.append(f"Inserted {max(cnt, 1)} line(s)")
            elif op == "R":
                after[e].extend(lines[s:e + 1] * max(cnt, 1))
                msgs.append(f"Repeated {len(rng)} line(s)")
            elif op in ("UC", "LC"):
                for k in rng:
                    lines[k] = lines[k].upper() if op == "UC" else lines[k].lower()
                msgs.append(f"{len(rng)} line(s) to {'UPPER' if op == 'UC' else 'lower'} case")
            elif op in ("(", ")"):
                cols = cnt or 2
                for k in rng:
                    lines[k] = lines[k][cols:] if op == "(" else " " * cols + lines[k]
                msgs.append(f"Shifted {len(rng)} line(s) {'left' if op == '(' else 'right'} {cols}")
            elif op in ("<", ">"):
                amount = cnt or 2
                for k in rng:
                    if op == "<":
                        # Data shifts remove indentation only, so nonblank data
                        # is never discarded as it can be by a column shift.
                        leading = len(lines[k]) - len(lines[k].lstrip(" "))
                        lines[k] = lines[k][min(amount, leading):]
                    else:
                        lines[k] = " " * amount + lines[k]
                msgs.append(f"Data shifted {len(rng)} line(s) {'left' if op == '<' else 'right'} {amount}")
            elif op == "HX":
                for k in rng:
                    # ISPF HX is a display command: retain the source line and
                    # put the high and low hex nibbles on two rows beneath it.
                    raw = lines[k].encode("utf-8")
                    high = "".join(f"{byte >> 4:X}" for byte in raw)
                    low = "".join(f"{byte & 0x0F:X}" for byte in raw)
                    after[k].extend((f"=HEX> {high}", f"=HEX> {low}"))
                msgs.append(f"Displayed two hex info lines under {len(rng)} line(s)")
            elif op == "TS":
                line = lines[s]
                cursor = self.text.index(tk.INSERT)
                split_col = (int(cursor.split(".")[1])
                             if int(cursor.split(".")[0]) == s + 1 else len(line))
                split_col = min(split_col, len(line))
                lines[s] = line[:split_col]
                after[s].extend([""] * max(cnt, 1) + [line[split_col:]])
                msgs.append(f"Split line {s + 1}; inserted {max(cnt, 1)} blank line(s)")
            elif op == "TF":
                start_line = lines[s]
                if start_line.strip() and not start_line.startswith("=HEX> "):
                    indent = len(start_line) - len(start_line.lstrip())
                    paragraph = [s]
                    for k in range(s + 1, n):
                        candidate = lines[k]
                        if (not candidate.strip() or candidate.startswith("=HEX> ")
                                or len(candidate) - len(candidate.lstrip()) != indent):
                            break
                        paragraph.append(k)
                    words = " ".join(lines[k].strip() for k in paragraph)
                    width = max(cnt or 72, indent + 1)
                    flowed = textwrap.wrap(words, width=width,
                                           initial_indent=" " * indent,
                                           subsequent_indent=" " * indent,
                                           break_long_words=False,
                                           break_on_hyphens=False) or [" " * indent]
                    lines[s] = flowed[0]
                    after[s].extend(flowed[1:])
                    delete.update(paragraph[1:])
                    msgs.append(f"Flowed {len(paragraph)} line(s) to column {width}")
                else:
                    msgs.append(f"Line {s + 1} is blank; nothing to flow")
            elif op == "TE":
                count = cnt or self._text_entry_default_count(s + 1)
                after[s].extend([""] * count)
                msgs.append(f"Text entry area opened with {count} line(s); press Enter to finish")
            elif op == "X":
                excluded.update(rng)
                msgs.append(f"Excluded {len(rng)} line(s)")
            elif op in ("F", "L", "S"):
                k = min(max(cnt, 1), len(rng))
                shown = rng[-k:] if op == "L" else rng[:k]
                excluded.difference_update(shown)
                msgs.append(f"Showing {k} line(s)")

        if sources:
            op, s, e, _ = sources[0]
            self.line_clipboard = [line for i, line in enumerate(lines[s:e + 1], s + 1)
                                   if not line.startswith("=HEX> ")
                                   and not self._is_compare_line(i)]
            self.clipboard_line = "\n".join(self.line_clipboard) + "\n"
            if op == "M":
                delete.update(range(s, e + 1))
            if not dests and not overlay_dests:
                msgs.append(f"{e - s + 1} line(s) {'moved' if op == 'M' else 'copied'}"
                            " - use A, B, or O to paste/overlay")
        if dests:
            op, s, e, cnt = dests[0]
            payload = self.line_clipboard * max(cnt, 1)
            if op == "A":
                after[e][:0] = payload
            else:
                before[s].extend(payload)
            msgs.append(f"Pasted {len(payload)} line(s) {'after' if op == 'A' else 'before'} line {s + 1}")
        if overlay_dests:
            _op, dest_start, dest_end, cnt = overlay_dests[0]
            if dest_end == dest_start:
                dest_end = min(dest_start + max(cnt, 1) - 1, n - 1)
            if sources and sources[0][0] == "M":
                source_indexes = set(range(sources[0][1], sources[0][2] + 1))
                destination_indexes = set(range(dest_start, dest_end + 1))
                if source_indexes & destination_indexes:
                    return "Cannot move lines over themselves with O/OO", commands
            source_lines = self.line_clipboard
            target_indexes = [i for i in range(dest_start, dest_end + 1)
                              if not lines[i].startswith("=HEX> ")
                              and not self._is_compare_line(i + 1)]
            if not source_lines or not target_indexes:
                return "O/OO needs standard source and destination lines", commands
            for offset, target_index in enumerate(target_indexes):
                source = source_lines[offset % len(source_lines)]
                original = lines[target_index]
                original_length = len(original)
                width = max(original_length, len(source))
                target = list(original.ljust(width))
                for column, char in enumerate(source):
                    if char != " " and target[column] == " ":
                        target[column] = char
                result = "".join(target)
                if len(result) > original_length:
                    last_data = max((i + 1 for i, char in enumerate(result)
                                     if char != " "), default=original_length)
                    result = result[:max(original_length, last_data)]
                lines[target_index] = result
            msgs.append(f"Overlaid {len(target_indexes)} line(s)")

        # Labels: one per line, a label name lives on one line only
        for idx, name in label_cmds:
            labels = {k: v for k, v in labels.items() if v != idx and k != name}
            if name:
                labels[name] = idx
                msgs.append(f"Label .{name} set")
            else:
                msgs.append("Label removed")

        new_lines, remap = [], {}
        for i, line in enumerate(lines):
            new_lines.extend(before[i])
            if i not in delete:
                remap[i] = len(new_lines)
                new_lines.append(line)
            new_lines.extend(after[i])

        # Labels and excluded lines follow their lines; deleted lines drop them
        new_labels = {k: remap[v] + 1 for k, v in labels.items() if v in remap}
        new_excluded = {remap[v] + 1 for v in excluded if v in remap}
        # The screen stays where it was: the old top line (or the next kept one) stays on top
        top = int(self.text.index("@0,0").split(".")[0]) - 1
        kept = [remap[v] for v in range(top, n) if v in remap]
        new_top = kept[0] + 1 if kept else len(new_lines)
        # Where the line command cursor was: its line (or, if deleted, the next kept one)
        cursor = self._current_line(self.line_numbers) - 1
        kept = [remap[v] for v in range(cursor, n) if v in remap]
        self._cursor_line = (kept[0] + 1 if kept else len(new_lines), cursor in remap)
        self._commit_text("\n".join(new_lines), (new_labels, new_excluded))
        text_entry_ops = [o for o in ops if o[0] == "TE"]
        if text_entry_ops:
            _, s, _, cnt = text_entry_ops[0]
            count = cnt or self._text_entry_default_count(s + 1)
            self._text_entry = (remap[s] + 2, count)
        self.text.yview(f"{new_top}.0")
        return "; ".join(msgs + info) or "Line commands processed", {}

    def _replace_text(self, content):
        """Replace the whole buffer as a single undo step, keeping the view."""
        if content == self.text.get("1.0", "end-1c"):
            return
        top = self.text.index("@0,0 linestart")  # a line, not a fraction: the length changes
        insert = self.text.index(tk.INSERT)
        self.text.config(autoseparators=False)
        self.text.edit_separator()
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.text.edit_separator()
        self.text.config(autoseparators=True)
        self.text.mark_set(tk.INSERT, insert)
        self.text.yview(top)

    # ------------------------------------------------------------------
    # Primary Commands
    # ------------------------------------------------------------------
    def process_primary_command(self, event=None):
        """Parse and execute a primary command from the command line."""
        cmd = self.cmd_entry.get().strip()
        parts = cmd.split()
        command = parts[0].upper() if parts else ""
        command = self.PRIMARY_ALIASES.get(command, command)
        args = parts[1:]

        if cmd:
            if not self._command_history or self._command_history[-1] != cmd:
                self._command_history.append(cmd)
            self._history_index = len(self._command_history)

        # Like ISPF, Enter also processes pending line commands (RESET discards them)
        if command not in ("RES", "RESET") and self._get_pending_commands():
            self.process_line_command()

        self.cmd_entry.delete(0, tk.END)
        if not cmd:
            # Empty command line: Enter jumps to the first line number on the page
            self._focus_gutter(self._first_row_on_page())
            return

        if command == "SAVE":
            self.save_file()
        elif command in ("CAN", "CANCEL"):
            self.cancel_editor()
        elif command in ("END", "EXIT"):
            self.end_editor()
        elif command in ("RFIND", "RF"):
            self.repeat_find()
        elif command in ("RCHANGE", "RCH"):
            self.repeat_change()
        elif command in ("RETRIEVE", "RETR"):
            self.retrieve_command()
        elif command in ("FIND", "F"):
            # Raw operands, so spaces inside quotes are kept
            term = cmd[len(parts[0]):].strip() or simpledialog.askstring("Find", "Search for:")
            if term:
                self.find_text(term)
        elif command in ("CHANGE", "C", "CHG"):
            operands = cmd[len(parts[0]):].strip()
            strings, options, columns = self._parse_search_operands(operands)
            if len(strings) >= 2:
                (old, exact), (new, _) = strings[0], strings[1]
                self.change_text(old, new, exact=exact, options=options, columns=columns)
            else:
                old = simpledialog.askstring("Change", "Find:")
                new = simpledialog.askstring("Change", "Replace with:")
                if old and new is not None:
                    self.change_text(old, new)
        elif command in ("LOCATE", "LOC", "L"):
            locate_categories = {"CHANGE", "ERROR", "EXCLUDED", "LABEL", "SPECIAL", "COMMAND"}
            locate_directions = set(self.FIND_DIRECTIONS)
            if len(args) > 1 and args[0].upper() in locate_directions and args[1].upper() in locate_categories:
                self.locate(args[1], args[0])
            elif args and args[0].upper() in locate_categories:
                self.locate(args[0], args[1] if len(args) > 1 else "NEXT")
            else:
                self.locate(args[0] if args else "")
        elif command == "COMPARE":
            raw = cmd[len(parts[0]):].strip()
            if not raw:
                if self.compare_filename:
                    self.compare_selected_file()
                else:
                    self.select_compare_file(compare_now=True)
            elif raw.upper() == "*":
                self.compare_session()
            else:
                compare_args = [value for value, _quoted in self._tokenize(raw)]
                if len(compare_args) != 1:
                    self.status.config(text="COMPARE: use COMPARE * or COMPARE file")
                else:
                    self.compare_file(compare_args[0])
        elif command == "DELETE":
            self.delete_text(cmd[len(parts[0]):].strip())
        elif command == "SORT":
            self.sort_text(cmd[len(parts[0]):].strip())
        elif command in ("COPY", "MOVE"):
            self.copy_move_data(command, cmd[len(parts[0]):].strip())
        elif command in ("CREATE", "REPLACE"):
            self.create_replace_data(command, cmd[len(parts[0]):].strip())
        elif command in ("LEFT", "RIGHT"):
            self.scroll_horizontal(command, args[0] if args else self.scroll_mode)
        elif command in ("UP", "DOWN"):
            self.scroll_vertical(command, args[0] if args else self.scroll_mode)
        elif command in ("EXCLUDE", "EXC", "EX", "X"):
            raw = cmd[len(parts[0]):].strip()
            strings, options, _columns = self._parse_search_operands(raw)
            if strings:
                search_text, exact = strings[0]
                if len(strings) > 1 or any(o.startswith(".") for o in options):
                    self.status.config(text="EXCLUDE: use a string and optional ALL")
                else:
                    self.exclude_text(search_text, all_matches="ALL" in options, exact=exact)
            else:
                self.exclude_all(args)
        elif command in ("RESET", "RES"):
            self.reset(args)
        elif command == "UC":
            self.change_case("upper")
        elif command == "LC":
            self.change_case("lower")
        elif command == "HEX":
            self.toggle_hex()
        elif command == "HELP":
            self.show_help()
        elif command == "UNDO":
            self.undo(args)
        elif command == "REDO":
            self.redo()
        elif command == "MODEL":
            self.status.config(text="MODEL: Template display (simplified)")
        elif command == "HILITE":
            lang = args[0].upper() if args else "JCL"
            self.status.config(text=f"HILITE: Syntax highlighting for {lang} (simplified)")
        elif command == "RECOVERY":
            self.status.config(text="REC ON/OFF: Undo history is always available in Tkinter")
        elif command == "TS":
            self.status.config(text="TS: Text Split (simplified - use Enter key)")
        elif command == "TF":
            self.status.config(text="TF: Text Flow (simplified - use Delete key)")
        elif command == "CUT":
            self.cut_selection()
        elif command == "PASTE":
            self.paste_clipboard()
        elif command == "INDEX":
            self.show_help()
        else:
            self.status.config(text=f"Unknown command: {command}")

    def _locate_category_lines(self, category):
        """Return line numbers matching a LOCATE category."""
        category = category.upper()
        count = self._text_line_count()
        if category == "EXCLUDED":
            return sorted(n for n in self.get_excluded() if 1 <= n <= count)
        if category == "LABEL":
            return sorted(n for n in self.get_labels().values() if 1 <= n <= count)
        if category == "COMMAND":
            return sorted(n for n in self._get_pending_commands() if 1 <= n <= count)
        if category == "ERROR":
            return sorted(n for n in self._error_lines if 1 <= n <= count)
        lines = self.text.get("1.0", "end-1c").split("\n")
        if category == "SPECIAL":
            return [i for i, line in enumerate(lines, 1)
                    if line.startswith("=HEX> ") or self._is_compare_row(i)]
        if category == "CHANGE":
            baseline = getattr(self, "_baseline_lines", [""])
            positions = [i for i, line in enumerate(lines, 1)
                         if not line.startswith("=HEX> ") and not self._is_compare_line(i)]
            comparable = [lines[i - 1] for i in positions]
            changed = set()
            for tag, _i1, _i2, j1, j2 in SequenceMatcher(None, baseline, comparable).get_opcodes():
                if tag in ("replace", "insert"):
                    changed.update(positions[j1:j2])
                elif tag == "delete":
                    # A deletion has no current line; point at the next line,
                    # or the previous one when the deletion was at EOF.
                    if positions:
                        changed.add(positions[min(j1, len(positions) - 1)])
            return sorted(changed)
        return []

    def compare_session(self):
        """Compare the current buffer with the baseline captured for this session."""
        self._compare_lines(self._baseline_lines, "session baseline")

    def _compare_lines(self, baseline_lines, comparison_name):
        """Show changed current rows in green and removed rows below in red."""
        original = self.text.get("1.0", "end-1c").split("\n")
        labels, excluded = self._get_line_state()
        keep = [(i, line) for i, line in enumerate(original, 1)
                if not self._is_compare_line(i)]
        # Compare source records only; HX and existing compare rows are display data.
        source = [(old_line, line) for old_line, line in keep
                  if not line.startswith("=HEX> ")]
        before = list(baseline_lines)
        after = [line for _, line in source]
        if before == [""]:
            before = []
        elif before and before[-1] == "":
            before.pop()
        if after == [""]:
            after = []
        elif after and after[-1] == "":
            after.pop()

        removed_after = defaultdict(list)
        added = set()
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after).get_opcodes():
            if tag in ("delete", "replace"):
                # A pure deletion is shown at the next boundary (beneath the
                # preceding data line). Replaced records follow their new rows.
                boundary = j1 if tag == "delete" else j2
                removed_after[boundary].extend(before[i1:i2])
            if tag in ("insert", "replace"):
                added.update(range(j1, j2))

        output, output_kinds, old_to_new = [], [], {}
        source_index = 0
        for old_line, line in keep:
            if line.startswith("=HEX> "):
                old_to_new[old_line] = len(output) + 1
                output.append(line)
                output_kinds.append("hex")
                continue
            for removed in removed_after.get(source_index, ()):
                output.append(removed)
                output_kinds.append("removed")
            old_to_new[old_line] = len(output) + 1
            output.append(line)
            output_kinds.append("added" if source_index in added else None)
            source_index += 1
        for removed in removed_after.get(source_index, ()):
            output.append(removed)
            output_kinds.append("removed")

        new_labels = {name: old_to_new[line] for name, line in labels.items()
                      if line in old_to_new}
        new_excluded = {old_to_new[line] for line in excluded if line in old_to_new}
        old_dirty = self._dirty
        self._processing = True
        try:
            self._commit_text("\n".join(output), (new_labels, new_excluded))
            self.text.tag_remove("compare_added", "1.0", tk.END)
            self.text.tag_remove("compare_removed", "1.0", tk.END)
            for line_number, kind in enumerate(output_kinds, 1):
                tag = {"added": "compare_added", "removed": "compare_removed"}.get(kind)
                if tag:
                    self.text.tag_add(tag, f"{line_number}.0", f"{line_number}.end +1c")
            self.text.edit_modified(False)
        finally:
            self._processing = False
        self._dirty = old_dirty
        self.refresh_gutter(keep=self._get_pending_commands())
        change_rows = len(added) + sum(map(len, removed_after.values()))
        prefix = "COMPARE *" if comparison_name == "session baseline" else f"COMPARE {comparison_name}"
        self.status.config(text=(f"{prefix}: {change_rows} change row(s) shown; RESET removes them")
                           if change_rows else f"{prefix}: no changes")

    def delete_text(self, raw=""):
        """Delete a line range, or all excluded/non-excluded lines.

        ISPF requires ALL when the selection is defined by X/NX rather than
        by an explicit range. A range is inclusive and may use labels or line
        numbers. This deliberately rejects an unqualified DELETE/DELETE ALL
        so a missing operand cannot erase the complete buffer by accident.
        """
        operands = [value.upper() for value, _quoted in self._tokenize(raw)]
        all_lines = [value for value in operands if value == "ALL"]
        x_modes = [value for value in operands if value in ("X", "NX")]
        targets = [value for value in operands
                   if value not in ("ALL", "X", "NX")]
        if len(all_lines) > 1:
            self.status.config(text="DELETE: duplicate ALL operand")
            return
        if len(set(x_modes)) > 1:
            self.status.config(text="DELETE: choose X or NX")
            return
        if len(x_modes) > 1:
            self.status.config(text="DELETE: duplicate X/NX operand")
            return
        if len(targets) > 2:
            self.status.config(text="DELETE: use [ALL] [X|NX] [line|label [line|label]]")
            return

        line_count = self._text_line_count()
        if targets:
            resolved = []
            for value in targets:
                if value.isdigit():
                    number = int(value)
                    resolved.append(number if 1 <= number <= line_count else None)
                else:
                    resolved.append(self._resolve_target(value))
            if any(line is None for line in resolved):
                self.status.config(text="DELETE: line number or label not found")
                return
            first, last = (min(resolved), max(resolved))
        else:
            first, last = 1, line_count
            if not x_modes or not all_lines:
                self.status.config(text="DELETE: specify a line range, or use ALL X/NX")
                return

        excluded = self.get_excluded()
        mode = x_modes[0] if x_modes else None
        selected = {line for line in range(first, last + 1)
                    if (mode != "X" or line in excluded)
                    and (mode != "NX" or line not in excluded)}
        if not selected:
            self.status.config(text="DELETE: no matching lines")
            return

        lines = self.text.get("1.0", "end-1c").split("\n")
        old_labels, old_excluded = self._get_line_state()
        new_lines, remap = [], {}
        for index, line in enumerate(lines):
            if index + 1 not in selected:
                remap[index] = len(new_lines)
                new_lines.append(line)
        # Tk's Text widget always contains one line; after deleting every
        # record, retain its required empty line as the editable buffer.
        if not new_lines:
            new_lines = [""]
        new_labels = {name: remap[line - 1] + 1
                      for name, line in old_labels.items() if line - 1 in remap}
        new_excluded = {remap[line - 1] + 1
                        for line in old_excluded if line - 1 in remap}

        current = self._current_line(self.text)
        surviving = [old for old in range(current - 1, line_count) if old in remap]
        if not surviving:
            surviving = [old for old in range(current - 2, -1, -1) if old in remap]
        new_cursor = remap[surviving[0]] + 1 if surviving else 1
        self._commit_text("\n".join(new_lines), (new_labels, new_excluded))
        self._dirty = True
        self.refresh_gutter(keep=self._get_pending_commands())
        self._focus_row(min(new_cursor, self._text_line_count()))
        self.status.config(text=f"Deleted {len(selected)} line(s)")

    def sort_text(self, raw=""):
        """Sort records by full line or up to five column ranges."""
        values = [value.upper() if not quoted else value
                  for value, quoted in self._tokenize(raw)]
        labels = [value for value in values if value.startswith(".")]
        if len(labels) not in (0, 2):
            self.status.config(text="SORT: a range needs two labels (.start .end)")
            return
        x_modes = [value for value in values if value in ("X", "NX")]
        if len(set(x_modes)) > 1:
            self.status.config(text="SORT: choose X or NX, not both")
            return
        excluded_mode = x_modes[0] if x_modes else None
        operands = [value for value in values
                    if not value.startswith(".") and value not in ("X", "NX")]
        fields = []
        if len(operands) == 1 and operands[0] in ("A", "D"):
            fields = [(1, None, operands[0])]
        elif operands:
            i = 0
            while i < len(operands):
                direction = None
                if operands[i] in ("A", "D"):
                    direction = operands[i]
                    i += 1
                if i + 1 >= len(operands) or not operands[i].isdigit() or not operands[i + 1].isdigit():
                    self.status.config(text="SORT: use [A|D] start_col end_col for each sort field")
                    return
                start_col, end_col = int(operands[i]), int(operands[i + 1])
                i += 2
                # A direction followed by another numeric pair begins the
                # next field (for example, ``A 1 2 D 3 4``). Accept a
                # direction after a range only when it is the final operand.
                if (i == len(operands) - 1
                        and operands[i] in ("A", "D")):
                    if direction is not None:
                        self.status.config(text="SORT: specify direction once per field")
                        return
                    direction = operands[i]
                    i += 1
                if start_col < 1 or end_col < start_col:
                    self.status.config(text="SORT: invalid column range")
                    return
                fields.append((start_col, end_col, direction))
                if len(fields) > 5:
                    self.status.config(text="SORT: a maximum of five fields is allowed")
                    return
            if len(fields) > 1 and any(direction is None for _, _, direction in fields):
                self.status.config(text="SORT: specify A or D for every sort field")
                return
            fields = [(start, end, direction or "A") for start, end, direction in fields]
        else:
            fields = [(1, None, "A")]

        lines = self.text.get("1.0", "end-1c").split("\n")
        first, last = 1, len(lines)
        if labels:
            resolved = [self._resolve_target(label) for label in labels]
            if None in resolved:
                self.status.config(text="SORT: label not found")
                return
            first, last = sorted(resolved)
        excluded = self.get_excluded()
        positions = [index for index in range(first - 1, min(last, len(lines)))
                     if not lines[index].startswith("=HEX> ")
                     and not self._is_compare_line(index + 1)
                     and (excluded_mode != "X" or index + 1 in excluded)
                     and (excluded_mode != "NX" or index + 1 not in excluded)]
        if len(positions) < 2:
            self.status.config(text="SORT: fewer than two eligible lines")
            return

        records = [(index, lines[index]) for index in positions]
        for start_col, end_col, direction in reversed(fields):
            def field_key(record, start_col=start_col, end_col=end_col):
                text = record[1][start_col - 1:end_col] if end_col else record[1][start_col - 1:]
                return text.encode("utf-8").hex() if self.hex_mode else text
            records = sorted(records, key=field_key, reverse=direction == "D")

        output = list(lines)
        moved = {}
        for destination, (source, line) in zip(positions, records):
            output[destination] = line
            moved[source] = destination
        if output == lines:
            self.status.config(text="SORT: lines already in order")
            return
        old_labels, old_excluded = self._get_line_state()
        new_labels = {name: moved.get(line - 1, line - 1) + 1
                      for name, line in old_labels.items()}
        new_excluded = {moved.get(line - 1, line - 1) + 1
                        for line in old_excluded}
        content = "\n".join(output)
        self._commit_text(content, (new_labels, new_excluded))
        self._dirty = True
        self.refresh_gutter(keep=self._get_pending_commands())
        self.status.config(text=f"SORT: sorted {len(positions)} line(s)")

    def locate(self, target, direction=None):
        """Locate a line number, label, or categorized line condition."""
        if not target:
            self.status.config(text="LOCATE needs a line number, .label, or category")
            return
        category = target.upper()
        categories = {"CHANGE", "ERROR", "EXCLUDED", "LABEL", "SPECIAL", "COMMAND"}
        if category in categories:
            direction = (direction or "NEXT").upper()
            if direction not in self.FIND_DIRECTIONS:
                self.status.config(text="LOCATE: direction must be FIRST, LAST, NEXT, or PREV")
                return
            candidates = self._locate_category_lines(category)
            if not candidates:
                self.status.config(text=f"LOCATE {category}: no matching lines")
                return
            current = self._current_line(self.text)
            if direction == "FIRST":
                line = candidates[0]
            elif direction == "LAST":
                line = candidates[-1]
            elif direction == "PREV":
                line = next((n for n in reversed(candidates) if n < current), candidates[-1])
            else:
                line = next((n for n in candidates if n > current), candidates[0])
        else:
            line = self._resolve_target(target)
        if line is None:
            self.status.config(text=f"Label {target.upper()} not found")
            return
        line = self._row_of(line)
        self._apply_tail_space()
        self.text.update_idletasks()
        self.text.yview(f"{line}.0")
        if line not in self.get_excluded():
            self.text.mark_set(tk.INSERT, f"{line}.0")
        # Cursor on the located line's number, ready for a line command
        self._focus_gutter(line)
        self._place_markers()
        self.status.config(text=f"Located {category} line {line}" if category in categories
                            else f"Located line {line}")

    def _char_width(self):
        return max(tkfont.Font(font=self.text.cget("font")).measure("0"), 1)

    def _visible_columns(self):
        inner = self.text.winfo_width() - 2 * (int(self.text.cget("borderwidth"))
                                               + int(self.text.cget("highlightthickness"))
                                               + int(self.text.cget("padx")))
        return max(inner // self._char_width(), 1)

    def _left_column(self):
        """1-based column shown at the left edge of the text area."""
        first, last = self.text.xview()
        if last - first <= 0:
            return 1
        total_px = self.text.winfo_width() / (last - first)
        return int(round(first * total_px / self._char_width())) + 1

    def scroll_horizontal(self, direction, amount):
        """LEFT/RIGHT [n | MAX | PAGE | HALF] - scroll the data columns."""
        amount = amount.upper()
        sign = -1 if direction == "LEFT" else 1
        page = self._visible_columns()
        if amount in ("MAX", "M"):
            self.text.xview_moveto(0.0 if sign < 0 else 1.0)
        elif amount.isdigit():
            self.text.xview_scroll(sign * int(amount), "units")
        elif amount in ("PAGE", "P"):
            self.text.xview_scroll(sign * page, "units")
        elif amount in ("HALF", "H"):
            self.text.xview_scroll(sign * max(page // 2, 1), "units")
        elif amount in ("CSR", "C"):
            cursor_col = int(self.text.index(tk.INSERT).split(".")[1]) + 1
            max_col = max((len(line) for line in
                           self.text.get("1.0", "end-1c").split("\n")), default=page)
            target_left = max(1, cursor_col - page + 1) if sign < 0 else cursor_col
            fraction = (target_left - 1) / max(max_col - page, 1)
            self.text.xview_moveto(min(fraction, 1.0))
        else:
            self.status.config(text=f"{direction}: amount must be a number, MAX, PAGE or HALF")
            return
        self.text.update_idletasks()
        left = self._left_column()
        self._update_ispf_header()
        self.status.config(text=f"Columns {left}-{left + page - 1}")

    def _visible_row_count(self):
        line_height = tkfont.Font(font=self.text.cget("font")).metrics("linespace")
        return max(self.text.winfo_height() // max(line_height, 1), 1)

    def scroll_vertical(self, direction, amount):
        """UP/DOWN [n | MAX | PAGE | HALF | CSR] - scroll the data lines.

        Counts screen rows, so an excluded block is one row (like ISPF).
        """
        amount = amount.upper()
        sign = -1 if direction == "UP" else 1
        page = self._visible_row_count()
        rows = self._visible_rows()
        top = rows.index(self._row_of(int(self.text.index("@0,0").split(".")[0])))
        # Work in rows and jump with yview(index): Tk's own unit scrolling
        # leaves half-visible lines at the top when scrolling up
        if amount in ("MAX", "M"):
            # UP MAX: first line on top; DOWN MAX: last page, ending with the last line
            new_top = 0 if sign < 0 else max(0, len(rows) - page)
        elif amount in ("CSR", "C"):
            # DOWN CSR: cursor line to the top; UP CSR: cursor line to the bottom
            cursor = self._row_of(self._current_line(self.text))
            pos = rows.index(cursor) if cursor in rows else top
            new_top = pos if sign > 0 else pos - page + 1
            if (new_top - top) * sign <= 0:  # cursor already at that edge: a page
                new_top = top + sign * page
        elif amount.isdigit():
            new_top = top + sign * int(amount)
        elif amount in ("PAGE", "P"):
            new_top = top + sign * page
        elif amount in ("HALF", "H"):
            new_top = top + sign * max(page // 2, 1)
        else:
            self.status.config(text=f"{direction}: amount must be a number, MAX, PAGE, HALF or CSR")
            return
        new_top = max(0, min(new_top, len(rows) - 1))
        self.text.yview(f"{rows[new_top]}.0")
        self.text.update_idletasks()
        self._place_markers()
        last = self._text_line_count()
        first = int(self.text.index("@0,0").split(".")[0])
        bottom = int(self.text.index(f"@0,{self.text.winfo_height() - 1}").split(".")[0])
        self.status.config(text=f"Lines {first}-{min(bottom, last)} of {last}")

    def exclude_all(self, args):
        """X ALL [.label1 .label2] - exclude every line (or every line in the range)."""
        words = [a.upper() for a in args]
        labels = [a for a in args if a.startswith(".")]
        if "ALL" not in words or len(words) != 1 + len(labels):
            self.status.config(text="EXCLUDE: use X ALL [.a .b]")
            return
        first, last = 1, self._text_line_count()
        if labels:
            if len(labels) != 2:
                self.status.config(text="EXCLUDE: a range needs two labels (.a .b)")
                return
            first, last = (self._resolve_target(lab) for lab in labels)
            if first is None or last is None:
                self.status.config(text="Label not found")
                return
            first, last = sorted((first, last))
        self.set_excluded(self.get_excluded() | set(range(first, last + 1)))
        self.refresh_gutter(keep=self._get_pending_commands())
        self.text.yview(f"{self._row_of(first)}.0")
        self._place_markers()
        self.status.config(text=f"{last - first + 1} line(s) excluded")

    def exclude_text(self, search_term, all_matches=False, exact=False):
        """Exclude the next matching line, or every matching line with ALL."""
        if not search_term:
            self.status.config(text="EXCLUDE: missing search string")
            return
        lines = self.text.get("1.0", "end-1c").split("\n")
        if not exact:
            needle = search_term.casefold()
        else:
            needle = search_term
        matches = []
        for line_no, line in enumerate(lines, 1):
            haystack = line if exact else line.casefold()
            if needle in haystack:
                matches.append(line_no)
        if not matches:
            self.status.config(text=f"EXCLUDE: '{search_term}' not found")
            return
        if not all_matches:
            cursor_line = self._current_line(self.text)
            chosen = next((line for line in matches if line >= cursor_line), matches[0])
            matches = [chosen]
        self.set_excluded(self.get_excluded() | set(matches))
        self.refresh_gutter(keep=self._get_pending_commands())
        first = matches[0]
        self.text.yview(f"{self._row_of(first)}.0")
        self._place_markers()
        scope = "matching line(s)" if all_matches else "next matching line"
        self.status.config(text=f"Excluded {len(matches)} {scope} for '{search_term}'")

    def reset(self, args):
        """RESET [EXCLUDED] [COMMAND] [FIND] [LABEL] - default: all except labels."""
        keys = {a.upper() for a in args}
        unknown = keys - {"EXCLUDED", "EX", "X", "COMMAND", "COM", "FIND", "FIN",
                          "LABEL", "LAB", "ALL"}
        if unknown:
            self.status.config(text=f"RESET: unknown keyword {', '.join(sorted(unknown))}")
            return
        everything = not keys or "ALL" in keys
        view = self._get_view()
        done = []
        # HX rows are transient display information. RES clears them along
        # with the other editor-only state, while preserving labels/exclusions.
        old_lines = self.text.get("1.0", "end-1c").split("\n")
        retained = [i for i, line in enumerate(old_lines)
                    if not line.startswith("=HEX> ") and not self._is_compare_line(i + 1)]
        if len(retained) != len(old_lines):
            remap = {old: new for new, old in enumerate(retained)}
            labels, excluded = self._get_line_state()
            new_labels = {name: remap[line - 1] + 1 for name, line in labels.items()
                          if line - 1 in remap}
            new_excluded = {remap[line - 1] + 1 for line in excluded
                            if line - 1 in remap}
            old_top = int(view[0].split(".")[0]) - 1
            old_insert = int(view[1].split(".")[0]) - 1
            def mapped_line(old):
                if old in remap:
                    return remap[old] + 1
                later = next((i for i in retained if i >= old), retained[-1] if retained else 0)
                return remap[later] + 1
            self._commit_text("\n".join(old_lines[i] for i in retained),
                              (new_labels, new_excluded))
            view = (f"{mapped_line(old_top)}.0", f"{mapped_line(old_insert)}.0")
            done.append("hex info lines")
        self.text.tag_remove("compare_added", "1.0", tk.END)
        self.text.tag_remove("compare_removed", "1.0", tk.END)
        if everything or keys & {"EXCLUDED", "EX", "X"}:
            self.set_excluded(set())
            done.append("excluded lines")
        if everything or keys & {"FIND", "FIN"}:
            self.text.tag_remove("found", "1.0", tk.END)
            done.append("find highlight")
        if "ALL" in keys or keys & {"LABEL", "LAB"}:
            self.set_labels({})
            done.append("labels")
        clear_commands = everything or keys & {"COMMAND", "COM"}
        if clear_commands:
            done.append("pending line commands")
        self.refresh_gutter(keep=None if clear_commands else self._get_pending_commands())
        self._set_view(view)  # shown lines come back without moving the page
        self.status.config(text="Reset: " + ", ".join(done))

    def undo(self, args=()):
        """Undo one edit interaction, or all available interactions."""
        options = [arg.upper() for arg in args]
        if options not in ([], ["ALL"]):
            self.status.config(text="UNDO: use UNDO or UNDO ALL")
            return
        view = self._get_view()
        count = 0
        while True:
            try:
                self.text.edit_undo()
                count += 1
            except tk.TclError:
                break
            if not options:
                break
        if not count:
            self.status.config(text="Nothing to undo")
            return
        self._restore_line_state(view)
        self.status.config(text=("Undid all available interactions" if options
                                 else "Undid one interaction"))

    def redo(self):
        view = self._get_view()
        try:
            self.text.edit_redo()
        except tk.TclError:
            self.status.config(text="Nothing to redo")
            return
        self._restore_line_state(view)

    def _get_view(self):
        """Top line and cursor, so undo/redo can stay on the current page."""
        return self.text.index("@0,0 linestart"), self.text.index(tk.INSERT)

    def _set_view(self, view):
        # Tk's undo re-inserts the text and scrolls to its end (= end of file)
        top, insert = view
        self.text.mark_set(tk.INSERT, insert)
        self.text.yview(top)
        self.text.update_idletasks()
        self._sync_scroll(self.text, self.line_numbers)
        self._place_markers()

    # ------------------------------------------------------------------
    # File Operations
    # ------------------------------------------------------------------
    def _refresh_recent_files_menu(self):
        menu = getattr(self, "recent_files_menu", None)
        if menu is None:
            return
        menu.delete(0, tk.END)
        if not self._recent_files:
            menu.add_command(label="(No recent files)", state=tk.DISABLED)
            return
        for path in self._recent_files:
            menu.add_command(label=path, command=lambda selected=path:
                             self.open_file("EDIT", selected))
        menu.add_separator()
        menu.add_command(label="Clear Recent Files", command=self._clear_recent_files)

    def _load_recent_files(self):
        """Restore the recent-file list between editor sessions."""
        try:
            paths = json.loads(self._recent_files_path.read_text(encoding="utf-8"))
            if not isinstance(paths, list):
                return []
            existing = []
            for path in paths:
                if isinstance(path, str) and Path(path).is_file():
                    resolved = str(Path(path).resolve())
                    if resolved not in existing:
                        existing.append(resolved)
            return existing[:10]
        except (OSError, ValueError, TypeError):
            return []

    def _save_recent_files(self):
        try:
            self._recent_files_path.write_text(
                json.dumps(self._recent_files, indent=2), encoding="utf-8")
        except OSError:
            # Keep the in-memory menu usable if the application folder is read-only.
            pass

    def _add_recent_file(self, path):
        resolved = str(Path(path).expanduser().resolve())
        self._recent_files = [item for item in self._recent_files if item != resolved]
        self._recent_files.insert(0, resolved)
        del self._recent_files[10:]
        self._save_recent_files()
        self._refresh_recent_files_menu()

    def _clear_recent_files(self):
        self._recent_files.clear()
        self._save_recent_files()
        self._refresh_recent_files_menu()

    def select_compare_file(self, compare_now=False):
        """Choose and remember an external file for COMPARE."""
        selected = filedialog.askopenfilename(
            parent=self.root, title="Select File to Compare")
        if not selected:
            return
        self.compare_filename = str(Path(selected).expanduser().resolve())
        self._add_recent_file(self.compare_filename)
        if hasattr(self, "file_menu") and self.compare_selected_menu_index is not None:
            self.file_menu.entryconfigure(self.compare_selected_menu_index, state=tk.NORMAL)
        if compare_now:
            self.compare_file(self.compare_filename)
            return
        self.status.config(text=f"Compare file selected: {self.compare_filename}")

    def compare_selected_file(self):
        if not self.compare_filename:
            self.status.config(text="COMPARE: select a file to compare first")
            return
        self.compare_file(self.compare_filename)

    def compare_file(self, path):
        """Compare the current buffer with an external text file inline."""
        target = Path(path).expanduser()
        try:
            with target.open("r", encoding="utf-8-sig", newline=None) as stream:
                baseline = stream.read().split("\n")
        except (OSError, UnicodeError) as exc:
            self.status.config(text=f"COMPARE: cannot read {target}: {exc}")
            return
        self.compare_filename = str(target.resolve())
        self._add_recent_file(self.compare_filename)
        if hasattr(self, "file_menu") and self.compare_selected_menu_index is not None:
            self.file_menu.entryconfigure(self.compare_selected_menu_index, state=tk.NORMAL)
        self._compare_lines(baseline, f"file {target}")

    def open_file(self, mode="EDIT", path=None):
        """Open a file in the specified mode."""
        fname = path or filedialog.askopenfilename(parent=self.root)
        if not fname:
            return
        try:
            with open(fname, "r") as f:
                content = f.read()
            self.text.config(state=tk.NORMAL)  # previous file may have been read-only
            self.text.delete("1.0", tk.END)
            self.text.insert("1.0", content)
            self._baseline_lines = self.text.get("1.0", "end-1c").split("\n")
            self._error_lines.clear()
            self.text.edit_reset()
            self.text.edit_modified(False)
            self._dirty = False
            self._text_entry = None
            self.set_labels({})
            self.set_excluded(set())
            self._snapshots.clear()
            self.filename = fname
            self._add_recent_file(fname)
            self.mode = mode
            self.text.config(state=tk.NORMAL if mode == "EDIT" else tk.DISABLED)
            self.refresh_gutter()
            self.text.yview_moveto(0)
            self.cmd_entry.focus_set()
            self.update_status()
            self.status.config(text=f"Opened: {fname} ({mode} mode)")
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open file: {e}")

    def save_file(self):
        """Save the current buffer to disk."""
        if not self.filename:
            return self.save_as()
        try:
            # HX rows are editor display information, not file contents.
            content = "\n".join(
                line for i, line in enumerate(self.text.get("1.0", "end-1c").split("\n"), 1)
                if not line.startswith("=HEX> ") and not self._is_compare_line(i)
            )
            with open(self.filename, "w") as f:
                f.write(content)
            self._add_recent_file(self.filename)
            self._baseline_lines = content.split("\n")
            self._dirty = False
            self.text.edit_modified(False)
            self.status.config(text=f"Saved: {self.filename}")
            return True
        except Exception as e:
            messagebox.showerror("Error", f"Cannot save: {e}")
            return False

    def save_as(self):
        """Save the buffer to a new file."""
        fname = filedialog.asksaveasfilename()
        if fname:
            self.filename = fname
            return self.save_file()
        return False

    def _buffer_records(self):
        """Current data records, omitting editor-only display rows."""
        return [line for i, line in enumerate(
                    self.text.get("1.0", "end-1c").split("\n"), 1)
                if not line.startswith("=HEX> ") and not self._is_compare_line(i)]

    def _insert_external_records(self, records, before_index):
        """Insert records and remap labels/exclusions as one undoable change."""
        content = self.text.get("1.0", "end-1c")
        terminal_newline = content.endswith("\n")
        old_lines = content.split("\n") if content else []
        if terminal_newline and old_lines:
            old_lines.pop()
        labels, excluded = self._get_line_state()
        before_index = max(0, min(before_index, len(old_lines)))
        new_lines = old_lines[:before_index] + list(records) + old_lines[before_index:]
        if terminal_newline and new_lines:
            new_content = "\n".join(new_lines) + "\n"
        else:
            new_content = "\n".join(new_lines)
        offset = len(records)
        new_labels = {name: line + (offset if line - 1 >= before_index else 0)
                      for name, line in labels.items()}
        new_excluded = {line + (offset if line - 1 >= before_index else 0)
                        for line in excluded}
        self._commit_text(new_content, (new_labels, new_excluded))
        self._dirty = True
        self.refresh_gutter(keep=self._get_pending_commands())

    def copy_move_data(self, command, raw):
        """COPY/MOVE an external UTF-8 text file into the current buffer."""
        if self.mode != "EDIT":
            self.status.config(text=f"{command}: only available in EDIT mode")
            return
        tokens = self._tokenize(raw)
        values = [value for value, _quoted in tokens]
        if not values:
            source_name = filedialog.askopenfilename(title=f"{command} from file")
            if not source_name:
                return
            values = [source_name]
        source = Path(values[0]).expanduser()
        destination = None
        index = 1
        if len(values) > 1 and values[1].upper() in ("BEFORE", "AFTER"):
            if len(values) < 3 or not values[2].startswith("."):
                self.status.config(text=f"{command}: use {command} file BEFORE|AFTER .label")
                return
            target_line = self._resolve_target(values[2])
            if target_line is None:
                self.status.config(text=f"{command}: label {values[2]} not found")
                return
            destination = target_line - 1 if values[1].upper() == "BEFORE" else target_line
            index = 3
        content = self.text.get("1.0", "end-1c")
        if destination is None and content:
            self.status.config(text=f"{command}: specify BEFORE or AFTER .label")
            return
        start_line = end_line = None
        if len(values) - index == 2 and all(v.isdigit() for v in values[index:]):
            start_line, end_line = map(int, values[index:])
        elif len(values) != index:
            self.status.config(text=f"{command}: invalid operands")
            return
        try:
            records = source.read_text(encoding="utf-8").splitlines()
            if start_line is not None:
                if start_line < 1 or end_line < start_line or start_line > len(records):
                    self.status.config(text=f"{command}: invalid source line range")
                    return
                records = records[start_line - 1:min(end_line, len(records))]
            if command == "MOVE" and self.filename:
                if source.resolve() == Path(self.filename).resolve():
                    self.status.config(text="MOVE: source is the file being edited")
                    return
            self._insert_external_records(records, destination if destination is not None else 0)
            if command == "MOVE":
                source.unlink()
            self.status.config(text=f"{len(records)} line(s) {command.lower()}d from {source}")
        except (OSError, UnicodeError) as exc:
            self.status.config(text=f"{command}: {exc}")

    def create_replace_data(self, command, raw):
        """CREATE a new text file or REPLACE one with selected buffer records."""
        tokens = self._tokenize(raw)
        values = [value for value, _quoted in tokens]
        if values:
            target = Path(values[0]).expanduser()
            selectors = values[1:]
        else:
            target_name = filedialog.asksaveasfilename(title=f"{command} data as")
            if not target_name:
                return
            target = Path(target_name)
            selectors = []
        records = self.text.get("1.0", "end-1c").split("\n")
        record_lines = list(range(1, len(records) + 1))
        labels = [v for v in selectors if v.startswith(".")]
        if labels:
            if len(labels) != 2 or len(selectors) != 2:
                self.status.config(text=f"{command}: specify two labels (.start .end)")
                return
            first, last = (self._resolve_target(label) for label in labels)
            if first is None or last is None:
                self.status.config(text=f"{command}: label not found")
                return
            first, last = sorted((first, last))
            records = records[first - 1:last]
            record_lines = record_lines[first - 1:last]
        elif selectors:
            if len(selectors) != 2 or not all(v.isdigit() for v in selectors):
                self.status.config(text=f"{command}: use a label range (.start .end)")
                return
            first, last = map(int, selectors)
            if first < 1 or last < first or first > len(records):
                self.status.config(text=f"{command}: invalid line range")
                return
            records = records[first - 1:last]
            record_lines = record_lines[first - 1:last]
        elif self.line_clipboard:
            records = list(self.line_clipboard)
            record_lines = None
        if record_lines is None:
            records = [line for line in records if not line.startswith("=HEX> ")]
        else:
            records = [line for line, line_no in zip(records, record_lines)
                       if not line.startswith("=HEX> ") and not self._is_compare_line(line_no)]
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if command == "CREATE":
                with target.open("x", encoding="utf-8", newline="") as stream:
                    stream.write("\n".join(records))
            else:
                with target.open("w", encoding="utf-8", newline="") as stream:
                    stream.write("\n".join(records))
            self.status.config(text=f"{command}: wrote {len(records)} line(s) to {target}")
        except FileExistsError:
            self.status.config(text=f"CREATE: target already exists: {target}")
        except OSError as exc:
            self.status.config(text=f"{command}: {exc}")

    # ------------------------------------------------------------------
    # Search and Replace
    # ------------------------------------------------------------------
    FIND_DIRECTIONS = ("NEXT", "PREV", "FIRST", "LAST")
    MATCH_MODES = ("CHARS", "WORD", "PREFIX", "SUFFIX")
    PRIMARY_ALIASES = {
        "CAN": "CANCEL", "C": "CHANGE", "CHA": "CHANGE", "CHG": "CHANGE",
        "CRE": "CREATE", "EX": "EXCLUDE", "EXC": "EXCLUDE", "F": "FIND",
        "DEL": "DELETE", "HI": "HILITE", "L": "LOCATE", "LOC": "LOCATE", "X": "EXCLUDE",
        "REC": "RECOVERY", "RECOV": "RECOVERY", "RECOVER": "RECOVERY",
        "RECOVRY": "RECOVERY", "RECVR": "RECOVERY", "RECVRY": "RECOVERY",
        "REP": "REPLACE", "RES": "RESET", "RF": "RFIND", "RCH": "RCHANGE",
        "RETR": "RETRIEVE", "EXIT": "END",
    }

    @staticmethod
    def _decode_search_string(value, quoted=False):
        m = re.fullmatch(r"([CXPT])(['\"])(.*)\2", value, re.IGNORECASE)
        if not m:
            return value, quoted
        kind, _, body = m.groups()
        if kind.upper() == "X":
            try:
                return bytes.fromhex(body).decode("latin1"), True
            except ValueError:
                return "", True
        return body, True

    def _parse_search_operands(self, raw):
        strings, options, nums = [], [], []
        for value, quoted in self._tokenize(raw):
            decoded, is_exact = self._decode_search_string(value, quoted)
            if quoted or decoded != value or value[:2].upper() in ("C'", 'C"', "X'", 'X"', "P'", 'P"', "T'", 'T"'):
                strings.append((decoded, is_exact))
            elif value.isdigit(): nums.append(int(value))
            elif value.upper() in ("ALL", "X", "NX", *self.FIND_DIRECTIONS, *self.MATCH_MODES): options.append(value.upper())
            elif value.startswith("."): options.append(value.upper())
            else: strings.append((value, False))
        cols = (nums[-2], nums[-1]) if len(nums) >= 2 else None
        return strings, options, cols

    def _reveal_found_lines(self, candidates):
        """Show every excluded line containing a match and refresh the gutter."""
        found_lines = {line for line, _column, _size in candidates}
        newly_shown = found_lines & self.get_excluded()
        if newly_shown:
            self.set_excluded(self.get_excluded() - newly_shown)
            self.refresh_gutter(keep=self._get_pending_commands())
        return found_lines

    def find_text(self, term=None, repeat=False):
        """FIND string [NEXT|PREV|FIRST|LAST] [.label1 .label2]

        The string may be quoted ('...' or "...") to search for spaces or for a
        keyword itself. A found excluded line is shown.
        """
        if not term:
            term = simpledialog.askstring("Find", "Search for:")
        if not term:
            return
        self._last_find = term

        # --- Parse operands -------------------------------------------
        operands, options, columns = self._parse_search_operands(term)
        labels = [o for o in options if o.startswith(".")]
        direction = next((o for o in options if o in self.FIND_DIRECTIONS), "NEXT")
        mode = next((o for o in options if o in self.MATCH_MODES), "CHARS")
        search_term = " ".join(v for v, _ in operands)
        exact = any(q for _, q in operands)
        if not search_term:
            self.status.config(text="FIND: no search string")
            return

        range_start, range_end = "1.0", "end-1c"
        if labels:
            if len(labels) != 2:
                self.status.config(text="FIND: a range needs two labels (.a .b)")
                return
            start_line, end_line = (self._resolve_target(lab) for lab in labels)
            if start_line is None or end_line is None:
                self.status.config(text="Label not found")
                return
            start_line, end_line = sorted((start_line, end_line))
            range_start, range_end = f"{start_line}.0", f"{end_line}.end"

        # --- Search ----------------------------------------------------
        excluded = self.get_excluded()
        first_line = int(range_start.split(".")[0])
        # Tk's end-1c is an index expression, not a numeric line index.
        last_line = (int(range_end.split(".")[0]) if "." in range_end
                     else self._text_line_count())
        col_start, col_end = columns or (1, None)
        if col_start < 1 or (col_end is not None and col_end < col_start):
            self.status.config(text="FIND: invalid column range")
            return
        if "X" in options and "NX" in options:
            self.status.config(text="FIND: choose X or NX, not both")
            return
        candidates = []
        for ln in range(first_line, last_line + 1):
            if ("X" in options and ln not in excluded) or ("NX" in options and ln in excluded): continue
            line = self.text.get(f"{ln}.0", f"{ln}.end")
            left, right = col_start - 1, min(len(line), col_end) if col_end else len(line)
            segment = line[left:right]
            hay, needle = (segment, search_term) if exact else (segment.casefold(), search_term.casefold())
            offsets = []
            if mode == "PREFIX": offsets = [0] if hay.startswith(needle) else []
            elif mode == "SUFFIX": offsets = [len(segment)-len(search_term)] if hay.endswith(needle) else []
            else:
                pos = 0
                while needle and (pos := hay.find(needle, pos)) >= 0:
                    end = pos + len(needle)
                    if mode != "WORD" or ((pos == 0 or not hay[pos-1].isalnum()) and (end == len(hay) or not hay[end].isalnum())): offsets.append(pos)
                    pos += max(1, len(needle))
            candidates.extend((ln, left + off, len(search_term)) for off in offsets)
        candidates.sort()
        if "ALL" in options and not repeat:
            self._reveal_found_lines(candidates)
            self.text.tag_remove("found", "1.0", tk.END)
            for ln, col, size in candidates: self.text.tag_add("found", f"{ln}.{col}", f"{ln}.{col+size}")
            if candidates:
                self.text.see(f"{candidates[0][0]}.0")
            self.status.config(text=f"FIND: {len(candidates)} occurrence(s) of '{search_term}'")
            return
        def search(index, stop, backwards=False):
            return self.text.search(search_term, index, stopindex=stop,
                                    backwards=backwards, nocase=not exact, elide=True)

        # Cursor clamped into the range; NEXT skips the current hit
        cursor = self.text.index(tk.INSERT)
        if self.text.compare(cursor, "<", range_start):
            cursor = range_start
        elif self.text.compare(cursor, ">", range_end):
            cursor = range_end
        wrapped = False
        cl, cc = map(int, cursor.split("."))
        if direction == "FIRST": chosen = candidates[0] if candidates else None
        elif direction == "LAST": chosen = candidates[-1] if candidates else None
        elif direction == "PREV": chosen = next((x for x in reversed(candidates) if (x[0], x[1]) < (cl, cc)), candidates[-1] if candidates else None)
        else: chosen = next((x for x in candidates if (x[0], x[1]) > (cl, cc)), candidates[0] if candidates else None)
        start = f"{chosen[0]}.{chosen[1]}" if chosen else None
        wrapped = bool(chosen and ((direction == "PREV" and (chosen[0],chosen[1]) >= (cl,cc)) or (direction == "NEXT" and (chosen[0],chosen[1]) <= (cl,cc))))
        if start:
            line = int(start.split(".")[0])
            excluded = self.get_excluded()
            if line in excluded:
                self.set_excluded(excluded - {line})
                self.refresh_gutter(keep=self._get_pending_commands())
            end = f"{start}+{len(search_term)}c"
            self.text.tag_remove("found", "1.0", tk.END)
            self.text.tag_add("found", start, end)
            self.text.mark_set(tk.INSERT, start)
            self.text.see(start)
            col = int(start.split(".")[1]) + 1
            note = ""
            if wrapped:
                note = " (wrapped to bottom)" if direction == "PREV" else " (wrapped to top)"
            self.status.config(text=f"'{search_term}' found on line {line}, col {col}"
                                    f" ({direction}){note}")
        else:
            self.status.config(text=f"Not found: '{search_term}'")

    def repeat_find(self):
        if not self._last_find:
            self.status.config(text="RFIND: no previous FIND command")
            return
        # ALL is a display-all request for the original FIND; PF5/RFIND must
        # still move to one successive occurrence rather than re-highlight all.
        self.find_text(self._last_find, repeat=True)

    @staticmethod
    def _tokenize(text):
        """Split command operands into (value, quoted) pairs; '...' and "..." are quoted."""
        pattern = r"([CXPT](?:'[^']*'|\"[^\"]*\"))|'([^']*)'|\"([^\"]*)\"|(\S+)"
        result = []
        for typed, single, double, word in re.findall(pattern, text, re.IGNORECASE):
            result.append((typed, False) if typed else ((single or double), True) if not word else (word, False))
        return result

    def change_text(self, old=None, new=None, exact=False, options=(), columns=None):
        """Change one selected occurrence, or every match with the ALL operand."""
        if not old:
            old = simpledialog.askstring("Change", "Find:")
        if new is None:
            new = simpledialog.askstring("Change", "Replace with:")
        if not old or new is None:
            return
        content = self.text.get("1.0", "end-1c")
        lines = content.split("\n")
        excluded = self.get_excluded()
        labels = [o for o in options if o.startswith(".")]
        first, last = 1, len(lines)
        if labels:
            if len(labels) != 2:
                self.status.config(text="CHANGE: a range needs two labels (.a .b)")
                return
            resolved = [self._resolve_target(label) for label in labels]
            if None in resolved:
                self.status.config(text="Label not found")
                return
            first, last = sorted(resolved)
        mode = next((o for o in options if o in self.MATCH_MODES), "CHARS")
        direction = next((o for o in options if o in self.FIND_DIRECTIONS), "NEXT")
        hidden, shown = "X" in options, "NX" in options
        col_start, col_end = columns or (1, None)
        if col_start < 1 or (col_end is not None and col_end < col_start):
            self.status.config(text="CHANGE: invalid column range")
            return
        if hidden and shown:
            self.status.config(text="CHANGE: choose X or NX, not both")
            return
        candidates = []
        flags = 0 if exact else re.IGNORECASE
        matcher = re.compile(re.escape(old), flags)
        for line_no in range(first, last + 1):
            if ((hidden and line_no not in excluded) or (shown and line_no in excluded)
                    or lines[line_no - 1].startswith("=HEX> ")
                    or self._is_compare_line(line_no)):
                continue
            i = line_no - 1
            line = lines[i]
            left = max(0, col_start - 1)
            right = min(len(line), col_end) if col_end else len(line)
            segment = line[left:right]
            for match in matcher.finditer(segment):
                start, end = match.span()
                left_word = start > 0 and segment[start - 1].isalnum()
                right_word = end < len(segment) and segment[end].isalnum()
                if mode == "WORD" and (left_word or right_word):
                    continue
                if mode == "PREFIX" and left_word:
                    continue
                if mode == "SUFFIX" and right_word:
                    continue
                candidates.append((line_no, left + start, end - start))

        candidates.sort()
        if not candidates:
            self._last_change = (old, new, exact, options, columns)
            self.status.config(text=f"CHANGE: '{old}' not found")
            return
        if "ALL" in options:
            chosen = candidates
        else:
            cursor = self.text.index(tk.INSERT)
            cursor_line, cursor_col = map(int, cursor.split("."))
            if direction == "FIRST":
                selected = candidates[0]
            elif direction == "LAST":
                selected = candidates[-1]
            elif direction == "PREV":
                selected = next((m for m in reversed(candidates)
                                 if (m[0], m[1]) < (cursor_line, cursor_col)), candidates[-1])
            else:
                selected = next((m for m in candidates
                                 if (m[0], m[1]) >= (cursor_line, cursor_col)), candidates[0])
            chosen = [selected]

        old_state = self._get_line_state()
        for line_no, col, size in reversed(chosen):
            line = lines[line_no - 1]
            lines[line_no - 1] = line[:col] + new + line[col + size:]
        new_content = "\n".join(lines)
        if new_content != content:
            self._commit_text(new_content, old_state)
            self.refresh_gutter()
        # Put the cursor after the chosen occurrence so PF6 continues forward.
        line_no, col, size = chosen[-1]
        earlier_delta = sum(len(new) - length for ln, c, length in chosen
                            if ln == line_no and c < col)
        final_col = col + earlier_delta + len(new)
        self.text.mark_set(tk.INSERT, f"{line_no}.{final_col}")
        self.text.see(tk.INSERT)
        self._last_change = (old, new, exact, options, columns)
        self.status.config(text=f"Changed {len(chosen)} occurrence(s) of '{old}' ({direction})")

    def repeat_change(self):
        """Repeat the last CHANGE at the next matching occurrence."""
        if not self._last_change:
            self.status.config(text="RCHANGE: no previous CHANGE command")
            return
        old, new, exact, options, columns = self._last_change
        retained = [o for o in options
                    if o not in (*self.FIND_DIRECTIONS, "ALL")]
        self.change_text(old, new, exact=exact,
                         options=tuple(retained) + ("NEXT",), columns=columns)

    # ------------------------------------------------------------------
    # Case Conversion
    # ------------------------------------------------------------------
    def change_case(self, case):
        """Convert entire buffer to upper or lower case (UC/LC)."""
        content = self.text.get("1.0", "end-1c")
        content = content.upper() if case == "upper" else content.lower()
        self._commit_text(content, self._get_line_state())
        self.refresh_gutter()
        self.status.config(text=f"Converted to {'UPPER' if case == 'upper' else 'lower'} case")

    # ------------------------------------------------------------------
    # Clipboard Operations
    # ------------------------------------------------------------------
    def cut_selection(self):
        """Cut selected text to clipboard (CUT command)."""
        try:
            selected = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_line = selected
            self.text.delete(tk.SEL_FIRST, tk.SEL_LAST)
            self.status.config(text="Selection cut")
        except tk.TclError:
            self.status.config(text="No selection to cut")

    def paste_clipboard(self):
        """Paste clipboard content at cursor (PASTE command)."""
        if self.clipboard_line:
            self.text.insert(tk.INSERT, self.clipboard_line)
            self.status.config(text="Clipboard pasted")

    # ------------------------------------------------------------------
    # Display Options
    # ------------------------------------------------------------------
    def toggle_hex(self):
        """Toggle hex display mode (simplified)."""
        self.hex_mode = not self.hex_mode
        if self.hex_mode:
            self.status.config(text="HEX ON - showing character codes (simplified)")
        else:
            self.status.config(text="HEX OFF")
        self.update_status()

    def update_status(self, event=None):
        """Update the status bar with mode, line, column, and file info."""
        pos = self.text.index(tk.INSERT)
        line, col = pos.split(".")
        mode_str = f"{self.mode}"
        if self.hex_mode:
            mode_str += " HEX"
        self.status.config(
            text=f"{mode_str} | Line: {line} Col: {col} | File: {self.filename or 'None'}")

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------
    def show_help(self):
        """Display built-in help."""
        help_text = """ISPF Editor Commands
=====================

PRIMARY COMMANDS (enter at Command ===>):
  SAVE       - Save the current file
  CANCEL/CAN - Discard changes and exit
  FIND/F x [NEXT|PREV|FIRST|LAST|ALL] [CHARS|WORD|PREFIX|SUFFIX]
             [X|NX] [col1 col2] [.a .b]
             - Search by direction or count every hit with ALL. X/NX
               limits search to hidden/shown lines; columns and labels limit scope.
  CHANGE/C/CHA/CHG a b [NEXT|PREV|FIRST|LAST|ALL]
             [CHARS|WORD|PREFIX|SUFFIX]
             [X|NX] [col1 col2] [.a .b]
             - Changes one occurrence (NEXT by default); ALL changes every match.
               PF6/RCHANGE changes the next occurrence using the last CHANGE options.
  Case: F x / C a b ignore upper/lower case.
        F 'x' / C 'a' b are case-sensitive. Quotes ('x' or "x")
        are also needed for spaces or keywords: F 'last one'
  LEFT/RIGHT [n|MAX|PAGE|HALF]
             - Scroll the data n columns left/right (default PAGE,
               MAX/M = first/last column)
  X string      - Exclude the next line containing string from the cursor
  X string ALL  - Exclude every line containing string
  X ALL [.a .b] - Exclude all lines (or all between labels);
             show them again with F/L/S on the - - - row or RESET
  UP/DOWN [n|MAX|PAGE|HALF|CSR]
             - Scroll n lines up/down (default PAGE, MAX/M = top /
               last page, CSR = cursor line to bottom / top).
               An excluded block counts as one line.
  LOCATE/L n - Scroll to line number n
  LOCATE/L .lab - Scroll to label (.ZF/.ZFIRST, .ZL/.ZLAST, .ZCSR too)
  LOCATE category [FIRST|LAST|NEXT|PREV]
             - Find CHANGE, ERROR, EXCLUDED, LABEL, SPECIAL, or COMMAND lines
  COMPARE *  - Insert inline changes since open or last save
  COMPARE file - Compare the current buffer with another text file
  SORT [ .start .end ] [X|NX] [[A|D] start_col end_col ...]
             - Sort full lines or up to five columns; default ascending
  SORT D     - Sort full lines in descending order
  DELETE/DEL ALL [X|NX] [ .start .end ]
             - Delete every selected line (X=excluded, NX=shown)
  DELETE .start .end
             - Delete an inclusive range; line numbers are also accepted
  COPY file BEFORE|AFTER .label [first last]
             - Insert an external text file or its line range
  MOVE file BEFORE|AFTER .label
             - Insert an external text file and remove the source file
  CREATE file [.start .end | first last]
             - Write the buffer or selected line range to a new file
  REPLACE file [.start .end | first last]
             - Write the buffer or selected line range, creating or replacing file
  RESET/RES  - Show excluded lines, clear pending line commands,
               hex info lines and find highlight. Keywords: EXCLUDED COMMAND
               FIND LABEL ALL (LABEL/ALL also remove labels)
  UC / LC    - Convert entire file to UPPER / lower case
  HEX        - Toggle hex display mode
  UNDO [ALL] - Undo one interaction, or all available undo history
  REDO       - Redo the last undone interaction
  CUT/PASTE  - Cut selected text / paste it
  HELP       - Show this help
  IBM aliases: CAN=CANCEL; C/CHA/CHG=CHANGE; CRE=CREATE; DEL=DELETE; EX/EXC/X=EXCLUDE;
               F=FIND; HI=HILITE; L/LOC=LOCATE; REC/RECOV=RECOVERY;
               REP=REPLACE; RES=RESET. COPY, MOVE, COMPARE, SAVE, and other
               commands use their full names unless listed above.
  Repeat aliases: RF=RFIND; RCH=RCHANGE; RETR=RETRIEVE; EXIT=END.

LINE COMMANDS (type DIRECTLY on the line number):
  Click anywhere on a line number (or Tab to it) and type the
  command - it replaces the number and shows in red. Press
  Enter (in the number area or the text area). Several
  commands can be entered before pressing Enter.

  I[n]     - Insert n blank lines after this line
  D[n]     - Delete n lines            DD..DD - delete block
  R[n]     - Repeat line n times       RR..RR - repeat block
  C[n]     - Copy n lines              CC..CC - copy block
  M[n]     - Move n lines              MM..MM - move block
  A[n]     - Paste copied/moved lines AFTER this line (n times)
  B[n]     - Paste copied/moved lines BEFORE this line
  O[n]     - Overlay copied/moved lines on this line (n lines)
  OO..OO   - Overlay copied/moved lines on a destination block
  UC/LC[n] - Upper/lower case          UCC/LCC - block
  )[n] ([n]- Shift right/left n cols   )) / (( - block
  >[n] / <[n] - Data shift right/left (default 2 spaces)
  >>..>> / <<..<< - Data shift a block
  HX[n]    - Show two aligned hex info lines under n lines (cleared by RES)
  TS[n]    - Split at the text cursor, inserting n blank lines (default 1)
  TF[n]    - Flow this paragraph to column n (default 72)
  TE[n]    - Open a text-entry area; type, then press Enter to flow it
  X[n]     - Exclude (hide) n lines    XX..XX - exclude block
  .label   - Set a label (. + 1-5 letters), shown in place of
             the number. Type spaces over it to remove it.
  C or M without a destination keeps the lines for later A/B/O use.

  On an excluded line (- - - ):
  F[n] / L[n] - Show the first / last n lines of the block
  S[n]     - Show n lines
  D, C, M, R, X, UC, LC - act on the whole hidden block

FIND WITH LABELS:
  FIND text .a .b       - Search only between labels .a and .b
  FIND text LAST .a .b  - Last occurrence between the labels
  FIND text ALL         - Highlight and count all matching occurrences
  FIND/F 'a b'          - Quoted strings; C'..', X'..', P'..', T'..' forms
  FIND text WORD X 1 10 - Match whole words on hidden lines, columns 1-10

MODES:
  EDIT   - Full editing (File > Open (Edit))
  BROWSE - Read-only viewing (File > Open (Browse))
  VIEW   - Read-only viewing (File > Open (View))

KEYBOARD:
  Home    - Jump to the command line
  PgUp/F7 - Scroll up 20 lines
  PgDn/F8 - Scroll down 20 lines
            An amount on the command line overrides the 20:
            M + F7 = UP MAX, M + F8 = DOWN MAX (also n, P, H, C)
  F1      - Help                 F3  - End (save prompt if changed)
  F5      - Repeat Find          F6  - Repeat Change
  F10/11  - Scroll left/right one page
  F12     - Retrieve command (set ISPFEditor.PF12_ACTION to CANCEL for Cancel)
  Tab     - Move between line command area and text
  Ctrl+S  - Save
  Ctrl+F  - Find
"""
        existing = getattr(self, "_help_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_set()
            return

        window = tk.Toplevel(self.root)
        self._help_window = window
        window.title("ISPF Editor Help")
        window.geometry("820x650")
        window.minsize(600, 400)
        window.transient(self.root)

        content = tk.Frame(window)
        content.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        help_text_widget = tk.Text(content, wrap=tk.WORD, undo=False,
                                   font=("Courier", 10), padx=8, pady=6,
                                   state=tk.NORMAL)
        help_scrollbar = tk.Scrollbar(content, orient=tk.VERTICAL,
                                      command=help_text_widget.yview)
        help_text_widget.configure(yscrollcommand=help_scrollbar.set)
        help_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        help_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        help_text_widget.insert("1.0", help_text)
        help_text_widget.config(state=tk.DISABLED)
        self.help_text_widget = help_text_widget

        close_button = tk.Button(window, text="Close", command=window.destroy)
        close_button.pack(anchor=tk.E, padx=8, pady=(2, 8))
        window.bind("<Escape>", lambda _event: window.destroy())
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        window.focus_set()


# ----------------------------------------------------------------------
# Main Entry Point
# ----------------------------------------------------------------------
def main():
    root = tk.Tk()
    app = ISPFEditor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
