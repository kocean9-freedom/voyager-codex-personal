import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from timeline_viewer import make_server, normalize_pages, render_html


def example_pages(kind="chatgpt"):
    return [
        {
            "thread": {"id": "thread-1", "title": "普通聊天 <script>", "kind": kind},
            "page": {"order": "newest_first", "hasMore": True},
            "turns": [{"id": "turn-2", "items": [
                {"id": "user-2", "type": "userMessage", "content": [{"type": "text", "text": "第二个问题"}]},
                {"id": "answer-2", "type": "agentMessage", "phase": None, "text": "第二个回答"},
            ]}],
        },
        {
            "thread": {"id": "thread-1", "title": "普通聊天 <script>", "kind": kind},
            "page": {"order": "newest_first", "hasMore": False},
            "turns": [{"id": "turn-1", "items": [
                {"id": "user-1", "type": "userMessage", "content": [{"type": "text", "text": "第一个问题"}]},
                {"id": "answer-1", "type": "agentMessage", "phase": None, "text": "第一个回答"},
                {"id": "progress-1", "type": "agentMessage", "phase": "commentary", "text": "进度"},
            ]}],
        },
    ]


class TimelineViewerTests(unittest.TestCase):
    def test_chat_messages_are_chronological_and_include_unphased_answers(self):
        timeline = normalize_pages(example_pages())
        self.assertEqual([node["id"] for node in timeline["nodes"]], ["user-1", "answer-1", "user-2", "answer-2"])
        self.assertFalse(timeline["incomplete"])

    def test_codex_requires_final_answer(self):
        pages = example_pages("codex")
        pages[1]["turns"][0]["items"][1]["phase"] = "final_answer"
        timeline = normalize_pages(pages)
        self.assertEqual([node["id"] for node in timeline["nodes"]], ["user-1", "answer-1", "user-2"])

    def test_render_does_not_inject_message_html(self):
        timeline = normalize_pages(example_pages())
        html = render_html(timeline, {"stars": [], "folder": ""}, "secret")
        self.assertNotIn("普通聊天 <script>", html)
        self.assertIn("\\u003cscript\\u003e", html)

    def test_http_star_and_folder_persist_in_existing_json(self):
        with tempfile.TemporaryDirectory() as folder:
            data_file = Path(folder) / "stars.json"
            server = make_server(normalize_pages(example_pages()), data_file)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}/{server.token}"
                with urlopen(base + "/") as response:
                    self.assertIn(b"Voyager", response.read())
                for endpoint, payload in (("star", {"message_id": "answer-1", "starred": True}), ("folder", {"folder": "研究"})):
                    request = Request(base + "/" + endpoint, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
                    with urlopen(request) as response:
                        self.assertEqual(response.status, 200)
                with urlopen(base + "/state") as response:
                    state = json.load(response)
                self.assertEqual(state["stars"], ["answer-1"])
                self.assertEqual(state["folder"], "研究")
                saved = json.loads(data_file.read_text(encoding="utf-8"))
                self.assertEqual(len(saved["stars"]), 1)
                self.assertEqual(len(saved["folders"]), 1)
                bad = Request(base + "/star", data=b'{"message_id":"made-up","starred":true}', headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(bad)
                self.assertEqual(caught.exception.code, 400)
                malformed = Request(base + "/star", data=b'{"message_id":[],"starred":true}', headers={"Content-Type": "application/json"})
                with self.assertRaises(HTTPError) as caught:
                    urlopen(malformed)
                self.assertEqual(caught.exception.code, 400)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
