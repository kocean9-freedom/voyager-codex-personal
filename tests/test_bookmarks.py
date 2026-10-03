import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "bookmarks.py"


class BookmarkCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.data_file = Path(self.temp.name) / "stars.json"

    def run_cli(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--data-file", str(self.data_file), *args],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, expected, result.stderr)
        return result.stdout

    def test_star_is_persistent_and_idempotent(self):
        self.run_cli("star", "--thread-id", "thread-a", "--message-id", "msg-1", "--thread-title", "研究任务", "--excerpt", "关键答案")
        self.run_cli("star", "--thread-id", "thread-a", "--message-id", "msg-1", "--thread-title", "研究任务", "--excerpt", "关键答案")
        records = json.loads(self.run_cli("list", "--thread-id", "thread-a"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["message_id"], "msg-1")
        self.assertEqual(records[0]["excerpt"], "关键答案")

    def test_unstar_only_removes_selected_message(self):
        for message_id in ("msg-1", "msg-2"):
            self.run_cli("star", "--thread-id", "thread-a", "--message-id", message_id)
        self.run_cli("unstar", "--thread-id", "thread-a", "--message-id", "msg-1")
        records = json.loads(self.run_cli("list"))
        self.assertEqual([record["message_id"] for record in records], ["msg-2"])

    def test_invalid_existing_data_is_not_overwritten(self):
        self.data_file.write_text("broken", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--data-file", str(self.data_file), "star", "--thread-id", "thread-a", "--message-id", "msg-1"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Invalid bookmark data", result.stderr)
        self.assertEqual(self.data_file.read_text(encoding="utf-8"), "broken")

    def test_local_folder_can_contain_work_and_chat(self):
        self.run_cli("folder-set", "--thread-id", "work-1", "--kind", "codex", "--folder", "研究")
        self.run_cli("folder-set", "--thread-id", "chat-1", "--kind", "chatgpt", "--folder", "研究")
        records = json.loads(self.run_cli("folder-list", "--folder", "研究"))
        self.assertEqual({(item["thread_id"], item["kind"]) for item in records}, {("work-1", "codex"), ("chat-1", "chatgpt")})

    def test_moving_local_folder_preserves_message_stars(self):
        self.run_cli("star", "--thread-id", "chat-1", "--message-id", "msg-1")
        self.run_cli("folder-set", "--thread-id", "chat-1", "--kind", "chatgpt", "--folder", "资料")
        self.run_cli("folder-set", "--thread-id", "chat-1", "--kind", "chatgpt", "--folder", "研究")
        records = json.loads(self.run_cli("folder-list"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["folder"], "研究")
        self.assertEqual(len(json.loads(self.run_cli("list", "--thread-id", "chat-1"))), 1)
        self.run_cli("folder-remove", "--thread-id", "chat-1")
        self.assertEqual(json.loads(self.run_cli("folder-list")), [])


if __name__ == "__main__":
    unittest.main()
