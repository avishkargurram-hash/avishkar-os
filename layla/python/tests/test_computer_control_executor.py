"""Real ComputerControlExecutor tests.

Shell execution and file operations run for REAL against a temporary
workspace directory (harmless commands, isolated filesystem location)
-- these don't touch the visible desktop, so real execution is safe
and appropriate here, unlike GUI control.

GUI actions (mouse/keyboard/clipboard/screenshot) are tested against
an injected FAKE `_gui` -- the real `_RealGUI` implementation is never
invoked (it would hijack this machine's actual cursor/keyboard), but
the real DISPATCH logic (which action calls which method with which
arguments) is fully exercised.
"""

import os
import shutil
import tempfile
import unittest

from avishkar_layla.executors.computer_control_executor import ComputerControlExecutor
from avishkar_layla.executors.errors import PathOutsideWorkspaceError, ShellCommandNotAllowedError, UnknownActionError


class FakeGUI:
    def __init__(self):
        self.calls = []

    def screenshot(self):
        self.calls.append(("screenshot",))
        return "fake-image"

    def move_mouse(self, x, y, *, duration=0.0):
        self.calls.append(("move_mouse", x, y, duration))

    def click(self, *, x=None, y=None, button="left"):
        self.calls.append(("click", x, y, button))

    def type_text(self, text, *, interval=0.0):
        self.calls.append(("type_text", text, interval))

    def hotkey(self, *keys):
        self.calls.append(("hotkey", keys))

    def copy_to_clipboard(self, text):
        self.calls.append(("copy_to_clipboard", text))

    def paste_from_clipboard(self):
        self.calls.append(("paste_from_clipboard",))
        return "clipboard contents"


class ExecutorTestCase(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.mkdtemp(prefix="avishkar-layla-test-")
        self.fake_gui = FakeGUI()
        self.executor = ComputerControlExecutor(
            workspace_root=self.workspace, allowed_shell_commands=("python", "echo"), _gui=self.fake_gui,
        )

    def tearDown(self):
        shutil.rmtree(self.workspace, ignore_errors=True)


class TestShellExecution(ExecutorTestCase):
    def test_real_allowed_command_runs_and_captures_output(self):
        result = self.executor("run_shell", {"command": "python -c \"print('hello from a real subprocess')\""})
        self.assertEqual(result["returncode"], 0)
        self.assertIn("hello from a real subprocess", result["stdout"])

    def test_command_not_in_allowlist_is_refused(self):
        with self.assertRaises(ShellCommandNotAllowedError):
            self.executor("run_shell", {"command": "curl http://example.com"})

    def test_empty_allowlist_refuses_everything(self):
        executor = ComputerControlExecutor(workspace_root=self.workspace, allowed_shell_commands=())
        with self.assertRaises(ShellCommandNotAllowedError):
            executor("run_shell", {"command": "python -c \"pass\""})

    def test_real_nonzero_exit_code_is_reported_not_swallowed(self):
        result = self.executor("run_shell", {"command": "python -c \"import sys; sys.exit(3)\""})
        self.assertEqual(result["returncode"], 3)

    def test_shell_runs_in_the_workspace_root_as_cwd(self):
        with open(os.path.join(self.workspace, "marker.txt"), "w") as f:
            f.write("present")
        result = self.executor("run_shell", {"command": "python -c \"import os; print(os.path.exists('marker.txt'))\""})
        self.assertIn("True", result["stdout"])


class TestFileOperations(ExecutorTestCase):
    def test_write_then_read_real_file(self):
        self.executor("write_file", {"path": "notes.txt", "content": "real content"})
        result = self.executor("read_file", {"path": "notes.txt"})
        self.assertEqual(result["content"], "real content")

    def test_list_dir_reports_real_entries(self):
        self.executor("write_file", {"path": "a.txt", "content": "a"})
        self.executor("write_file", {"path": "b.txt", "content": "b"})
        result = self.executor("list_dir", {"path": "."})
        self.assertEqual(set(result["entries"]), {"a.txt", "b.txt"})

    def test_delete_file_actually_removes_it(self):
        self.executor("write_file", {"path": "gone.txt", "content": "x"})
        self.executor("delete_file", {"path": "gone.txt"})
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "gone.txt")))

    def test_move_file(self):
        self.executor("write_file", {"path": "src.txt", "content": "moved"})
        self.executor("move_file", {"src": "src.txt", "dst": "dst.txt"})
        self.assertFalse(os.path.exists(os.path.join(self.workspace, "src.txt")))
        self.assertEqual(self.executor("read_file", {"path": "dst.txt"})["content"], "moved")

    def test_path_traversal_with_dotdot_is_refused(self):
        with self.assertRaises(PathOutsideWorkspaceError):
            self.executor("read_file", {"path": "../../etc/passwd"})

    def test_absolute_path_outside_workspace_is_refused(self):
        fd, outside = tempfile.mkstemp()
        os.close(fd)
        try:
            with self.assertRaises(PathOutsideWorkspaceError):
                self.executor("read_file", {"path": outside})
        finally:
            os.remove(outside)

    def test_write_creates_nested_directories_within_workspace(self):
        self.executor("write_file", {"path": os.path.join("nested", "deep", "file.txt"), "content": "ok"})
        result = self.executor("read_file", {"path": os.path.join("nested", "deep", "file.txt")})
        self.assertEqual(result["content"], "ok")


class TestGUIDispatch(ExecutorTestCase):
    def test_move_mouse_dispatches_to_gui_with_real_arguments(self):
        self.executor("move_mouse", {"x": 100, "y": 200})
        self.assertEqual(self.fake_gui.calls, [("move_mouse", 100, 200, 0.0)])

    def test_click_dispatches_with_default_button(self):
        self.executor("click", {"x": 5, "y": 10})
        self.assertEqual(self.fake_gui.calls, [("click", 5, 10, "left")])

    def test_type_text_dispatches(self):
        self.executor("type_text", {"text": "hello"})
        self.assertEqual(self.fake_gui.calls, [("type_text", "hello", 0.0)])

    def test_hotkey_dispatches_with_unpacked_keys(self):
        self.executor("hotkey", {"keys": ["ctrl", "c"]})
        self.assertEqual(self.fake_gui.calls, [("hotkey", ("ctrl", "c"))])

    def test_screenshot_returns_whatever_gui_returns(self):
        result = self.executor("screenshot", {})
        self.assertEqual(result["image"], "fake-image")

    def test_clipboard_round_trip_dispatch(self):
        self.executor("copy_to_clipboard", {"text": "copied"})
        result = self.executor("paste_from_clipboard", {})
        self.assertEqual(result["text"], "clipboard contents")
        self.assertIn(("copy_to_clipboard", "copied"), self.fake_gui.calls)

    def test_real_gui_is_never_touched_when_a_fake_is_injected(self):
        """Structural proof: FakeGUI has no way to reach real
        pyautogui/pyperclip, so if this whole test class passes, no
        real hardware action ever occurred.
        """
        self.executor("move_mouse", {"x": 1, "y": 1})
        self.executor("click", {"x": 1, "y": 1})
        self.executor("type_text", {"text": "x"})
        self.assertEqual(len(self.fake_gui.calls), 3)


class TestUnknownAction(ExecutorTestCase):
    def test_unknown_action_raises(self):
        with self.assertRaises(UnknownActionError):
            self.executor("levitate", {})


if __name__ == "__main__":
    unittest.main()
