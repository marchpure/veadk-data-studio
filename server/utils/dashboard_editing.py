import re
from dataclasses import dataclass
from difflib import SequenceMatcher


class DashboardEditError(Exception):
    """Base exception for dashboard editing failures."""


class DashboardSearchReplaceError(DashboardEditError):
    """Raised when a SEARCH/REPLACE block cannot be applied."""


class DashboardPatchError(DashboardEditError):
    """Raised when a patch cannot be parsed or applied."""


@dataclass
class SearchReplaceBlock:
    search: str
    replace: str


@dataclass
class PatchChunk:
    old_lines: list[str]
    new_lines: list[str]


SEARCH_REPLACE_PATTERN = re.compile(
    r"<<<<<<<\s*SEARCH\s*?\n(?P<search>.*?)\n=======\s*\n(?P<replace>.*?)\n>>>>>>>"
    r"\s*REPLACE",
    re.DOTALL,
)

PATCH_BEGIN = "*** Begin Patch"
PATCH_END = "*** End Patch"


def parse_search_replace_blocks(diff_content: str) -> list[SearchReplaceBlock]:
    matches = list(SEARCH_REPLACE_PATTERN.finditer(diff_content))
    blocks: list[SearchReplaceBlock] = []

    for match in matches:
        search = (match.group("search") or "").strip("\r\n")
        replace = (match.group("replace") or "").strip("\r\n")
        blocks.append(SearchReplaceBlock(search=search, replace=replace))

    return blocks


def _split_lines_preserve(content: str) -> list[str]:
    return content.splitlines()


def _check_for_marker_lines(lines: list[str], block_label: str) -> None:
    for line in lines:
        stripped = line.strip()
        if stripped in {"<<<<<<< SEARCH", "=======", ">>>>>>> REPLACE"}:
            raise DashboardSearchReplaceError(
                f"{block_label} block still contains diff marker line '{stripped}'. "
                "Only include clean HTML/JSX content between the markers."
            )


def _join_lines_preserve(lines: list[str], line_ending: str, original: str) -> str:
    text = line_ending.join(lines)
    if original.endswith(line_ending):
        text += line_ending
    return text


def _line_matchers():
    return (
        lambda a, b: a == b,
        lambda a, b: a.strip() == b.strip(),
        lambda a, b: a.lstrip() == b.lstrip(),
    )


def _find_block_start(lines: list[str], block_lines: list[str]) -> int:
    for matcher in _line_matchers():
        candidates: list[int] = []
        for i in range(len(lines) - len(block_lines) + 1):
            if all(matcher(lines[i + j], block_lines[j]) for j in range(len(block_lines))):
                candidates.append(i)

        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise DashboardSearchReplaceError(
                "Search block matched multiple locations; refine the SEARCH section for uniqueness."
            )

    # Fallback to fuzzy match on full block string
    needle = "\n".join(block_lines)
    best_score = 0.0
    best_index = -1
    if not needle.strip():
        raise DashboardSearchReplaceError("Search block cannot be empty.")

    for i in range(len(lines) - len(block_lines) + 1):
        window = "\n".join(lines[i : i + len(block_lines)])
        score = SequenceMatcher(None, window, needle).ratio()
        if score > best_score:
            best_score = score
            best_index = i

    if best_score >= 0.9 and best_index != -1:
        return best_index

    raise DashboardSearchReplaceError(
        f"Search block did not match any content in the dashboard body. Best similarity: {best_score:.2f}"
    )


def apply_search_replace(content: str, diff_content: str) -> str:
    blocks = parse_search_replace_blocks(diff_content)

    if not blocks:
        raise DashboardSearchReplaceError(
            "No SEARCH/REPLACE blocks detected. Use <<<<<<< SEARCH, =======, >>>>>>> REPLACE markers."
        )

    line_ending = "\r\n" if "\r\n" in content else "\n"
    lines = _split_lines_preserve(content)

    for block in blocks:
        search_lines = _split_lines_preserve(block.search)
        replace_lines = _split_lines_preserve(block.replace)

        if not search_lines or all(line == "" for line in search_lines):
            raise DashboardSearchReplaceError("SEARCH section cannot be empty.")

        _check_for_marker_lines(search_lines, "SEARCH")
        _check_for_marker_lines(replace_lines, "REPLACE")

        start_idx = _find_block_start(lines, search_lines)
        end_idx = start_idx + len(search_lines)
        lines = lines[:start_idx] + replace_lines + lines[end_idx:]

    updated = _join_lines_preserve(lines, line_ending, content)

    if any(marker in updated for marker in ("<<<<<<< SEARCH", ">>>>>>> REPLACE")):
        raise DashboardSearchReplaceError(
            "Replacement output still contains diff markers. Ensure each block is formatted correctly."
        )

    return updated


def parse_dashboard_patch(patch_text: str) -> list[PatchChunk]:
    if PATCH_BEGIN not in patch_text or PATCH_END not in patch_text:
        raise DashboardPatchError("Patch must include '*** Begin Patch' and '*** End Patch' markers.")

    lines = patch_text.splitlines()
    hunks: list[PatchChunk] = []
    i = 0
    inside_patch = False

    while i < len(lines):
        line = lines[i].strip()
        if line == PATCH_BEGIN:
            inside_patch = True
            i += 1
            continue
        if line == PATCH_END:
            break

        if inside_patch and line.startswith("*** Update File:"):
            i += 1
            # Expect @@ header
            if i >= len(lines) or not lines[i].startswith("@@"):
                raise DashboardPatchError("Patch chunk missing @@ header.")

            i += 1
            old_lines: list[str] = []
            new_lines: list[str] = []
            while i < len(lines) and not lines[i].startswith("***"):
                chunk_line = lines[i]
                if chunk_line.startswith("+"):
                    new_lines.append(chunk_line[1:])
                elif chunk_line.startswith("-"):
                    old_lines.append(chunk_line[1:])
                elif chunk_line.startswith(" "):
                    segment = chunk_line[1:]
                    old_lines.append(segment)
                    new_lines.append(segment)
                elif chunk_line == "":
                    old_lines.append("")
                    new_lines.append("")
                else:
                    break
                i += 1

            hunks.append(PatchChunk(old_lines=old_lines, new_lines=new_lines))
            continue

        i += 1

    if not hunks:
        raise DashboardPatchError("No valid update hunks found in patch.")

    return hunks


def apply_dashboard_patch(content: str, patch_text: str) -> str:
    lines = _split_lines_preserve(content)
    hunks = parse_dashboard_patch(patch_text)

    for hunk in hunks:
        if not hunk.old_lines:
            raise DashboardPatchError("Patch hunks must include existing lines to match.")

        start_idx = _find_block_start(lines, hunk.old_lines)
        end_idx = start_idx + len(hunk.old_lines)
        lines = lines[:start_idx] + hunk.new_lines + lines[end_idx:]

    line_ending = "\r\n" if "\r\n" in content else "\n"
    return _join_lines_preserve(lines, line_ending, content)
