import difflib
import glob as globmod
import os
import shutil
from pathlib import Path

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def build_expanded_path(home_dir: Path | None = None) -> str:
    """Build a comprehensive PATH string covering all common CLI install locations.

    Reusable by both find_claude_cli_path() and claude_mcp_service.py so that
    CLI discovery and SDK subprocess launch share the same search scope.
    """
    home = home_dir or Path.home()
    home_str = str(home)
    system_path = os.environ.get("PATH", "")

    extra: list[str] = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        f"{home_str}/.local/bin",
        f"{home_str}/.bun/bin",
        f"{home_str}/.volta/bin",
        f"{home_str}/.npm-global/bin",
        f"{home_str}/.npm/bin",
        f"{home_str}/.yarn/bin",
        f"{home_str}/Library/pnpm",
        f"{home_str}/.local/share/pnpm",
        f"{home_str}/.asdf/shims",
        f"{home_str}/.asdf/bin",
    ]

    pnpm_home = os.environ.get("PNPM_HOME")
    if pnpm_home:
        extra.append(pnpm_home)

    # Native installer location
    native_current = home / ".local" / "share" / "claude" / "current"
    if native_current.is_dir():
        extra.append(str(native_current))

    # nvm versions
    nvm_dir_env = os.environ.get("NVM_DIR")
    if nvm_dir_env and Path(nvm_dir_env).is_dir():
        nvm_dir = Path(nvm_dir_env)
    else:
        nvm_dir = home / ".nvm"
    nvm_versions = nvm_dir / "versions" / "node"
    if nvm_versions.is_dir():
        versions = sorted(
            [p for p in nvm_versions.iterdir() if p.is_dir()],
            reverse=True,
        )
        for v in versions:
            extra.append(str(v / "bin"))

    # fnm versions
    fnm_dirs = [
        home / "Library" / "Application Support" / "fnm" / "node-versions",
        home / ".local" / "share" / "fnm" / "node-versions",
    ]
    for fnm_dir in fnm_dirs:
        if fnm_dir.is_dir():
            versions = sorted(
                [p for p in fnm_dir.iterdir() if p.is_dir()],
                reverse=True,
            )
            for v in versions:
                extra.append(str(v / "installation" / "bin"))

    return f"{':'.join(extra)}:{system_path}"


def find_claude_cli_path(
    search_path: str | None = None,
    home_dir: Path | None = None,
) -> str | None:
    """
    Auto-detect Claude CLI path by checking common installation locations.
    When launched from Tauri (Finder/Dock), shell profiles aren't sourced so
    nvm/fnm/volta/bun bin dirs won't be in PATH. We check those explicitly.
    """
    # Env var override — escape hatch for non-standard installs
    for env_key in ("BYAAN_CLAUDE_CLI_PATH", "CLAUDE_CLI_PATH"):
        override = os.environ.get(env_key)
        if override and _is_executable_file(Path(override)):
            logger.info(f"Using Claude CLI from {env_key}: {override}")
            return override

    if search_path is None:
        which_result = shutil.which("claude")
        if which_result:
            return which_result
    else:
        which_result = shutil.which("claude", path=search_path)
        if which_result:
            return which_result

    home = home_dir or Path.home()

    pnpm_home = os.environ.get("PNPM_HOME")

    search_locations: list[Path] = [
        home / ".local/bin/claude",
        Path("/opt/homebrew/bin/claude"),
        Path("/usr/local/bin/claude"),
        home / ".npm-global/bin/claude",
        home / ".npm/bin/claude",
        home / ".yarn/bin/claude",
        home / "node_modules/.bin/claude",
        home / ".claude/local/claude",
        home / ".bun/bin/claude",
        home / ".volta/bin/claude",
        home / "Library/pnpm/claude",
        home / ".local/share/pnpm/claude",
        home / ".asdf/shims/claude",
        home / ".asdf/bin/claude",
        # Native installer (curl ... | bash) locations
        home / ".local/share/claude/current/claude",
    ]
    if pnpm_home:
        search_locations.insert(0, Path(pnpm_home) / "claude")

    for location in search_locations:
        if _is_executable_file(location):
            return str(location)

    # Native installer versioned dirs
    native_versions = home / ".local" / "share" / "claude" / "versions"
    if native_versions.is_dir():
        candidates = sorted(
            globmod.glob(str(native_versions / "*" / "claude")),
            reverse=True,
        )
        for candidate in candidates:
            if _is_executable_file(Path(candidate)):
                return candidate
        # Fallback: some installers place the binary as versions/<version> directly
        for entry in sorted(native_versions.iterdir(), reverse=True):
            if entry.is_file() and os.access(entry, os.X_OK):
                return str(entry)

    nvm_dir_env = os.environ.get("NVM_DIR")
    if nvm_dir_env and Path(nvm_dir_env).is_dir():
        nvm_dir = Path(nvm_dir_env)
    else:
        nvm_dir = home / ".nvm"
    nvm_versions = nvm_dir / "versions" / "node"
    if nvm_versions.is_dir():
        candidates = sorted(nvm_versions.glob("*/bin/claude"), reverse=True)
        for candidate in candidates:
            if _is_executable_file(candidate):
                return str(candidate)

    fnm_dirs = [
        home / "Library" / "Application Support" / "fnm" / "node-versions",
        home / ".local" / "share" / "fnm" / "node-versions",
    ]
    for fnm_dir in fnm_dirs:
        if fnm_dir.is_dir():
            candidates = sorted(fnm_dir.glob("*/installation/bin/claude"), reverse=True)
            for candidate in candidates:
                if _is_executable_file(candidate):
                    return str(candidate)

    return None


class FileOperations:
    """Handle file operations for the code assistant."""

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace in text for comparison purposes."""
        import re

        # Replace multiple spaces with single space and normalize line breaks
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n", "\n", text)
        return text.strip()

    @staticmethod
    def fuzzy_find_and_replace(content: str, find_text: str, replace_text: str) -> tuple[str, bool]:
        """Attempt to find and replace text using multiple strategies."""
        try:
            original_content = content

            # Strategy 1: Exact match (original behavior)
            if find_text in content:
                return content.replace(find_text, replace_text, 1), True

            # Strategy 2: Normalized whitespace matching
            normalized_content = FileOperations.normalize_whitespace(content)
            normalized_find = FileOperations.normalize_whitespace(find_text)
            FileOperations.normalize_whitespace(replace_text)

            if normalized_find in normalized_content:
                # Find the original location and replace there
                normalized_lines = normalized_content.split("\n")
                find_lines = normalized_find.split("\n")

                # Find the start line
                for i in range(len(normalized_lines) - len(find_lines) + 1):
                    if normalized_lines[i : i + len(find_lines)] == find_lines:
                        # Found it! Now replace in original content
                        content_lines = content.split("\n")
                        replace_lines = replace_text.split("\n")
                        result_lines = content_lines[:i] + replace_lines + content_lines[i + len(find_lines) :]
                        return "\n".join(result_lines), True

            # Strategy 3: Fuzzy line-by-line matching
            content_lines = content.split("\n")
            find_lines = find_text.split("\n")

            # Look for approximate matches using difflib
            for i in range(len(content_lines) - len(find_lines) + 1):
                content_section = "\n".join(content_lines[i : i + len(find_lines)])

                # Calculate similarity ratio
                similarity = difflib.SequenceMatcher(None, content_section.strip(), find_text.strip()).ratio()

                if similarity > 0.8:  # 80% similarity threshold
                    # Close enough match, perform replacement
                    replace_lines = replace_text.split("\n")
                    result_lines = content_lines[:i] + replace_lines + content_lines[i + len(find_lines) :]
                    logger.info(f"Fuzzy match found with {similarity:.2f} similarity")
                    return "\n".join(result_lines), True

            # Strategy 4: Key phrase matching (for partial matches)
            find_lines_stripped = [line.strip() for line in find_lines if line.strip()]
            if len(find_lines_stripped) > 0:
                # Look for distinctive lines as anchors
                key_line = max(find_lines_stripped, key=len)  # Use longest line as key

                for i, content_line in enumerate(content_lines):
                    if (
                        key_line in content_line
                        or difflib.SequenceMatcher(None, content_line.strip(), key_line).ratio() > 0.7
                    ):
                        # Found anchor line, try to match surrounding context
                        start_idx = max(0, i - find_lines_stripped.index(key_line.strip()))
                        end_idx = min(len(content_lines), start_idx + len(find_lines))

                        if end_idx <= len(content_lines):
                            replace_lines = replace_text.split("\n")
                            result_lines = content_lines[:start_idx] + replace_lines + content_lines[end_idx:]
                            logger.info(f"Key phrase match found using line: {key_line[:30]}...")
                            return "\n".join(result_lines), True

            return original_content, False
        except Exception as e:
            logger.error(
                f"Failed to perform fuzzy find and replace: {str(e)}",
                exc_info=True,
                posthog_context={
                    "function": "FileOperations.fuzzy_find_and_replace",
                    "content_length": len(content) if content else 0,
                    "find_text_length": len(find_text) if find_text else 0,
                },
            )
            return content, False
