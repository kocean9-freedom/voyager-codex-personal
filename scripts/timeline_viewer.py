#!/usr/bin/env python3
"""Serve a local, interactive timeline for a Codex task or ChatGPT chat."""

import argparse
import json
import re
import secrets
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import bookmarks


IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
TEMPLATE = Path(__file__).resolve().parents[1] / "assets" / "timeline.html"
BOOKMARKS_SCRIPT = Path(__file__).with_name("bookmarks.py")


def message_text(item):
    if item.get("type") == "userMessage":
        content = item.get("content", [])
        if isinstance(content, list):
            parts = [part.get("text", "") for part in content if isinstance(part, dict) and isinstance(part.get("text"), str)]
            if parts:
                return "\n".join(parts)
        if isinstance(content, str):
            return content
    return item.get("text", "") if isinstance(item.get("text"), str) else ""


def normalize_pages(pages):
    """Normalize read_thread pages fetched from newest to oldest into one timeline."""
    if not isinstance(pages, list) or not pages:
        raise ValueError("Snapshot must contain at least one read_thread page")
    thread = pages[0].get("thread", {})
    thread_id, kind = thread.get("id"), thread.get("kind")
    if not isinstance(thread_id, str) or not IDENTIFIER.fullmatch(thread_id):
        raise ValueError("Invalid thread ID")
    if kind not in ("codex", "chatgpt"):
        raise ValueError("Unsupported thread kind")
    order = pages[0].get("page", {}).get("order")
    if order not in ("newest_first", "oldest_first"):
        raise ValueError("Unknown page order")
    for page in pages:
        if page.get("thread", {}).get("id") != thread_id or page.get("page", {}).get("order") != order:
            raise ValueError("Snapshot pages belong to different threads or use different orders")
    ordered_pages = reversed(pages) if order == "newest_first" else pages
    nodes, seen = [], set()
    for page in ordered_pages:
        turns = page.get("turns", [])
        ordered_turns = reversed(turns) if order == "newest_first" else turns
        for turn in ordered_turns:
            for item in turn.get("items", []):
                item_type, phase = item.get("type"), item.get("phase")
                if item_type == "userMessage":
                    role = "user"
                elif item_type == "agentMessage" and (phase == "final_answer" or kind == "chatgpt" and phase is None):
                    role = "assistant"
                else:
                    continue
                message_id = item.get("id")
                if not isinstance(message_id, str) or not IDENTIFIER.fullmatch(message_id):
                    continue
                if message_id in seen:
                    continue
                seen.add(message_id)
                text = message_text(item).strip() or "[空消息或附件内容未提供]"
                if "## My request:" in text and item_type == "userMessage":
                    text = text.split("## My request:", 1)[1].strip() or text
                nodes.append({"id": message_id, "role": role, "text": text, "excerpt": " ".join(text.split())[:180]})
    return {
        "thread_id": thread_id,
        "kind": kind,
        "title": str(thread.get("title") or "未命名会话"),
        "nodes": nodes,
        "incomplete": bool(pages[-1].get("page", {}).get("hasMore")),
    }


def state_for(timeline, data_file):
    data = bookmarks.read_data(data_file)
    thread_id = timeline["thread_id"]
    return {
        "stars": sorted(record["message_id"] for record in data["stars"].values() if isinstance(record, dict) and record.get("thread_id") == thread_id and isinstance(record.get("message_id"), str)),
        "folder": data["folders"].get(thread_id, {}).get("folder", ""),
    }


def render_html(timeline, state, token):
    payload = json.dumps({"timeline": timeline, "state": state, "token": token}, ensure_ascii=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return TEMPLATE.read_text(encoding="utf-8").replace("__VOYAGER_DATA__", payload)


class ViewerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_payload(self, status, body, content_type="application/json; charset=utf-8"):
        body = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def route(self):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            return None
        parts = urlsplit(self.path).path.strip("/").split("/")
        if not parts or parts[0] != self.server.token:
            return None
        return parts[1] if len(parts) == 2 else "" if len(parts) == 1 else None

    def do_GET(self):
        route = self.route()
        if route is None:
            self.send_error(404)
        elif route == "":
            html = render_html(self.server.timeline, state_for(self.server.timeline, self.server.data_file), self.server.token)
            self.send_payload(200, html, "text/html; charset=utf-8")
        elif route == "state":
            self.send_payload(200, json.dumps(state_for(self.server.timeline, self.server.data_file), ensure_ascii=False))
        else:
            self.send_error(404)

    def do_POST(self):
        route = self.route()
        if route not in ("star", "folder"):
            self.send_error(404)
            return
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Origin") not in (None, expected_origin) or self.headers.get_content_type() != "application/json":
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4096:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("Invalid request")
            thread_id = self.server.timeline["thread_id"]
            command = [sys.executable, str(BOOKMARKS_SCRIPT), "--data-file", str(self.server.data_file)]
            if route == "star":
                message_id, starred = payload.get("message_id"), payload.get("starred")
                nodes = {node["id"]: node for node in self.server.timeline["nodes"]}
                if not isinstance(message_id, str) or message_id not in nodes or not isinstance(starred, bool):
                    raise ValueError("Unknown message")
                command += ["star" if starred else "unstar", "--thread-id", thread_id, "--message-id", message_id]
                if starred:
                    command += ["--thread-title", self.server.timeline["title"], "--excerpt", nodes[message_id]["excerpt"]]
            else:
                folder = payload.get("folder")
                if not isinstance(folder, str) or len(folder) > 120 or any(ord(ch) < 32 for ch in folder):
                    raise ValueError("Invalid folder name")
                folder = folder.strip()
                if folder:
                    command += ["folder-set", "--thread-id", thread_id, "--kind", self.server.timeline["kind"], "--folder", folder, "--thread-title", self.server.timeline["title"]]
                else:
                    command += ["folder-remove", "--thread-id", thread_id]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise ValueError(result.stderr.strip() or "Could not update local data")
            self.send_payload(200, json.dumps(state_for(self.server.timeline, self.server.data_file), ensure_ascii=False))
        except (ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            self.send_payload(400, json.dumps({"error": str(exc)}, ensure_ascii=False))


def make_server(timeline, data_file):
    server = ThreadingHTTPServer(("127.0.0.1", 0), ViewerHandler)
    server.timeline = timeline
    server.data_file = Path(data_file).expanduser()
    server.token = secrets.token_urlsafe(24)
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open a local Voyager timeline from read_thread pages")
    parser.add_argument("--snapshot", type=Path, required=True, help="JSON array of read_thread pages, newest page first")
    parser.add_argument("--data-file", type=Path, default=bookmarks.default_data_file())
    args = parser.parse_args(argv)
    try:
        source = json.loads(args.snapshot.read_text(encoding="utf-8"))
        timeline = normalize_pages(source["pages"] if isinstance(source, dict) else source)
        server = make_server(timeline, args.data_file)
        print(json.dumps({"url": f"http://127.0.0.1:{server.server_port}/{server.token}/", "thread_id": timeline["thread_id"], "nodes": len(timeline["nodes"]), "incomplete": timeline["incomplete"]}), flush=True)
        server.serve_forever()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
