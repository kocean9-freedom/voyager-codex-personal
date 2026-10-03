#!/usr/bin/env python3
"""Local message stars for the Voyager Codex personal skill."""

import argparse
import contextlib
import fcntl
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def default_data_file():
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_home / "voyager-codex-personal" / "stars.json"


def read_data(path):
    if not path.exists():
        return {"schema_version": 1, "stars": {}, "folders": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid bookmark data: JSON cannot be read") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("stars"), dict):
        raise ValueError("Invalid bookmark data: unsupported schema")
    if "folders" not in data:
        data["folders"] = {}
    if not isinstance(data["folders"], dict):
        raise ValueError("Invalid bookmark data: invalid folders")
    return data


def write_data(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".stars-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


@contextlib.contextmanager
def locked(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def main(argv=None):
    parser = argparse.ArgumentParser(description="Keep Codex message stars in a local JSON file.")
    parser.add_argument("--data-file", type=Path, default=default_data_file())
    subcommands = parser.add_subparsers(dest="command", required=True)

    star = subcommands.add_parser("star", help="Star a message")
    star.add_argument("--thread-id", required=True)
    star.add_argument("--message-id", required=True)
    star.add_argument("--thread-title", default="")
    star.add_argument("--excerpt", default="")
    star.add_argument("--note", default="")

    unstar = subcommands.add_parser("unstar", help="Remove a message star")
    unstar.add_argument("--thread-id", required=True)
    unstar.add_argument("--message-id", required=True)

    listing = subcommands.add_parser("list", help="List message stars")
    listing.add_argument("--thread-id")

    folder_set = subcommands.add_parser("folder-set", help="Assign a task or chat to a local folder")
    folder_set.add_argument("--thread-id", required=True)
    folder_set.add_argument("--kind", required=True, choices=("codex", "chatgpt"))
    folder_set.add_argument("--folder", required=True)
    folder_set.add_argument("--thread-title", default="")

    folder_remove = subcommands.add_parser("folder-remove", help="Remove a local folder assignment")
    folder_remove.add_argument("--thread-id", required=True)

    folder_list = subcommands.add_parser("folder-list", help="List local folder assignments")
    folder_list.add_argument("--folder")

    args = parser.parse_args(argv)
    path = args.data_file.expanduser()
    try:
        if args.command == "list":
            data = read_data(path)
            records = list(data["stars"].values())
            if args.thread_id:
                records = [record for record in records if record.get("thread_id") == args.thread_id]
            records.sort(key=lambda record: (record.get("created_at", ""), record.get("message_id", "")))
            print(json.dumps(records, ensure_ascii=False, indent=2))
            return 0

        if args.command == "folder-list":
            data = read_data(path)
            records = list(data["folders"].values())
            if args.folder:
                records = [record for record in records if record.get("folder") == args.folder]
            records.sort(key=lambda record: (record.get("folder", ""), record.get("thread_id", "")))
            print(json.dumps(records, ensure_ascii=False, indent=2))
            return 0

        if args.command in ("folder-set", "folder-remove"):
            if not args.thread_id.strip():
                raise ValueError("Thread ID must be nonempty")
            if args.command == "folder-set" and not args.folder.strip():
                raise ValueError("Folder name must be nonempty")
            with locked(path):
                data = read_data(path)
                if args.command == "folder-set":
                    data["folders"][args.thread_id] = {
                        "thread_id": args.thread_id,
                        "kind": args.kind,
                        "folder": args.folder.strip(),
                        "thread_title": args.thread_title,
                    }
                else:
                    data["folders"].pop(args.thread_id, None)
                write_data(path, data)
            print("Folder saved" if args.command == "folder-set" else "Folder removed")
            return 0

        if not args.thread_id.strip() or not args.message_id.strip():
            raise ValueError("Thread and message IDs must be nonempty")
        key = f"{args.thread_id}\x1f{args.message_id}"
        with locked(path):
            data = read_data(path)
            if args.command == "star":
                previous = data["stars"].get(key, {})
                data["stars"][key] = {
                    "thread_id": args.thread_id,
                    "message_id": args.message_id,
                    "thread_title": args.thread_title or previous.get("thread_title", ""),
                    "excerpt": args.excerpt[:240] or previous.get("excerpt", ""),
                    "note": args.note or previous.get("note", ""),
                    "created_at": previous.get("created_at") or datetime.now(timezone.utc).isoformat(),
                }
            else:
                data["stars"].pop(key, None)
            write_data(path, data)
        print("Star saved" if args.command == "star" else "Star removed")
        return 0
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
