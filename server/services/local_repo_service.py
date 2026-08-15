from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from server.services.repo_analysis_service import SKIP_DIRS, SKIP_EXTENSIONS
from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

MAX_FILE_SIZE = 100 * 1024  # 100KB
MAX_TREE_ENTRIES = 10_000
MAX_SEARCH_RESULTS = 50

EXTENSION_TO_LANGUAGE = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C",
    ".hpp": "C++",
    ".swift": "Swift",
    ".scala": "Scala",
    ".r": "R",
    ".R": "R",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".vue": "Vue",
    ".svelte": "Svelte",
    ".dart": "Dart",
    ".lua": "Lua",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".xml": "XML",
    ".md": "Markdown",
    ".proto": "Protocol Buffers",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".zig": "Zig",
    ".nim": "Nim",
}


def _validate_path(base_path: str, relative_path: str) -> str:
    full = os.path.realpath(os.path.join(base_path, relative_path))
    if not full.startswith(os.path.realpath(base_path)):
        raise ValueError("Path traversal detected")
    return full


def _should_skip_dir(name: str) -> bool:
    return f"{name}/" in SKIP_DIRS


def _should_skip_file(name: str) -> bool:
    for ext in SKIP_EXTENSIONS:
        if name.endswith(ext):
            return True
    return False


PERMISSION_ERROR_MSG = (
    "Byaan cannot access this folder. Please grant file access in "
    "System Settings > Privacy & Security > Files and Folders > Byaan, then retry."
)


def _walk_directory(base_path: str) -> list[dict]:
    entries: list[dict] = []
    base = os.path.realpath(base_path)

    try:
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if not _should_skip_dir(d) and not d.startswith(".")]

            for f in files:
                if _should_skip_file(f):
                    continue
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, base)
                entries.append({"path": rel_path, "type": "blob"})
                if len(entries) >= MAX_TREE_ENTRIES:
                    return entries
    except PermissionError:
        raise PermissionError(PERMISSION_ERROR_MSG)

    return entries


async def get_local_file_tree(base_path: str) -> list[dict]:
    return await asyncio.to_thread(_walk_directory, base_path)


async def get_local_file_content(base_path: str, relative_path: str) -> str | None:
    try:
        full_path = _validate_path(base_path, relative_path)
    except ValueError:
        return None

    if not os.path.isfile(full_path):
        return None

    if os.path.getsize(full_path) > MAX_FILE_SIZE:
        return None

    def _read():
        try:
            with open(full_path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except PermissionError:
            raise PermissionError(PERMISSION_ERROR_MSG)
        except (OSError, UnicodeDecodeError):
            return None

    return await asyncio.to_thread(_read)


def detect_local_languages(file_tree: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in file_tree:
        if entry.get("type") != "blob":
            continue
        ext = Path(entry["path"]).suffix.lower()
        lang = EXTENSION_TO_LANGUAGE.get(ext)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def search_local_files(file_tree: list[dict], query: str) -> list[str]:
    query_lower = query.lower()
    results = []
    for entry in file_tree:
        if entry.get("type") != "blob":
            continue
        if query_lower in entry["path"].lower():
            results.append(entry["path"])
            if len(results) >= MAX_SEARCH_RESULTS:
                break
    return results


def _grep_files(base_path: str, pattern: str, file_extensions: list[str] | None, max_results: int) -> list[dict]:
    base = os.path.realpath(base_path)
    results: list[dict] = []

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error:
        return []

    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if not _should_skip_dir(d) and not d.startswith(".")]

        for f in files:
            if _should_skip_file(f):
                continue
            if file_extensions:
                ext = os.path.splitext(f)[1].lower()
                if ext not in file_extensions:
                    continue

            full_path = os.path.join(root, f)
            if os.path.getsize(full_path) > MAX_FILE_SIZE:
                continue

            try:
                with open(full_path, encoding="utf-8", errors="replace") as fh:
                    for line_num, line in enumerate(fh, 1):
                        if regex.search(line):
                            rel_path = os.path.relpath(full_path, base)
                            results.append({"path": rel_path, "line": line_num, "content": line.rstrip()[:200]})
                            if len(results) >= max_results:
                                return results
            except PermissionError:
                raise PermissionError(PERMISSION_ERROR_MSG)
            except (OSError, UnicodeDecodeError):
                continue

    return results


async def grep_local_files(
    base_path: str, pattern: str, file_extensions: list[str] | None = None, max_results: int = 50
) -> list[dict]:
    return await asyncio.to_thread(_grep_files, base_path, pattern, file_extensions, max_results)


async def list_local_directory(base_path: str, relative_dir_path: str = "") -> list[dict]:
    try:
        full_path = _validate_path(base_path, relative_dir_path) if relative_dir_path else os.path.realpath(base_path)
    except ValueError:
        return []

    if not os.path.isdir(full_path):
        return []

    def _list():
        entries = []
        try:
            for entry in os.scandir(full_path):
                if entry.name.startswith("."):
                    continue
                if entry.is_dir() and _should_skip_dir(entry.name):
                    continue
                item = {"name": entry.name, "type": "dir" if entry.is_dir() else "file"}
                if entry.is_file():
                    try:
                        item["size"] = entry.stat().st_size
                    except OSError:
                        item["size"] = 0
                entries.append(item)
        except PermissionError:
            raise PermissionError(PERMISSION_ERROR_MSG)
        except OSError:
            pass
        return sorted(entries, key=lambda x: (x["type"] == "file", x["name"]))

    return await asyncio.to_thread(_list)
