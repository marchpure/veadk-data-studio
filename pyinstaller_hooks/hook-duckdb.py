"""PyInstaller hook for duckdb.

Ensures DuckDB's shared libraries and distribution metadata are bundled so the
frozen backend can import duckdb, resolve its version at runtime, and load any
installed DuckDB extension wheels (e.g., duckdb-extension-excel).
"""

import importlib.metadata
import importlib.util
from collections.abc import Iterable

from PyInstaller.utils.hooks import collect_data_files, copy_metadata

# Include any native libraries/resources shipped with duckdb (e.g., extensions).
datas = collect_data_files("duckdb", include_py_files=False)

# Bundle package metadata so importlib.metadata.version('duckdb') works.
datas += copy_metadata("duckdb")

# Hidden imports populated at runtime below.
hiddenimports = []


def _maybe_include_package(module_name: str, dist_name: str | None = None) -> None:
    """Add metadata and resources for optional DuckDB extension packages."""

    if importlib.util.find_spec(module_name) is None:
        return

    hiddenimports.append(module_name)
    datas.extend(collect_data_files(module_name, include_py_files=False))

    metadata_target = dist_name or module_name
    try:
        datas.extend(copy_metadata(metadata_target))
    except Exception:
        # Some community wheels omit metadata. Skip silently so the build still succeeds.
        pass


def _iter_duckdb_extension_dists() -> Iterable[tuple[str, str]]:
    """Yield (module_name, dist_name) for any installed duckdb-extension-* wheels."""

    for dist in importlib.metadata.distributions():
        dist_name = dist.metadata.get("Name")
        if not dist_name:
            continue

        normalized = dist_name.lower().replace("_", "-")
        if not normalized.startswith("duckdb-extension-"):
            continue

        module_name = dist_name.replace("-", "_")
        yield module_name, dist_name


# Packages explicitly tracked in pyproject (module_name, dist_name)
_explicit_optional_packages = (
    ("duckdb_extensions", "duckdb-extensions"),
    ("duckdb_extension_excel", "duckdb-extension-excel"),
)

for module_name, dist_name in _explicit_optional_packages:
    _maybe_include_package(module_name, dist_name)

# Auto-discover standalone DuckDB extension wheels following duckdb-extension-* naming.
for module_name, dist_name in _iter_duckdb_extension_dists():
    _maybe_include_package(module_name, dist_name)
