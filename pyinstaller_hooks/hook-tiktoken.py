# PyInstaller hook for tiktoken
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all tiktoken data files (encodings)
datas = collect_data_files("tiktoken")

# Collect all submodules
hiddenimports = collect_submodules("tiktoken")

# Also include tiktoken_ext if it exists
try:
    datas += collect_data_files("tiktoken_ext")
    hiddenimports += collect_submodules("tiktoken_ext")
except Exception:
    pass
