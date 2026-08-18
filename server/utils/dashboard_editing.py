import re
from dataclasses import dataclass
from difflib import SequenceMatcher


class DashboardEditError(Exception):
    """Base exception for dashboard editing failures."""


class DashboardSearchReplaceError(DashboardEditError):
    """Raised when a SEARCH/REPLACE block cannot be applied."""


class DashboardPatchError(DashboardEditError):
    """Raised when a patch cannot be parsed or applied."""


class DashboardValidationError(DashboardEditError):
    """Raised when edited dashboard HTML violates a runtime invariant."""


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
HOOK_PATTERN = re.compile(r"\b(?:React\.)?use(?:State|Effect|Memo|Callback|Ref|Reducer|Context|LayoutEffect)\s*\(")
EARLY_RETURN_PATTERN = re.compile(r"\bif\s*\([^)]*\)\s*\{?\s*return\b", re.DOTALL)


def _brace_depth_at_positions(source: str, positions: list[int]) -> dict[int, int]:
    """Return brace depth at selected offsets, ignoring strings and comments."""
    targets = set(positions)
    depths: dict[int, int] = {}
    depth = 0
    quote: str | None = None
    escaped = False
    line_comment = False
    block_comment = False
    index = 0

    while index < len(source):
        if index in targets:
            depths[index] = depth

        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
        elif block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 1
        elif quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char == "/" and next_char == "/":
            line_comment = True
            index += 1
        elif char == "/" and next_char == "*":
            block_comment = True
            index += 1
        elif char in {'"', "'", "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        index += 1

    for position in targets:
        depths.setdefault(position, depth)
    return depths


def validate_dashboard_html(content: str) -> None:
    """Reject hook declarations after a component-level conditional return.

    Dashboard HTML is generated incrementally. A common invalid edit inserts a
    hook below the starter template's loading return, changing the number of
    hooks between renders. This narrow guard catches that runtime failure before
    the edited version is persisted while leaving hooks inside nested helper
    components alone.
    """
    component_start = re.search(r"\bconst\s+Dashboard\s*=\s*\(\s*\)\s*=>\s*\{", content)
    render_start = content.find("ReactDOM.render", component_start.end() if component_start else 0)
    if component_start is None or render_start < 0:
        return

    component = content[component_start.end() : render_start]
    returns = list(EARLY_RETURN_PATTERN.finditer(component))
    hooks = list(HOOK_PATTERN.finditer(component))
    positions = [match.start() for match in (*returns, *hooks)]
    depths = _brace_depth_at_positions(component, positions)
    top_level_returns = [match for match in returns if depths[match.start()] == 0]
    if not top_level_returns:
        return

    first_return_offset = top_level_returns[0].start()
    trailing_hook = next(
        (match for match in hooks if match.start() > first_return_offset and depths[match.start()] == 0),
        None,
    )
    if trailing_hook:
        raise DashboardValidationError(
            "Dashboard hooks must be declared before the first conditional return. "
            "Move every useState/useEffect hook to the top of Dashboard and retry the edit."
        )


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
