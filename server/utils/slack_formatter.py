"""Deterministic Markdown to Slack Block Kit converter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

MAX_SECTION_TEXT = 3000
MAX_HEADER_TEXT = 150
MAX_BLOCKS = 50


class SectionType(Enum):
    HEADER = "header"
    DIVIDER = "divider"
    PARAGRAPH = "paragraph"
    LIST = "list"
    CODE_BLOCK = "code_block"


@dataclass
class ParsedSection:
    type: SectionType
    content: str
    level: int = 1


def markdown_to_slack_blocks(text: str) -> tuple[list[dict], str]:
    if not text or not text.strip():
        return [], ""

    sections = _parse_markdown_sections(text)
    blocks: list[dict] = []
    for section in sections:
        blocks.extend(_section_to_blocks(section))

    blocks = _consolidate_blocks(blocks)
    fallback = _convert_inline_markdown(text)

    return blocks, fallback


def _parse_markdown_sections(text: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            code_lines = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < len(lines):
                code_lines.append(lines[i])
                i += 1
            sections.append(ParsedSection(type=SectionType.CODE_BLOCK, content="\n".join(code_lines)))
            continue

        if line.strip() == "---" or line.strip() == "***" or line.strip() == "___":
            sections.append(ParsedSection(type=SectionType.DIVIDER, content=""))
            i += 1
            continue

        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if header_match:
            level = len(header_match.group(1))
            sections.append(ParsedSection(type=SectionType.HEADER, content=header_match.group(2).strip(), level=level))
            i += 1
            continue

        if re.match(r"^\s*[-*+]\s+", line) or re.match(r"^\s*\d+\.\s+", line):
            list_lines = [line]
            i += 1
            while i < len(lines) and (re.match(r"^\s*[-*+]\s+", lines[i]) or re.match(r"^\s*\d+\.\s+", lines[i])):
                list_lines.append(lines[i])
                i += 1
            sections.append(ParsedSection(type=SectionType.LIST, content="\n".join(list_lines)))
            continue

        if line.strip() == "":
            i += 1
            continue

        para_lines = [line]
        i += 1
        while i < len(lines):
            next_line = lines[i]
            if (
                next_line.strip() == ""
                or next_line.startswith("#")
                or next_line.startswith("```")
                or next_line.strip() in ("---", "***", "___")
                or re.match(r"^\s*[-*+]\s+", next_line)
                or re.match(r"^\s*\d+\.\s+", next_line)
            ):
                break
            para_lines.append(next_line)
            i += 1
        sections.append(ParsedSection(type=SectionType.PARAGRAPH, content="\n".join(para_lines)))

    return sections


def _section_to_blocks(section: ParsedSection) -> list[dict]:
    if section.type == SectionType.DIVIDER:
        return [{"type": "divider"}]

    if section.type == SectionType.HEADER:
        if section.level <= 2:
            header_text = section.content[:MAX_HEADER_TEXT]
            return [{"type": "header", "text": {"type": "plain_text", "text": header_text, "emoji": True}}]
        converted = _convert_inline_markdown(section.content)
        return [_make_section_block(f"*{converted}*")]

    if section.type == SectionType.CODE_BLOCK:
        return _chunk_text_to_sections(section.content)

    if section.type == SectionType.LIST:
        converted_lines = []
        for line in section.content.split("\n"):
            unordered = re.match(r"^(\s*)[-*+]\s+(.+)$", line)
            ordered = re.match(r"^(\s*)\d+\.\s+(.+)$", line)
            if unordered:
                indent = len(unordered.group(1)) // 2
                bullet = "  " * indent + "•"
                converted_lines.append(f"{bullet} {_convert_inline_markdown(unordered.group(2))}")
            elif ordered:
                indent = len(ordered.group(1)) // 2
                prefix = "  " * indent + "•"
                converted_lines.append(f"{prefix} {_convert_inline_markdown(ordered.group(2))}")
            else:
                converted_lines.append(_convert_inline_markdown(line))
        return _chunk_text_to_sections("\n".join(converted_lines))

    if section.type == SectionType.PARAGRAPH:
        converted = _convert_inline_markdown(section.content)
        return _chunk_text_to_sections(converted)

    return []


def _convert_inline_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    text = re.sub(r"__(.+?)__", r"*\1*", text)
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)
    return text


def _chunk_text_to_sections(text: str) -> list[dict]:
    if len(text) <= MAX_SECTION_TEXT:
        return [_make_section_block(text)]

    blocks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""

    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 > MAX_SECTION_TEXT:
            if current_chunk:
                blocks.append(_make_section_block(current_chunk))
                current_chunk = ""
            if len(para) > MAX_SECTION_TEXT:
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for sentence in sentences:
                    if len(sentence) > MAX_SECTION_TEXT:
                        if current_chunk:
                            blocks.append(_make_section_block(current_chunk))
                            current_chunk = ""
                        for j in range(0, len(sentence), MAX_SECTION_TEXT):
                            blocks.append(_make_section_block(sentence[j : j + MAX_SECTION_TEXT]))
                    elif len(current_chunk) + len(sentence) + 1 > MAX_SECTION_TEXT:
                        if current_chunk:
                            blocks.append(_make_section_block(current_chunk))
                        current_chunk = sentence
                    else:
                        current_chunk = f"{current_chunk} {sentence}".strip() if current_chunk else sentence
            else:
                current_chunk = para
        else:
            current_chunk = f"{current_chunk}\n\n{para}".strip() if current_chunk else para

    if current_chunk:
        blocks.append(_make_section_block(current_chunk))

    return blocks


def _make_section_block(text: str) -> dict:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _consolidate_blocks(blocks: list[dict]) -> list[dict]:
    if len(blocks) <= MAX_BLOCKS:
        return blocks

    consolidated: list[dict] = []
    for block in blocks:
        if (
            len(consolidated) >= MAX_BLOCKS - 1
            and block["type"] == "section"
            and consolidated
            and consolidated[-1]["type"] == "section"
        ):
            existing = consolidated[-1]["text"]["text"]
            addition = block["text"]["text"]
            if len(existing) + len(addition) + 2 <= MAX_SECTION_TEXT:
                consolidated[-1]["text"]["text"] = f"{existing}\n\n{addition}"
                continue
        consolidated.append(block)
        if len(consolidated) >= MAX_BLOCKS:
            break

    return consolidated
