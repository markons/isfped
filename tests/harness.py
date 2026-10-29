"""Drive an ISPFEditor the way a user does: type into the line command area,
type on the command line, press Enter.

The Tk window is created fully transparent, so tests run without anything
showing on screen; dialogs are replaced by fakes so nothing blocks.
"""
import sys
import tempfile
import tkinter as tk
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import isfped  # noqa: E402


class EditorDriver:
    def __init__(self, lines=("",)):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._patches = [
            mock.patch.object(isfped.messagebox, "askyesno", return_value=True),
            mock.patch.object(isfped.messagebox, "askyesnocancel", return_value=False),
            mock.patch.object(isfped.messagebox, "showerror"),
            mock.patch.object(isfped.simpledialog, "askstring", return_value=None),
            mock.patch.object(isfped.filedialog, "askopenfilename", return_value=""),
            mock.patch.object(isfped.filedialog, "asksaveasfilename", return_value=""),
            # END/CANCEL must not close the console running the tests
            mock.patch.object(isfped.ISPFEditor, "_close_command_window"),
        ]
        for p in self._patches:
            p.start()
        self.root = tk.Tk()
        self.root.attributes("-alpha", 0.0)
        # Keep the recent-files list out of the repository
        with mock.patch.object(isfped.Path, "with_name",
                               return_value=self.tmp / "recent.json"):
            self.ed = isfped.ISPFEditor(self.root)
        self.root.update()
        self.load(lines)

    def close(self):
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()

    # --- set up ----------------------------------------------------------
    def load(self, lines, name="data.txt"):
        """Open a file with these lines, as `python isfped.py file` would."""
        path = self.tmp / name
        path.write_text("\n".join(lines), encoding="utf-8")
        self.ed.open_file("EDIT", str(path))
        self.root.update()
        return path

    # --- user actions ----------------------------------------------------
    def type_line_cmd(self, line, cmd):
        """Type cmd into the line command field of a (visible) line."""
        g = self.ed.line_numbers
        g.focus_set()
        g.mark_set(tk.INSERT, f"{self.ed._row_of(line)}.0")
        for ch in cmd:
            event = SimpleNamespace(char=ch, widget=g, keysym=ch)
            self.ed._gutter_overtype(event)

    def blank_line_field(self, line):
        """Space over a field (removes a label, like erasing it in ISPF)."""
        g = self.ed.line_numbers
        g.delete(f"{line}.0", f"{line}.end")
        g.insert(f"{line}.0", " " * isfped.FIELD_WIDTH)

    def enter(self, line=None):
        """Press Enter in the line command area (on `line`, default: where it is)."""
        g = self.ed.line_numbers
        if line is not None:
            g.mark_set(tk.INSERT, f"{line}.0")
        result = self.ed.process_line_command(SimpleNamespace(widget=g))
        self.root.update()
        return result

    def line_cmds(self, commands, at=None):
        """Type several line commands {line: cmd}, then press Enter once."""
        for line, cmd in commands.items():
            self.type_line_cmd(line, cmd)
        self.enter(at if at is not None else max(commands))
        return self.status

    def primary(self, command):
        """Type a primary command on the command line and press Enter."""
        self.ed.cmd_entry.delete(0, tk.END)
        self.ed.cmd_entry.insert(0, command)
        self.ed.process_primary_command(SimpleNamespace(widget=self.ed.cmd_entry))
        try:
            self.root.update()
        except tk.TclError:     # END / CANCEL closed the editor
            return None
        return self.status

    def cursor(self, line, col=0):
        """Put the text cursor at a 1-based line, 0-based column."""
        self.ed.text.mark_set(tk.INSERT, f"{line}.{col}")

    def type_text(self, line, text, col=0):
        """Type into the data area (overwrites nothing - Tk inserts)."""
        self.ed.text.insert(f"{line}.{col}", text)
        self.ed._on_text_modified()
        self.root.update()

    # --- inspection ------------------------------------------------------
    @property
    def lines(self):
        return self.ed.text.get("1.0", "end-1c").split("\n")

    @property
    def data(self):
        """Lines as SAVE writes them (no HX/COMPARE display rows)."""
        return self.ed._buffer_records()

    @property
    def status(self):
        try:
            return self.ed.status.cget("text")
        except tk.TclError:     # END / CANCEL closed the editor
            return None

    @property
    def excluded(self):
        return self.ed.get_excluded()

    @property
    def labels(self):
        return self.ed.get_labels()

    @property
    def pending(self):
        return self.ed._get_pending_commands()

    @property
    def gutter(self):
        return self.ed.line_numbers.get("1.0", "end-1c").split("\n")

    @property
    def found(self):
        r = self.ed.text.tag_ranges("found")
        return [(str(a), str(b)) for a, b in zip(r[::2], r[1::2])]

    @property
    def insert(self):
        return self.ed.text.index(tk.INSERT)

    def saved(self):
        self.ed.save_file()
        return Path(self.ed.filename).read_text().split("\n")


def run_case(lines, steps):
    """Run a scenario from cases.py; return (saved lines, status after each step)."""
    d = EditorDriver(lines)
    try:
        statuses = []
        for kind, value in steps:
            if kind == "P":
                statuses.append(d.primary(value))
            else:
                statuses.append(d.line_cmds(value))
        # SAVE on the command line, as the SPFLite macro does
        d.primary("SAVE")
        return Path(d.ed.filename).read_text().split("\n"), statuses
    finally:
        d.close()
