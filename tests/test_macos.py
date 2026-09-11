from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


if sys.platform != "darwin":
    raise unittest.SkipTest("Native macOS regression tests require PyObjC")
from codex_ui.backends.macos import engine as codex_ui


class ChromeSemanticPressTests(unittest.TestCase):
    def test_web_button_clicks_semantic_frame_once_without_axpress(self):
        rect = codex_ui.Rect(0, 0, 1000, 800)
        target = codex_ui.ResolvedTarget(codex_ui.WindowInfo(1, 10, "Google Chrome", "Demo", rect, 0, 0, True))
        area = codex_ui.AXNode("area", None, 0, "AXWebArea", "", "", "", "", True, rect, ())
        button = codex_ui.AXNode("button", area, 1, "AXButton", "", "Activate demo", "", "", True,
                                  codex_ui.Rect(100, 200, 80, 40), ("AXPress",))
        with mock.patch.object(codex_ui, "traverse_ax", return_value=[area, button]), mock.patch.object(codex_ui, "ax_frame", return_value=button.frame), mock.patch.object(codex_ui, "click_mouse") as click, mock.patch.object(codex_ui.AS, "AXUIElementPerformAction") as action:
            result = codex_ui.press_ax(target, name="Activate demo", role="button", contains=False, occurrence=None)
        click.assert_called_once_with(140, 220)
        action.assert_not_called()
        self.assertEqual(result["activation"], "accessibility_frame_click")


class GeometryTests(unittest.TestCase):
    def test_rect_handles_negative_display_coordinates(self) -> None:
        rect = codex_ui.Rect(-3008, 0, 3008, 1692)
        self.assertTrue(rect.contains(-1, 1692))
        self.assertFalse(rect.contains(1, 1693))
        self.assertEqual(rect.center, (-1504, 846))

    def test_capture_pixel_mapping_respects_retina_scale(self) -> None:
        metadata = {
            "screen_rect_points": {"x": 3008, "y": 137, "width": 391, "height": 248},
            "scale": {"x": 2, "y": 2},
        }
        self.assertEqual(codex_ui.capture_pixel_to_screen(metadata, 272, 223), (3144, 248.5))

    def test_normalize_role_accepts_ax_and_friendly_forms(self) -> None:
        self.assertEqual(codex_ui.normalize_role("AXRadioButton"), "radiobutton")
        self.assertEqual(codex_ui.normalize_role("radio_button"), "radiobutton")
        self.assertEqual(codex_ui.normalize_role("radio-button"), "radiobutton")


class WindowGeometryTests(unittest.TestCase):
    def display(self, rect: codex_ui.Rect) -> codex_ui.DisplayInfo:
        return codex_ui.DisplayInfo(1, 4, rect, int(rect.width), int(rect.height), True)

    def target(self, rect: codex_ui.Rect) -> codex_ui.ResolvedTarget:
        window = codex_ui.WindowInfo(
            1, 10, "App", "Window", rect, 0, 0, True
        )
        return codex_ui.ResolvedTarget(window)

    def test_negative_display_right_half_preset(self) -> None:
        display = self.display(codex_ui.Rect(-3008, 0, 3008, 1692))
        with mock.patch.object(codex_ui, "list_displays", return_value=[display]):
            requested, moved, resized = codex_ui.requested_window_rect(
                codex_ui.Rect(0, 0, 1000, 800),
                preset="right-half",
                display_index=1,
                margin=10,
            )
        self.assertEqual(requested, codex_ui.Rect(-1504, 10, 1494, 1672))
        self.assertTrue(moved)
        self.assertTrue(resized)

    def test_position_only_preserves_size(self) -> None:
        requested, moved, resized = codex_ui.requested_window_rect(
            codex_ui.Rect(100, 200, 900, 700), position=(-100, 50)
        )
        self.assertEqual(requested, codex_ui.Rect(-100, 50, 900, 700))
        self.assertTrue(moved)
        self.assertFalse(resized)

    def test_partially_offscreen_geometry_fails_closed(self) -> None:
        display = self.display(codex_ui.Rect(0, 0, 1000, 1000))
        with mock.patch.object(codex_ui, "list_displays", return_value=[display]):
            with self.assertRaisesRegex(codex_ui.UIControlError, "outside"):
                codex_ui.validate_window_visibility(
                    codex_ui.Rect(900, 900, 200, 200), allow_partial=False
                )

    def test_constrained_geometry_rolls_back_when_not_allowed(self) -> None:
        original = codex_ui.Rect(10, 20, 800, 600)
        requested = codex_ui.Rect(100, 120, 400, 300)
        constrained = codex_ui.Rect(100, 120, 500, 350)
        target = self.target(original)
        with mock.patch.object(codex_ui, "ax_window_for", return_value="element"), mock.patch.object(
            codex_ui, "ax_frame", side_effect=[original, constrained, original]
        ), mock.patch.object(codex_ui, "set_ax_window_rect") as setter, mock.patch.object(
            codex_ui.time, "sleep"
        ):
            with self.assertRaisesRegex(codex_ui.UIControlError, "constrained"):
                codex_ui.apply_window_rect(
                    target,
                    requested,
                    change_position=True,
                    change_size=True,
                    allow_constrained=False,
                )
        self.assertEqual(setter.call_count, 2)
        self.assertEqual(setter.call_args_list[1].args, ("element", original))
        self.assertEqual(
            setter.call_args_list[1].kwargs,
            {"position": True, "size": True},
        )


class SelectionTests(unittest.TestCase):
    def window(self, number: int, app: str, title: str, z: int = 0):
        return codex_ui.WindowInfo(number, 10, app, title, codex_ui.Rect(0, 0, 100, 100), 0, z, True)

    def test_window_filters_combine_app_and_title(self) -> None:
        windows = [
            self.window(1, "Google Chrome", "Pulse"),
            self.window(2, "Google Chrome", "Calendar"),
            self.window(3, "Safari", "Pulse"),
        ]
        matches = codex_ui.filter_windows(windows, app="chrome", title="pulse")
        self.assertEqual([window.window_id for window in matches], [1])

    def test_ambiguous_selection_fails_closed(self) -> None:
        with self.assertRaises(codex_ui.AmbiguousTargetError):
            codex_ui.select_occurrence([1, 2], None, "window")

    def test_explicit_occurrence_is_one_based(self) -> None:
        self.assertEqual(codex_ui.select_occurrence(["a", "b"], 2, "item"), "b")

    def test_default_frontmost_uses_top_z_order_window(self) -> None:
        windows = [self.window(1, "Terminal", "Top", 0), self.window(2, "Terminal", "Other", 1)]
        with mock.patch.object(codex_ui, "list_windows", return_value=windows), mock.patch.object(
            codex_ui, "frontmost_pid", return_value=10
        ):
            target = codex_ui.resolve_target(codex_ui.TargetSpec(frontmost=True))
        self.assertEqual(target.window.window_id, 1)


class ChromeTests(unittest.TestCase):
    def tab(self, window: int, tab: int, url: str) -> codex_ui.ChromeTabInfo:
        return codex_ui.ChromeTabInfo(
            window, tab, 1, "Title", url, codex_ui.Rect(3008, 0, 1000, 800), True, False
        )

    def test_chrome_url_match_is_literal_substring(self) -> None:
        tabs = [self.tab(1, 1, "file:///tmp/one.html"), self.tab(2, 3, "file:///tmp/two.html")]
        selected = codex_ui.select_chrome_tab(tabs, "/tmp/two")
        self.assertEqual((selected.window_index, selected.tab_index), (2, 3))

    def test_active_chrome_match_avoids_full_tab_scan(self) -> None:
        active = [self.tab(1, 1, "file:///Users/me/project/index.html")]
        window = codex_ui.WindowInfo(
            8, 99, "Google Chrome", "Project", active[0].rect, 0, 0, True
        )
        with mock.patch.object(codex_ui, "query_chrome_tabs", return_value=active) as query, mock.patch.object(
            codex_ui, "nearest_window_for_chrome", return_value=window
        ):
            target = codex_ui.resolve_target(codex_ui.TargetSpec(chrome_url="project/index.html"))
        self.assertEqual(target.window.window_id, 8)
        query.assert_called_once_with(active_only=True)

    def test_chrome_activation_uses_stable_window_id_and_verifies_url(self) -> None:
        tab = codex_ui.ChromeTabInfo(
            2,
            3,
            8,
            "Frames",
            "https://example.com/frames/",
            codex_ui.Rect(3008, 0, 1000, 800),
            True,
            False,
            451,
        )
        result = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "windowId": 451,
                    "tabIndex": 3,
                    "title": "Frames",
                    "url": "https://example.com/frames/",
                }
            ),
            stderr="",
        )
        with mock.patch.object(codex_ui.subprocess, "run", return_value=result) as run, mock.patch.object(
            codex_ui.time, "sleep"
        ):
            codex_ui.activate_chrome_tab(tab)
        self.assertEqual(run.call_args.args[0][-3:], ["2", "3", "451"])

    def test_chrome_activation_fails_closed_on_wrong_selected_tab(self) -> None:
        tab = self.tab(2, 3, "https://example.com/frames/")
        result = mock.Mock(
            returncode=0,
            stdout=json.dumps(
                {
                    "windowId": 451,
                    "tabIndex": 8,
                    "title": "Marketplace",
                    "url": "https://example.com/marketplace/",
                }
            ),
            stderr="",
        )
        with mock.patch.object(codex_ui.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(codex_ui.UIControlError, "different tab"):
                codex_ui.activate_chrome_tab(tab)

    def test_chrome_target_refreshes_window_after_activation(self) -> None:
        requested = codex_ui.ChromeTabInfo(
            2,
            3,
            8,
            "Frames",
            "https://example.com/frames/",
            codex_ui.Rect(3008, 0, 1000, 800),
            True,
            False,
            451,
        )
        active = codex_ui.ChromeTabInfo(
            1,
            3,
            3,
            "Frames",
            requested.url,
            requested.rect,
            True,
            False,
            451,
        )
        stale_window = codex_ui.WindowInfo(
            10, 99, "Google Chrome", "Other", requested.rect, 0, 1, True
        )
        actual_window = codex_ui.WindowInfo(
            11, 99, "Google Chrome", "Frames", requested.rect, 0, 0, True
        )
        target = codex_ui.ResolvedTarget(stale_window, requested)
        focused = object()

        def ax_value(_element: object, attribute: str, default: object = None) -> object:
            if attribute == codex_ui.AS.kAXFocusedWindowAttribute:
                return focused
            if attribute == codex_ui.AS.kAXTitleAttribute:
                return "Frames"
            if attribute == "AXDocument":
                return active.url
            return default

        with mock.patch.object(codex_ui, "activate_chrome_tab") as activate, mock.patch.object(
            codex_ui, "query_chrome_tabs", return_value=[active]
        ), mock.patch.object(codex_ui.AS, "AXUIElementCreateApplication", return_value="app"), mock.patch.object(
            codex_ui, "ax_get", side_effect=ax_value
        ), mock.patch.object(
            codex_ui, "ax_frame", return_value=actual_window.rect
        ):
            codex_ui.activate_chrome_target(target)
        activate.assert_called_once_with(requested)
        self.assertEqual(target.chrome_tab, active)
        self.assertIs(target.ax_window, focused)
        self.assertEqual(target.window.title, "Frames")
        self.assertEqual(target.window.rect, actual_window.rect)

    def test_chrome_target_rejects_wrong_focused_document(self) -> None:
        requested = codex_ui.ChromeTabInfo(
            2,
            3,
            8,
            "Frames",
            "https://example.com/frames/",
            codex_ui.Rect(3008, 0, 1000, 800),
            True,
            False,
            451,
        )
        active = codex_ui.replace(requested, active_tab_index=3)
        target = codex_ui.ResolvedTarget(
            codex_ui.WindowInfo(10, 99, "Google Chrome", "Other", requested.rect, 0, 1, True),
            requested,
        )
        focused = object()

        def ax_value(_element: object, attribute: str, default: object = None) -> object:
            if attribute == codex_ui.AS.kAXFocusedWindowAttribute:
                return focused
            if attribute == "AXDocument":
                return "https://example.com/other/"
            return default

        with mock.patch.object(codex_ui, "activate_chrome_tab"), mock.patch.object(
            codex_ui, "query_chrome_tabs", return_value=[active]
        ), mock.patch.object(codex_ui.AS, "AXUIElementCreateApplication", return_value="app"), mock.patch.object(
            codex_ui, "ax_get", side_effect=ax_value
        ), mock.patch.object(codex_ui, "ax_frame", return_value=requested.rect):
            with self.assertRaisesRegex(codex_ui.UIControlError, "different document"):
                codex_ui.activate_chrome_target(target)

    def test_devtools_restore_uses_visible_close_control(self) -> None:
        target = codex_ui.ResolvedTarget(
            codex_ui.WindowInfo(
                10, 99, "Google Chrome", "Frames", codex_ui.Rect(3008, 0, 1000, 800), 0, 1, True
            ),
            self.tab(2, 3, "https://example.com/frames/"),
        )
        location = (
            {
                "screen_rect_points": {"x": 3008, "y": 0, "width": 1000, "height": 800},
                "scale": {"x": 2, "y": 2},
            },
            {"pixel_rect": {"x": 200, "y": 1200, "width": 80, "height": 20}},
        )
        with mock.patch.object(
            codex_ui, "chrome_console_ocr_location", side_effect=[location, None]
        ), mock.patch.object(codex_ui, "click_mouse") as click, mock.patch.object(
            codex_ui.time, "sleep"
        ):
            codex_ui.restore_devtools(
                target, codex_ui.DevToolsState(was_open=False, active_panel=None), False
            )
        click.assert_called_once_with(3990, 605.0)

    def test_console_entries_include_level_and_source(self) -> None:
        log = codex_ui.AXNode(
            element="log",
            parent=None,
            depth=1,
            role="AXGroup",
            subrole="AXApplicationLog",
            title="",
            description="Something failed",
            value="",
            enabled=True,
            frame=None,
            actions=(),
        )
        source = codex_ui.AXNode(
            element="source",
            parent=log,
            depth=2,
            role="AXStaticText",
            subrole="",
            title="",
            description="",
            value="index.html:17",
            enabled=True,
            frame=None,
            actions=(),
        )
        with mock.patch.object(
            codex_ui, "ax_get", return_value=["console-message-wrapper", "console-error-level"]
        ):
            entries, visible, matched = codex_ui.collect_console_entries(
                [log, source], search="failed", level="error", limit=10
            )
        self.assertEqual(visible, 1)
        self.assertEqual(matched, 1)
        self.assertEqual(
            entries,
            [{"level": "error", "message": "Something failed", "source": "index.html:17"}],
        )

    def test_console_ocr_summary_recognizes_empty_levels(self) -> None:
        def word(text: str, x: int, y: int) -> dict[str, object]:
            return {
                "text": text,
                "pixel_rect": {"x": x, "y": y, "width": 30, "height": 18},
            }

        words = [
            word("No", 100, 200),
            word("errors", 140, 202),
            word("No", 100, 240),
            word("warnin...", 140, 241),
            word("No", 100, 280),
            word("messa...", 140, 280),
        ]
        self.assertEqual(
            codex_ui.console_empty_levels_from_ocr_words(words),
            {"error", "warning", "message"},
        )

    def test_devtools_state_remembers_selected_panel(self) -> None:
        panel = codex_ui.AXNode(
            element="panel",
            parent=None,
            depth=1,
            role="AXRadioButton",
            subrole="AXTabButton",
            title="",
            description="Elements",
            value=1,
            enabled=True,
            frame=None,
            actions=(),
        )
        self.assertEqual(
            codex_ui.devtools_state([panel]),
            codex_ui.DevToolsState(was_open=True, active_panel="Elements"),
        )

    def test_console_readiness_allows_keyboard_fallback(self) -> None:
        target = codex_ui.ResolvedTarget(
            codex_ui.WindowInfo(
                1, 10, "Google Chrome", "Project", codex_ui.Rect(0, 0, 100, 100), 0, 0, True
            ),
            self.tab(1, 1, "https://example.com"),
        )
        ocr_location = ({"path": "/tmp/devtools.jpg"}, {"text": "Console"})
        with mock.patch.object(
            codex_ui, "chrome_console_ocr_location", return_value=ocr_location
        ), mock.patch.object(codex_ui, "focus_chrome_console_ocr") as focus, mock.patch.object(
            codex_ui, "press_key_chord"
        ) as press, mock.patch.object(
            codex_ui, "traverse_ax", return_value=[]
        ), mock.patch.object(codex_ui.time, "sleep"):
            self.assertEqual(codex_ui.ensure_chrome_console(target, []), [])
        press.assert_called_once_with("option+cmd+j")
        focus.assert_called_once_with(ocr_location)

    def test_devtools_eval_uses_keyboard_when_prompt_is_not_accessible(self) -> None:
        class Indicator:
            def pump(self, _seconds: float) -> None:
                pass

        class Context:
            monitor = None
            indicator = Indicator()

            def wait_for_user(self) -> None:
                pass

        clipboard = [{"public.utf8-plain-text": b"original"}]
        marker_value = codex_ui.DEVTOOLS_RESULT_PREFIX + json.dumps({"ok": True, "value": 3})
        pasteboard = mock.Mock()
        pasteboard.generalPasteboard.return_value.stringForType_.return_value = marker_value
        with mock.patch.object(codex_ui, "snapshot_clipboard", return_value=clipboard), mock.patch.object(
            codex_ui, "set_clipboard_text"
        ), mock.patch.object(codex_ui, "type_text") as type_value, mock.patch.object(
            codex_ui, "press_key_chord"
        ) as press, mock.patch.object(codex_ui, "restore_clipboard") as restore, mock.patch.object(
            codex_ui, "NSPasteboard", pasteboard
        ):
            self.assertEqual(codex_ui.evaluate_in_devtools([], "1 + 2", Context(), 0.1), 3)
        self.assertIn("1 + 2", type_value.call_args.args[0])
        press.assert_called_once_with("enter")
        restore.assert_called_once_with(clipboard)


class AccessibilityTests(unittest.TestCase):
    def test_static_text_resolves_to_actionable_parent(self) -> None:
        parent = codex_ui.AXNode(
            element="button",
            parent=None,
            depth=1,
            role="AXRadioButton",
            subrole="",
            title="Market 2 modules",
            description="",
            value=0,
            enabled=True,
            frame=codex_ui.Rect(10, 10, 80, 40),
            actions=(codex_ui.AS.kAXPressAction,),
        )
        child = codex_ui.AXNode(
            element="text",
            parent=parent,
            depth=2,
            role="AXStaticText",
            subrole="",
            title="",
            description="",
            value="Market",
            enabled=True,
            frame=codex_ui.Rect(20, 20, 30, 10),
            actions=(),
        )
        matches = codex_ui.find_ax_nodes(
            [parent, child], name="Market", role="radio_button", contains=False, actionable=True
        )
        self.assertEqual(matches, [parent])

    def test_disabled_accessibility_match_is_not_pressed(self) -> None:
        node = codex_ui.AXNode(
            element="button",
            parent=None,
            depth=1,
            role="AXButton",
            subrole="",
            title="Save",
            description="",
            value=None,
            enabled=False,
            frame=None,
            actions=(codex_ui.AS.kAXPressAction,),
        )
        self.assertFalse(node.enabled)


class InterfaceTests(unittest.TestCase):
    def test_parser_accepts_screenshot_pixel_click(self) -> None:
        args = codex_ui.build_parser().parse_args(
            ["click", "--capture", "/tmp/a.jpg", "--pixel", "40", "50"]
        )
        self.assertEqual(args.command, "click")
        self.assertEqual(args.pixel, [40.0, 50.0])

    def test_target_mapping_parses_occurrence(self) -> None:
        target = codex_ui.target_from_mapping(
            {"chrome_url": "file:///tmp/index.html", "occurrence": 2}
        )
        self.assertEqual(target.chrome_url, "file:///tmp/index.html")
        self.assertEqual(target.occurrence, 2)

    def test_error_payload_can_be_serialized(self) -> None:
        payload = {"schema_version": codex_ui.SCHEMA_VERSION, "ok": False, "error": "ambiguous"}
        self.assertEqual(json.loads(json.dumps(payload)), payload)

    def test_parser_accepts_chrome_dom_options(self) -> None:
        args = codex_ui.build_parser().parse_args(
            [
                "chrome-dom",
                "--chrome-url",
                "project/index.html",
                "--selector",
                ".card",
                "--depth",
                "2",
                "--include-html",
            ]
        )
        self.assertEqual(args.command, "chrome-dom")
        self.assertEqual(args.selector, ".card")
        self.assertEqual(args.depth, 2)
        self.assertTrue(args.include_html)

    def test_parser_accepts_combined_window_bounds(self) -> None:
        args = codex_ui.build_parser().parse_args(
            [
                "window-set",
                "--app",
                "Safari",
                "--bounds",
                "20",
                "30",
                "1200",
                "900",
                "--capture-after",
            ]
        )
        self.assertEqual(args.command, "window-set")
        self.assertEqual(args.bounds, [20.0, 30.0, 1200.0, 900.0])
        self.assertTrue(args.capture_after)

    def test_ocr_tsv_treats_bare_quotes_as_text(self) -> None:
        header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        body = (
            "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t96\tCollector\"s\n"
            "5\t1\t1\t1\t1\t2\t45\t20\t40\t10\t95\tConsole\n"
        )
        result = mock.Mock(returncode=0, stdout=header + body, stderr="")
        with mock.patch.object(codex_ui.Path, "exists", return_value=True), mock.patch.object(
            codex_ui.subprocess, "run", return_value=result
        ) as runner:
            rows = codex_ui.run_ocr("/tmp/example.jpg", psm=6)
        self.assertEqual([row["text"] for row in rows], ['Collector"s', "Console"])
        self.assertEqual(runner.call_args.args[0][4], "6")

    def test_ocr_phrase_match_combines_words_on_one_line(self) -> None:
        words = [
            {
                "text": "Save",
                "confidence": 96.0,
                "line_key": "1:2:3:4",
                "word_number": 1,
                "pixel_rect": {"x": 100, "y": 50, "width": 30, "height": 12},
            },
            {
                "text": "image",
                "confidence": 94.0,
                "line_key": "1:2:3:4",
                "word_number": 2,
                "pixel_rect": {"x": 136, "y": 49, "width": 42, "height": 14},
            },
        ]
        matches = codex_ui.ocr_text_matches(words, "Save image", contains=False)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["text"], "Save image")
        self.assertEqual(
            matches[0]["pixel_rect"],
            {"x": 100, "y": 49, "width": 78, "height": 14},
        )


class CollisionTests(unittest.TestCase):
    class Indicator:
        def __init__(self) -> None:
            self.states: list[str] = []

        def update(self, state: str) -> None:
            self.states.append(state)

        def pump(self, seconds: float) -> None:
            time.sleep(seconds)

    def test_recent_user_input_pauses_then_resumes(self) -> None:
        monitor = codex_ui.UserActivityMonitor.__new__(codex_ui.UserActivityMonitor)
        monitor.last_user_input = time.monotonic()
        monitor.pause_count = 0
        indicator = self.Indicator()

        paused = monitor.wait_until_idle(indicator, "controlling", idle_seconds=0.01)

        self.assertTrue(paused)
        self.assertEqual(monitor.pause_count, 1)
        self.assertEqual(indicator.states, ["paused", "controlling"])

    def test_tagged_agent_input_is_not_recorded_as_user_activity(self) -> None:
        monitor = codex_ui.UserActivityMonitor.__new__(codex_ui.UserActivityMonitor)
        monitor.last_user_input = None
        event = object()
        with mock.patch.object(
            codex_ui.Quartz,
            "CGEventGetIntegerValueField",
            return_value=codex_ui.EVENT_MAGIC,
        ):
            returned = monitor._callback(None, 0, event, None)

        self.assertIs(returned, event)
        self.assertIsNone(monitor.last_user_input)


class TextInputTests(unittest.TestCase):
    class Indicator:
        def __init__(self) -> None:
            self.pumps: list[float] = []

        def pump(self, seconds: float) -> None:
            self.pumps.append(seconds)

    class Monitor:
        def __init__(self) -> None:
            self.calls = 0

        def wait_until_idle(self, indicator: object, state: str) -> None:
            del indicator
            self.calls += 1
            if state != "controlling":
                raise AssertionError(f"unexpected state: {state}")

    def test_type_text_pastes_special_characters_and_restores_clipboard(self) -> None:
        text = 'https://x.com/search?q=%22CollectorFlex%22&src=typed_query&f=live'
        monitor = self.Monitor()
        indicator = self.Indicator()
        clipboard = [{"public.utf8-plain-text": b"original"}]

        with mock.patch.object(
            codex_ui, "snapshot_clipboard", return_value=clipboard
        ) as snapshot, mock.patch.object(
            codex_ui, "set_clipboard_text"
        ) as set_text, mock.patch.object(
            codex_ui, "press_key_chord"
        ) as press, mock.patch.object(
            codex_ui, "restore_clipboard"
        ) as restore:
            codex_ui.type_text(text, monitor, indicator)

        snapshot.assert_called_once_with()
        set_text.assert_called_once_with(text)
        press.assert_called_once_with("cmd+v")
        restore.assert_called_once_with(clipboard)
        self.assertEqual(monitor.calls, 1)
        self.assertEqual(indicator.pumps, [0.4])

    def test_type_text_restores_clipboard_when_paste_fails(self) -> None:
        indicator = self.Indicator()
        clipboard = [{"public.utf8-plain-text": b"original"}]
        with mock.patch.object(
            codex_ui, "snapshot_clipboard", return_value=clipboard
        ), mock.patch.object(
            codex_ui, "set_clipboard_text"
        ), mock.patch.object(
            codex_ui, "press_key_chord", side_effect=RuntimeError("paste failed")
        ), mock.patch.object(
            codex_ui, "restore_clipboard"
        ) as restore:
            with self.assertRaisesRegex(RuntimeError, "paste failed"):
                codex_ui.type_text("hello", None, indicator)
        restore.assert_called_once_with(clipboard)

    def test_type_text_empty_value_is_a_noop(self) -> None:
        with mock.patch.object(codex_ui, "snapshot_clipboard") as snapshot:
            codex_ui.type_text("", None, self.Indicator())
        snapshot.assert_not_called()


class PointerRestorationTests(unittest.TestCase):
    class Indicator:
        def finish(self, success: bool = True) -> None:
            del success

    def target(self) -> codex_ui.ResolvedTarget:
        window = codex_ui.WindowInfo(
            1,
            10,
            "Google Chrome",
            "Project",
            codex_ui.Rect(0, 0, 100, 100),
            0,
            0,
            True,
        )
        return codex_ui.ResolvedTarget(window)

    def test_controlling_context_restores_pointer_on_success_and_error(self) -> None:
        for should_fail in (False, True):
            with self.subTest(should_fail=should_fail), tempfile.TemporaryDirectory() as directory:
                state_path = Path(directory) / "state.json"
                with mock.patch.object(
                    codex_ui, "StatusIndicator", return_value=self.Indicator()
                ), mock.patch.object(
                    codex_ui, "mouse_position", return_value=(42.5, 81.25)
                ), mock.patch.object(codex_ui, "move_mouse") as move, mock.patch.object(
                    codex_ui, "RUNTIME_STATE_PATH", state_path
                ):
                    if should_fail:
                        with self.assertRaisesRegex(RuntimeError, "boom"):
                            with codex_ui.CommandContext(self.target(), "controlling"):
                                raise RuntimeError("boom")
                    else:
                        with codex_ui.CommandContext(self.target(), "controlling"):
                            pass
                move.assert_called_once_with(42.5, 81.25, duration=0.05)

    def test_pointer_restoration_failure_fails_the_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            codex_ui, "StatusIndicator", return_value=self.Indicator()
        ), mock.patch.object(
            codex_ui, "mouse_position", return_value=(42.5, 81.25)
        ), mock.patch.object(
            codex_ui, "move_mouse", side_effect=RuntimeError("display disappeared")
        ), mock.patch.object(
            codex_ui, "RUNTIME_STATE_PATH", Path(directory) / "state.json"
        ):
            with self.assertRaisesRegex(
                codex_ui.UIControlError, "Pointer restoration failed"
            ):
                with codex_ui.CommandContext(self.target(), "controlling"):
                    pass


if __name__ == "__main__":
    unittest.main()
