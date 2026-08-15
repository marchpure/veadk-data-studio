# PyInstaller hook for litellm
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

# Only collect specific data files that are actually needed at runtime
# Collecting all litellm files (1000+) makes the build very slow
datas = []

try:
    import litellm

    litellm_path = Path(litellm.__file__).parent

    tokenizers_path = litellm_path / "litellm_core_utils" / "tokenizers"
    if tokenizers_path.exists():
        for json_file in tokenizers_path.glob("*.json"):
            datas.append((str(json_file), "litellm/litellm_core_utils/tokenizers"))

    containers_path = litellm_path / "containers" / "endpoints.json"
    if containers_path.exists():
        datas.append((str(containers_path), "litellm/containers"))

    cost_json = litellm_path / "cost.json"
    if cost_json.exists():
        datas.append((str(cost_json), "litellm"))

except Exception:
    datas = collect_data_files("litellm")
