# PyInstaller hook for sqlglot
from PyInstaller.utils.hooks import collect_submodules

# Collect all dialect submodules
# sqlglot dynamically imports dialects at runtime based on string parameters
# e.g., sqlglot.parse(query, dialect="postgres") -> imports sqlglot.dialects.postgres
hiddenimports = collect_submodules("sqlglot.dialects")

# Ensure core expression modules are included
hiddenimports += collect_submodules("sqlglot.expressions")
