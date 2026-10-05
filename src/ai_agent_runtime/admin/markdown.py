"""Conservative Markdown adapter for the semantic-structured chunk contract.

A section is indivisible prose (rules, exceptions, lists and FAQ stay together).
Tables become self-contained rows with all section prose and ancestor context.
Oversized/ambiguous units fail closed instead of losing qualifications.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

STRATEGY = "semantic-structured-markdown"
VERSION = "1"
MAX_BYTES = 512_000
MAX_CHUNK_CHARS = 6_000
MAX_FILES = 100


class KnowledgeError(ValueError):
    """Only constant public error codes are allowed as messages."""


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def fingerprint(value) -> str:
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


@dataclass(frozen=True)
class Source:
    key: str
    sha256: str
    chunks: list[dict]

    @property
    def chunk_digest(self):
        return fingerprint(self.chunks)


def _cells(line):
    # Escaped pipes/code in tables need explicit editorial normalization.
    if "\\|" in line or "`" in line:
        raise KnowledgeError("UNSUPPORTED_TABLE_SYNTAX")
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def chunk_markdown(text: str) -> list[dict]:
    if not text.strip() or any(ord(c) < 32 and c not in "\n\t\r" for c in text):
        raise KnowledgeError("EMPTY_OR_INVALID_MARKDOWN")
    if text.lstrip().startswith(("---", "+++")):
        raise KnowledgeError("FRONTMATTER_NOT_ALLOWED")
    if re.search(r"(?im)^\s*(organization[_-]?id|tenant[_-]?id)\s*:", text):
        raise KnowledgeError("TENANT_METADATA_NOT_ALLOWED")
    # A restricted, documented subset avoids interpreting code/HTML as knowledge.
    if re.search(r"(?m)^\s*(```|~~~)|<!--|<script\b|!\[", text):
        raise KnowledgeError("UNSUPPORTED_MARKDOWN_STRUCTURE")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    root = {"path": [], "lines": [], "children": []}
    stack = [(0, root)]
    for line in text.splitlines():
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            level, title = len(match[1]), match[2].strip()
            while stack[-1][0] >= level:
                stack.pop()
            parent = stack[-1][1]
            node = {"path": [*parent["path"], title], "lines": [], "children": []}
            parent["children"].append(node)
            stack.append((level, node))
        else:
            if re.match(r"^\s*(===+|---+)\s*$", line):
                raise KnowledgeError("USE_ATX_HEADINGS")
            stack[-1][1]["lines"].append(line)
    result = []

    def emit(path, body, semantic_type, metadata):
        content = "\n".join([" > ".join(path), body]).strip()
        if len(content) > MAX_CHUNK_CHARS:
            raise KnowledgeError("SEMANTIC_UNIT_TOO_LARGE_SPLIT_HEADINGS")
        result.append({"content": content, "section_path": path,
                       "semantic_type": semantic_type, "metadata": metadata})

    def visit(node, inherited):
        lines = node["lines"]
        prose, tables = [], []
        i = 0
        while i < len(lines):
            if i + 1 < len(lines) and "|" in lines[i] and re.fullmatch(
                    r"\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*", lines[i + 1]):
                headers = _cells(lines[i])
                if not all(headers) or len(set(headers)) != len(headers):
                    raise KnowledgeError("INVALID_TABLE_HEADERS")
                rows = []
                i += 2
                while i < len(lines) and lines[i].strip() and "|" in lines[i]:
                    values = _cells(lines[i])
                    if len(values) != len(headers) or not all(values):
                        raise KnowledgeError("INVALID_TABLE_ROW")
                    rows.append(values)
                    i += 1
                if not rows:
                    raise KnowledgeError("EMPTY_TABLE")
                tables.append((headers, rows))
            else:
                if "|" in lines[i]:
                    raise KnowledgeError("AMBIGUOUS_TABLE")
                prose.append(lines[i])
                i += 1
        body = "\n".join(prose).strip()
        context = "\n\n".join(x for x in [inherited, body] if x)
        if tables and node["children"]:
            raise KnowledgeError("TABLE_WITH_CHILDREN_REQUIRES_RESTRUCTURE")
        if tables:
            for table_index, (headers, rows) in enumerate(tables):
                for row_index, values in enumerate(rows):
                    row = "\n".join(f"{h}: {v}" for h, v in zip(headers, values))
                    emit(node["path"], "\n\n".join(x for x in [context, row] if x), "TABLE_ROW",
                         {"tableHeaders": headers, "sourceTable": table_index, "sourceRow": row_index})
        elif body and not node["children"]:
            emit(node["path"], context, "SEMANTIC_ATOMIC_UNIT", {})
        for child in node["children"]:
            visit(child, context)

    visit(root, "")
    if not result:
        raise KnowledgeError("EMPTY_OR_INVALID_MARKDOWN")
    return result


def read_sources(path: Path) -> list[Source]:
    if path.is_symlink():
        raise KnowledgeError("SYMLINK_NOT_ALLOWED")
    if path.is_dir():
        paths = sorted((p for p in path.iterdir() if p.suffix.lower() == ".md"), key=lambda p: p.name)
    else:
        paths = [path]
    if not paths or len(paths) > MAX_FILES:
        raise KnowledgeError("INVALID_SOURCE_COUNT")
    sources = []
    for item in paths:
        if item.is_symlink() or not item.is_file() or item.suffix.lower() != ".md":
            raise KnowledgeError("INVALID_MARKDOWN_FILE")
        if not re.fullmatch(r"[\w][\w .-]{0,159}\.md", item.name, re.UNICODE):
            raise KnowledgeError("INVALID_SOURCE_NAME")
        if item.stat().st_size > MAX_BYTES:
            raise KnowledgeError("SOURCE_TOO_LARGE")
        raw = item.read_bytes()
        if len(raw) > MAX_BYTES:
            raise KnowledgeError("SOURCE_TOO_LARGE")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise KnowledgeError("INVALID_UTF8") from None
        sources.append(Source(item.name, digest(raw), chunk_markdown(text)))
    return sources


def source_from_text(logical_name: str, content: str) -> Source:
    """The HTTP adapter shares the exact parser/identity used by the CLI."""
    if not isinstance(logical_name, str) or not re.fullmatch(r"[\w][\w .-]{0,155}", logical_name, re.UNICODE):
        raise KnowledgeError("INVALID_LOGICAL_NAME")
    if logical_name.endswith(".md") or not isinstance(content, str):
        raise KnowledgeError("INVALID_MARKDOWN_FILE")
    try:
        raw = content.encode("utf-8", "strict")
    except UnicodeError:
        raise KnowledgeError("INVALID_UTF8") from None
    if len(raw) > MAX_BYTES:
        raise KnowledgeError("SOURCE_TOO_LARGE")
    return Source(logical_name + ".md", digest(raw), chunk_markdown(content.removeprefix("\ufeff")))
