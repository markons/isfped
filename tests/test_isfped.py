"""Regression tests for isfped's editor behaviour (screen, cursor, state).

Run:  python -m unittest discover -s tests -v
"""
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import BASE, MIXED  # noqa: E402
from harness import EditorDriver  # noqa: E402


class EditorTest(unittest.TestCase):
    lines = BASE

    def setUp(self):
        self.d = EditorDriver(self.lines)

    def tearDown(self):
        self.d.close()


class LineCommandParsing(EditorTest):
    def test_count_before_or_after(self):
        self.d.line_cmds({2: "3D"})
        self.assertEqual(self.d.lines, BASE[:1] + BASE[4:])

    def test_count_on_both_sides_is_an_error(self):
        status = self.d.line_cmds({2: "3D3"})
        self.assertIn("Invalid line command", status)
        self.assertEqual(self.d.lines, BASE)
        self.assertEqual(self.d.pending, {2: "3D3"})

    def test_unknown_command_kept_and_marked(self):
        status = self.d.line_cmds({4: "QQ"})
        self.assertIn("line 4", status)
        self.assertEqual(self.d.ed._error_lines, {4})
        self.assertEqual(self.d.pending, {4: "QQ"})

    def test_lowercase_commands(self):
        self.d.line_cmds({2: "dd", 3: "dd"})
        self.assertEqual(self.d.lines, BASE[:1] + BASE[3:])

    def test_typing_overwrites_the_line_number(self):
        self.d.type_line_cmd(3, "D")
        self.assertEqual(self.d.gutter[2], "D     ")
        self.assertEqual(self.d.pending, {3: "D"})

    def test_enter_with_nothing_typed_moves_to_next_field(self):
        self.d.enter(3)
        self.assertEqual(self.d.ed._current_line(self.d.ed.line_numbers), 4)
        self.assertEqual(self.d.lines, BASE)

    def test_ts_tf_te_must_be_alone(self):
        """TS, TF and TE are refused together with other line commands."""
        status = self.d.line_cmds({1: "TF", 3: "D"})
        self.assertIn("by themselves", status)
        self.assertEqual(self.d.lines, BASE)

    def test_cols_not_supported_but_harmless(self):
        status = self.d.line_cmds({2: "COLS"})
        self.assertIn("not supported", status)
        self.assertEqual(self.d.lines, BASE)


class BlockAndPending(EditorTest):
    def test_unmatched_block_stays_pending(self):
        status = self.d.line_cmds({3: "DD"})
        self.assertIn("incomplete", status)
        self.assertEqual(self.d.pending, {3: "DD"})
        self.d.line_cmds({5: "DD"})
        self.assertEqual(self.d.lines, BASE[:2] + BASE[5:])
        self.assertEqual(self.d.pending, {})

    def test_copy_source_waits_for_destination(self):
        status = self.d.line_cmds({2: "C"})
        self.assertIn("pending", status)
        self.assertEqual(self.d.lines, BASE)
        self.d.line_cmds({4: "A"})
        self.assertEqual(self.d.lines, BASE[:4] + [BASE[1]] + BASE[4:])

    def test_two_sources_refused(self):
        status = self.d.line_cmds({2: "C", 3: "M", 5: "A"})
        self.assertIn("Only one", status)
        self.assertEqual(self.d.lines, BASE)

    def test_destination_reuses_last_copy(self):
        self.d.line_cmds({1: "C", 2: "A"})
        self.d.line_cmds({4: "B"})
        self.assertEqual(self.d.lines[3], BASE[0])

    def test_destination_without_any_copy(self):
        status = self.d.line_cmds({4: "A"})
        self.assertIn("nothing copied", status)

    def test_move_over_itself_with_overlay_refused(self):
        status = self.d.line_cmds({2: "MM", 4: "MM", 3: "O"})
        self.assertIn("Cannot move", status)
        self.assertEqual(self.d.lines, BASE)

    def test_conflicting_data_shift_amounts(self):
        status = self.d.line_cmds({2: "<<3", 4: "<<5"})
        self.assertIn("conflicting", status)

    def test_reset_command_keyword_clears_pending(self):
        self.d.line_cmds({2: "CC"})
        self.d.primary("RESET COMMAND")
        self.assertEqual(self.d.pending, {})


class InsertedLines(EditorTest):
    def test_inserted_lines_marked_and_cursor_on_first(self):
        self.d.line_cmds({3: "I2"})
        self.assertEqual(self.d.lines[3:5], ["", ""])
        self.assertEqual(self.d.ed.get_temp_lines(), {4, 5})
        self.assertEqual(self.d.gutter[3], "''''''")
        self.assertEqual(self.d.insert, "4.0")

    def test_untouched_inserted_lines_dropped_on_enter(self):
        self.d.line_cmds({3: "I2"})
        self.d.primary("")
        self.assertEqual(self.d.lines, BASE)

    def test_empty_enter_in_number_area_keeps_inserted_lines(self):
        # Like SPFLite's NewLine: just moves to the next field
        self.d.line_cmds({3: "I2"})
        self.d.enter(1)
        self.assertEqual(self.d.ed.get_temp_lines(), {4, 5})

    def test_attention_key_drops_inserted_lines(self):
        self.d.line_cmds({3: "I2"})
        self.d.ed._attention(SimpleNamespace(widget=self.d.ed.line_numbers))
        self.assertEqual(self.d.lines, BASE)

    def test_typed_inserted_line_kept(self):
        self.d.line_cmds({3: "I2"})
        self.d.type_text(4, "new")
        self.d.primary("")
        self.assertEqual(self.d.lines, BASE[:3] + ["new"] + BASE[3:])
        self.assertEqual(self.d.ed.get_temp_lines(), set())

    def test_enter_on_last_typed_inserted_line_adds_another(self):
        self.d.line_cmds({3: "I"})
        self.d.type_text(4, "new")
        self.d.cursor(4, 3)
        self.d.ed._text_return(SimpleNamespace(widget=self.d.ed.text))
        self.d.root.update()
        self.assertEqual(self.d.lines[3:5], ["new", ""])
        self.assertEqual(self.d.ed.get_temp_lines(), {5})
        self.assertEqual(self.d.insert, "5.0")

    def test_save_drops_untouched_inserted_lines(self):
        self.d.line_cmds({3: "I3"})
        self.d.primary("SAVE")
        self.assertEqual(Path(self.d.ed.filename).read_text().split("\n"), BASE)

    def test_undo_keeps_inserted_lines_for_undo(self):
        self.d.line_cmds({3: "I"})
        self.d.primary("UNDO")
        self.assertEqual(self.d.lines, BASE)


class TextSplitFlowEntry(EditorTest):
    def test_ts_splits_at_cursor(self):
        self.d.cursor(1, 5)
        self.d.line_cmds({1: "TS"})
        self.assertEqual(self.d.lines[:3], ["alpha", "", " one"])

    def test_ts_cursor_elsewhere_splits_at_end(self):
        self.d.cursor(5, 0)
        self.d.line_cmds({1: "TS"})
        self.assertEqual(self.d.lines[:3], ["alpha one", "", ""])

    def test_tf_on_blank_line(self):
        self.d.load(["", "x"])
        status = self.d.line_cmds({1: "TF"})
        self.assertIn("blank", status)

    def test_te_opens_area_and_enter_flows_it(self):
        self.d.line_cmds({1: "TE3"})
        self.assertEqual(self.d.lines[1:4], ["", "", ""])
        self.d.type_text(2, "some words")
        self.d.type_text(3, "more")
        self.d.ed._text_return(SimpleNamespace(widget=self.d.ed.text))
        self.d.root.update()
        self.assertEqual(self.d.lines[:3], ["alpha one", "some words more", "  beta two"])


class Exclude(EditorTest):
    def test_x_shows_one_row_per_block(self):
        self.d.line_cmds({2: "X3"})
        self.assertEqual(self.d.excluded, {2, 3, 4})
        self.assertEqual(self.d.gutter[1], "- - - ")
        self.assertEqual(self.d.ed._visible_rows(), [1, 2, 5, 6, 7, 8, 9, 10])

    def test_s_shows_first_lines(self):
        self.d.primary("X ALL")
        self.d.line_cmds({1: "S2"})
        self.assertEqual(self.d.excluded, set(range(3, 11)))

    def test_f_l_s_only_on_excluded(self):
        status = self.d.line_cmds({2: "F"})
        self.assertIn("only works on excluded", status)

    def test_find_reveals_excluded_line(self):
        self.d.primary("X ALL")
        self.d.primary("F theta")
        self.assertNotIn(8, self.d.excluded)
        self.assertEqual(len(self.d.excluded), 9)

    def test_reset_shows_all_keeps_labels(self):
        self.d.line_cmds({3: ".AA"})
        self.d.primary("X ALL")
        self.d.primary("RESET")
        self.assertEqual(self.d.excluded, set())
        self.assertEqual(self.d.labels, {"AA": 3})

    def test_reset_label_and_unknown_keyword(self):
        self.d.line_cmds({3: ".AA"})
        self.assertIn("unknown keyword", self.d.primary("RESET BOGUS"))
        self.d.primary("RESET LABEL")
        self.assertEqual(self.d.labels, {})

    def test_x_all_label_range(self):
        self.d.line_cmds({3: ".AA", 5: ".BB"})
        self.d.primary("X ALL .AA .BB")
        self.assertEqual(self.d.excluded, {3, 4, 5})

    def test_exclude_next_match_only(self):
        self.d.primary("X eta")
        self.assertEqual(self.d.excluded, {2})


class Labels(EditorTest):
    def test_label_shown_and_follows_line(self):
        self.d.line_cmds({5: ".AA"})
        self.assertEqual(self.d.gutter[4], ".AA   ")
        self.d.line_cmds({1: "D2"})
        self.assertEqual(self.d.labels, {"AA": 3})

    def test_label_moves_to_new_line(self):
        self.d.line_cmds({5: ".AA"})
        self.d.line_cmds({7: ".AA"})
        self.assertEqual(self.d.labels, {"AA": 7})

    def test_blanking_label_removes_it(self):
        self.d.line_cmds({5: ".AA"})
        self.d.blank_line_field(5)
        self.d.enter(5)
        self.assertEqual(self.d.labels, {})

    def test_z_labels_reserved(self):
        self.assertIn("reserved", self.d.line_cmds({2: ".ZAP"}))

    def test_label_too_long(self):
        self.assertIn("Invalid", self.d.line_cmds({2: ".ABCDEF"}))

    def test_deleted_line_drops_label(self):
        self.d.line_cmds({5: ".AA"})
        self.d.line_cmds({5: "D"})
        self.assertEqual(self.d.labels, {})

    def test_locate_label(self):
        self.d.line_cmds({7: ".AA"})
        self.assertIn("line 7", self.d.primary("L .AA"))
        self.assertEqual(self.d.ed._current_line(self.d.ed.line_numbers), 7)

    def test_locate_missing_label(self):
        self.assertIn("not found", self.d.primary("L .NOPE"))

    def test_zfirst_zlast(self):
        self.assertIn("line 10", self.d.primary("L .ZLAST"))
        self.assertIn("line 1", self.d.primary("L .ZF"))


class Find(EditorTest):
    def test_find_moves_cursor_and_highlights(self):
        status = self.d.primary("F eta")
        self.assertIn("line 2", status)
        self.assertEqual(self.d.insert, "2.3")
        self.assertEqual(self.d.found, [("2.3", "2.6")])

    def test_rfind_continues_and_wraps(self):
        self.d.primary("F eta")
        lines = [self.d.insert]
        for _ in range(4):
            self.d.primary("RFIND")
            lines.append(self.d.insert)
        self.assertEqual(lines, ["2.3", "6.1", "7.0", "8.2", "2.3"])
        self.assertIn("wrapped", self.d.status)

    def test_find_first_match_at_top_of_file(self):
        """The first FIND after opening searches from the top, without wrapping."""
        status = self.d.primary("F alpha")
        self.assertIn("line 1", status)
        self.assertNotIn("wrapped", status)

    def test_cursor_at_top_after_open(self):
        """After opening, the text cursor is at the top of the data."""
        self.assertEqual(self.d.insert, "1.0")

    def test_find_prefix_suffix_inside_line(self):
        """FIND PREFIX/SUFFIX match words anywhere in the line."""
        self.d.load(["x abcd yabc z"])
        self.assertIn("1 occurrence", self.d.primary("F ALL abc PREFIX"))
        self.assertIn("1 occurrence", self.d.primary("F ALL abc SUFFIX"))

    def test_find_prefix_suffix_not_whole_word(self):
        """PREFIX/SUFFIX: the start/end of a word, not the whole word (ISPF)."""
        self.d.load(["abc"])
        self.assertIn("Not found", self.d.primary("F abc PREFIX"))

    def test_find_prev_first_last(self):
        self.assertIn("line 8", self.d.primary("F eta LAST"))
        self.assertIn("line 7", self.d.primary("F eta PREV"))
        self.assertIn("line 2", self.d.primary("F eta FIRST"))

    def test_find_all_counts(self):
        self.assertIn("4 occurrence", self.d.primary("F ALL eta"))
        self.assertEqual(len(self.d.found), 4)

    def test_find_word(self):
        self.d.load(["abc abcd xabc", "abc"])
        self.assertIn("2 occurrence", self.d.primary("F ALL abc WORD"))

    def test_find_columns(self):
        self.assertIn("1 occurrence", self.d.primary("F ALL a 1 1"))

    def test_find_quoted_and_exact(self):
        self.d.load(MIXED)
        self.assertIn("1 occurrence", self.d.primary("F ALL C'ONLY'"))
        self.assertIn("2 occurrence", self.d.primary("F ALL only"))
        self.assertIn("1 occurrence", self.d.primary("F ALL 'r o'"))

    def test_find_x_nx(self):
        self.d.line_cmds({1: "XX", 5: "XX"})
        self.assertIn("8 occurrence", self.d.primary("F ALL e NX"))
        self.assertIn("7 occurrence", self.d.primary("F ALL e X"))
        # FIND ALL shows the excluded lines it found
        self.assertEqual(self.d.excluded, set())
        self.assertIn("X or NX", self.d.primary("F ALL e X NX"))

    def test_find_label_range(self):
        self.d.line_cmds({6: ".AA", 8: ".BB"})
        self.assertIn("3 occurrence", self.d.primary("F ALL eta .AA .BB"))

    def test_not_found(self):
        self.assertIn("Not found", self.d.primary("F zzz"))

    def test_find_then_change_next_continues_from_find(self):
        self.d.primary("F theta")
        self.d.primary("C e E")
        self.assertEqual(self.d.lines[7], "thEta eight")

    def test_rfind_without_find(self):
        self.assertIn("no previous FIND", self.d.primary("RFIND"))


class Change(EditorTest):
    def test_change_highlights_and_cursor_after(self):
        self.d.primary("C two TWO")
        self.assertEqual(self.d.found, [("2.7", "2.10")])
        self.assertEqual(self.d.insert, "2.10")

    def test_rchange_continues(self):
        self.d.cursor(1, 0)
        self.d.primary("C e E")
        self.d.primary("RCHANGE")
        self.d.primary("RCHANGE")
        self.assertEqual(self.d.lines[:3], ["alpha onE", "  bEta two", "gamma thrEe"])

    def test_rchange_without_change(self):
        self.assertIn("no previous CHANGE", self.d.primary("RCHANGE"))

    def test_change_undo_in_one_step(self):
        self.d.primary("C ALL e E")
        self.d.primary("UNDO")
        self.assertEqual(self.d.lines, BASE)

    def test_invalid_columns(self):
        self.assertIn("invalid column", self.d.primary("C a b 5 2"))


class UndoRedo(EditorTest):
    def test_undo_restores_labels_and_excluded(self):
        self.d.line_cmds({4: ".AA"})
        self.d.line_cmds({6: "XX", 7: "XX"})
        self.d.line_cmds({1: "D"})
        self.assertEqual(self.d.labels, {"AA": 3})
        self.d.primary("UNDO")
        self.assertEqual(self.d.lines, BASE)
        self.assertEqual(self.d.labels, {"AA": 4})
        self.assertEqual(self.d.excluded, {6, 7})

    def test_redo(self):
        self.d.line_cmds({1: "D"})
        self.d.primary("UNDO")
        self.d.primary("REDO")
        self.assertEqual(self.d.lines, BASE[1:])

    def test_undo_all(self):
        self.d.line_cmds({1: "D"})
        self.d.line_cmds({1: "D"})
        self.d.primary("UNDO ALL")
        self.assertEqual(self.d.lines, BASE)

    def test_nothing_to_undo(self):
        self.assertIn("Nothing to undo", self.d.primary("UNDO"))


class HexAndCompare(EditorTest):
    def test_hx_rows_shown_not_saved(self):
        self.d.line_cmds({1: "HX"})
        self.assertEqual(self.d.lines[1:3], ["=HEX> 667662666", "=HEX> 1C0810FE5"])
        self.assertEqual(self.d.data, BASE)
        self.d.primary("RESET")
        self.assertEqual(self.d.lines, BASE)

    def test_compare_session_marks_changes_not_saved(self):
        self.d.line_cmds({2: "D"})
        self.d.primary("C ALL kappa KAPPA")
        status = self.d.primary("COMPARE *")
        self.assertIn("change row", status)
        self.assertIn(BASE[1], self.d.lines)          # removed line shown again
        self.assertNotIn(BASE[1], self.d.data)        # ... but not data
        self.d.primary("RESET")
        self.assertEqual(self.d.lines, self.d.data)

    def test_compare_file(self):
        other = self.d.tmp / "other.txt"
        other.write_text("\n".join(BASE[:5]))
        status = self.d.primary(f'COMPARE "{other}"')
        self.assertIn("change row", status)
        self.assertEqual(self.d.data, BASE)

    def test_compare_no_changes(self):
        self.assertIn("no changes", self.d.primary("COMPARE *"))

    def test_locate_change_after_edit(self):
        self.d.primary("C ALL kappa KAPPA")
        self.assertIn("line 10", self.d.primary("L CHANGE FIRST"))


class FileCommands(EditorTest):
    def test_file_ending_in_newline_has_no_phantom_line(self):
        """The newline ending the last line does not show as an empty line, so
        SORT cannot move one to the top; it is written back on SAVE."""
        path = self.d.tmp / "nl.txt"
        path.write_text("pear\napple\n")
        self.d.ed.open_file("EDIT", str(path))
        self.assertEqual(self.d.lines, ["pear", "apple"])
        self.d.primary("SORT")
        self.d.primary("SAVE")
        self.assertEqual(path.read_text(), "apple\npear\n")

    def test_file_ending_in_newline_round_trips(self):
        path = self.d.tmp / "nl.txt"
        path.write_bytes(b"one\ntwo\n")
        self.d.ed.open_file("EDIT", str(path))
        self.d.primary("SAVE")
        self.assertEqual(path.read_text(), "one\ntwo\n")

    def test_save_writes_no_trailing_newline(self):
        self.d.line_cmds({1: "D"})
        self.d.primary("SAVE")
        self.assertEqual(Path(self.d.ed.filename).read_text(), "\n".join(BASE[1:]))
        self.assertFalse(self.d.ed._dirty)

    def test_save_trims_trailing_blanks(self):
        self.d.load(["a  ", "", "b c "])
        self.d.primary("SAVE")
        self.assertEqual(Path(self.d.ed.filename).read_text(), "a\n\nb c")
        self.assertEqual(self.d.lines, ["a  ", "", "b c "])   # the screen keeps them

    def test_create_and_replace_label_range(self):
        target = self.d.tmp / "out.txt"
        self.d.line_cmds({2: ".AA", 3: ".BB"})
        self.assertIn("wrote 2", self.d.primary(f'CREATE "{target}" .AA .BB'))
        self.assertEqual(target.read_text(), "\n".join(BASE[1:3]))
        self.assertIn("already exists", self.d.primary(f'CREATE "{target}" .AA .BB'))
        self.d.primary(f'REPLACE "{target}" .AA .AA')
        self.assertEqual(target.read_text(), BASE[1])

    def test_create_from_copied_lines(self):
        target = self.d.tmp / "cc.txt"
        self.d.line_cmds({4: "CC", 5: "CC", 6: "A"})
        self.d.primary(f'CREATE "{target}"')
        self.assertEqual(target.read_text(), "\n".join(BASE[3:5]))

    def test_copy_after_label(self):
        source = self.d.tmp / "in.txt"
        source.write_text("new1\nnew2\n")
        self.d.line_cmds({3: ".AA"})
        self.d.primary(f'COPY "{source}" AFTER .AA')
        self.assertEqual(self.d.lines, BASE[:3] + ["new1", "new2"] + BASE[3:])
        self.assertTrue(source.exists())

    def test_copy_needs_destination(self):
        source = self.d.tmp / "in.txt"
        source.write_text("x")
        self.assertIn("BEFORE or AFTER", self.d.primary(f'COPY "{source}"'))

    def test_move_deletes_source(self):
        source = self.d.tmp / "in.txt"
        source.write_text("a\nb\nc\n")
        self.d.line_cmds({1: ".AA"})
        self.d.primary(f'MOVE "{source}" BEFORE .AA 2 3')
        self.assertEqual(self.d.lines[:3], ["b", "c", BASE[0]])
        self.assertFalse(source.exists())

    def test_browse_refuses_line_commands(self):
        path = self.d.tmp / "ro.txt"
        path.write_text("x\ny")
        self.d.ed.open_file("BROWSE", str(path))
        status = self.d.line_cmds({1: "D"})
        self.assertIn("only available in EDIT", status)
        self.assertEqual(self.d.lines, ["x", "y"])

    def test_end_closes_the_editor(self):
        self.d.primary("END")
        with self.assertRaises(tk.TclError):
            self.d.root.winfo_exists()

    def test_end_resolves_pending_line_commands_first(self):
        self.d.type_line_cmd(2, "DD")
        self.assertIn("Resolve pending", self.d.primary("END"))
        self.assertTrue(self.d.root.winfo_exists())


class DeleteSortPrimary(EditorTest):
    def test_delete_numbers(self):
        self.d.primary("DELETE 2 4")
        self.assertEqual(self.d.lines, BASE[:1] + BASE[4:])

    def test_delete_line_number_pseudo_labels(self):
        self.d.primary("DELETE .3 .5")
        self.assertEqual(self.d.lines, BASE[:2] + BASE[5:])

    def test_pseudo_label_past_end_is_undefined(self):
        self.assertIn("undefined", self.d.primary("UC .2 .15"))
        self.assertEqual(self.d.lines, BASE)

    def test_uc_without_range_changes_nothing(self):
        self.assertIn("pending line range", self.d.primary("UC"))
        self.assertEqual(self.d.lines, BASE)

    def test_uc_range_skips_hex_rows(self):
        self.d.line_cmds({2: "HX"})
        self.d.primary("UC ALL")
        self.assertEqual(self.d.data, [line.upper() for line in BASE])
        self.assertTrue(self.d.lines[2].startswith("=HEX> "))

    def test_count_past_end_keeps_commands(self):
        status = self.d.line_cmds({1: "D", 9: "D5"})
        self.assertIn("past the last line", status)
        self.assertEqual(self.d.lines, BASE)
        self.assertEqual(self.d.pending, {1: "D", 9: "D5"})

    def test_sort_ignores_case_and_keeps_order_of_equals(self):
        self.d.load(["b", "B", "a", "A"])
        self.d.primary("SORT")
        self.assertEqual(self.d.lines, ["a", "A", "b", "B"])

    def test_delete_all_without_x_refused(self):
        self.assertIn("specify", self.d.primary("DELETE ALL"))
        self.assertEqual(self.d.lines, BASE)

    def test_delete_everything_leaves_one_empty_line(self):
        self.d.primary("X ALL")
        self.d.primary("DELETE ALL X")
        self.assertEqual(self.d.lines, [""])

    def test_sort_x_only(self):
        self.d.load(["d", "c", "b", "a"])
        self.d.line_cmds({1: "XX", 2: "XX"})
        self.d.primary("SORT X")
        self.assertEqual(self.d.lines, ["c", "d", "b", "a"])

    def test_sort_already_in_order(self):
        self.d.load(["a", "b"])
        self.assertIn("already in order", self.d.primary("SORT"))

    def test_sort_bad_operands(self):
        self.assertIn("SORT:", self.d.primary("SORT 5"))


class Scrolling(EditorTest):
    lines = [f"line {i}" for i in range(1, 201)]

    def top(self):
        return int(self.d.ed.text.index("@0,0").split(".")[0])

    def test_down_up_numbers(self):
        self.d.primary("DOWN 50")
        self.assertEqual(self.top(), 51)
        self.d.primary("UP 20")
        self.assertEqual(self.top(), 31)

    def test_max(self):
        self.d.primary("DOWN MAX")
        self.assertGreater(self.top(), 150)
        self.d.primary("UP MAX")
        self.assertEqual(self.top(), 1)

    def test_excluded_block_is_one_row(self):
        self.d.line_cmds({2: "X50"})
        self.d.primary("DOWN 2")
        self.assertEqual(self.top(), 52)

    def test_locate_line_number(self):
        self.d.primary("L 120")
        self.assertEqual(self.top(), 120)

    def test_bad_amount(self):
        self.assertIn("amount must be", self.d.primary("DOWN LOTS"))

    def test_right_left(self):
        self.d.load(["x" * 500])
        self.d.primary("RIGHT 100")
        self.assertGreater(self.d.ed._left_column(), 1)
        self.d.primary("LEFT MAX")
        self.assertEqual(self.d.ed._left_column(), 1)


class PrimaryMisc(EditorTest):
    def test_unknown_command(self):
        self.assertIn("Unknown command", self.d.primary("FROB"))

    def test_retrieve(self):
        """A typed RETRIEVE brings back the command before it, not itself."""
        self.d.primary("F eta")
        self.d.primary("RETRIEVE")
        self.assertEqual(self.d.ed.cmd_entry.get(), "F eta")

    def test_primary_enter_also_runs_line_commands(self):
        self.d.type_line_cmd(2, "D")
        self.d.primary("F kappa")
        self.assertEqual(self.d.lines, BASE[:1] + BASE[2:])
        self.assertIn("line 9", self.d.status)

    def test_scroll_field(self):
        self.d.ed.scroll_entry.delete(0, "end")
        self.d.ed.scroll_entry.insert(0, "h")
        self.d.ed._set_scroll_mode()
        self.assertEqual(self.d.ed.scroll_mode, "HALF")


if __name__ == "__main__":
    unittest.main()
