"""Test-only stubs for optional dependencies used by the server codebase.

Placing this module inside the test tree ensures it is only imported when the
test runner includes `server/tests` on `PYTHONPATH` (for example via
`PYTHONPATH=..:tests`). Production environments should install the real
dependencies instead of relying on these shims.
"""

from __future__ import annotations

import sys
import types
from importlib import import_module


def _ensure_asyncpg() -> None:
    if "asyncpg" in sys.modules:
        return
    try:
        import_module("asyncpg")
        return
    except Exception:
        pass
    sys.modules["asyncpg"] = types.ModuleType("asyncpg")


def _ensure_certifi() -> None:
    if "certifi" in sys.modules:
        return
    try:
        import_module("certifi")
        return
    except Exception:
        pass

    module = types.ModuleType("certifi")

    def where() -> str:
        return ""

    module.where = where  # type: ignore[attr-defined]
    sys.modules["certifi"] = module


def _ensure_motor() -> None:
    if "motor.motor_asyncio" in sys.modules:
        return
    try:
        import_module("motor.motor_asyncio")
        return
    except Exception:
        pass

    motor_module = types.ModuleType("motor")
    motor_asyncio = types.ModuleType("motor.motor_asyncio")

    class _DummyMotorClient:
        def __init__(self, *args, **kwargs):
            self._databases: dict[str, object] = {}

        def __getitem__(self, name: str):
            return self._databases.setdefault(name, {})

        def close(self) -> None:
            pass

    motor_asyncio.AsyncIOMotorClient = _DummyMotorClient  # type: ignore[attr-defined]
    motor_module.motor_asyncio = motor_asyncio  # type: ignore[attr-defined]

    sys.modules["motor"] = motor_module
    sys.modules["motor.motor_asyncio"] = motor_asyncio


def _ensure_bson() -> None:
    try:
        import_module("bson")
        import_module("bson.regex")
        import_module("bson.json_util")
        return
    except Exception:
        pass

    if "bson" in sys.modules:
        return

    bson_module = types.ModuleType("bson")
    regex_module = types.ModuleType("bson.regex")
    json_util_module = types.ModuleType("bson.json_util")

    class _DummyObjectId(str):
        def __new__(cls, value: str | None = None):
            value = value or "0" * 24
            return str.__new__(cls, value)

    class _DummyRegex:
        def __init__(self, pattern, flags=0):
            self.pattern = pattern
            self.flags = flags

    class _DummySimpleValue:
        def __init__(self, value=None):
            self.value = value

    class _DummyTimestamp:
        def __init__(self, time: int = 0, inc: int = 0):
            self.time = time
            self.inc = inc

    def _dummy_json_dumps(value):
        return str(value)

    regex_module.Regex = _DummyRegex  # type: ignore[attr-defined]
    json_util_module.dumps = _dummy_json_dumps  # type: ignore[attr-defined]
    bson_module.ObjectId = _DummyObjectId  # type: ignore[attr-defined]
    bson_module.Binary = _DummySimpleValue  # type: ignore[attr-defined]
    bson_module.Code = _DummySimpleValue  # type: ignore[attr-defined]
    bson_module.DBRef = _DummySimpleValue  # type: ignore[attr-defined]
    bson_module.Decimal128 = _DummySimpleValue  # type: ignore[attr-defined]
    bson_module.Int64 = int  # type: ignore[attr-defined]
    bson_module.MaxKey = _DummySimpleValue  # type: ignore[attr-defined]
    bson_module.MinKey = _DummySimpleValue  # type: ignore[attr-defined]
    bson_module.Timestamp = _DummyTimestamp  # type: ignore[attr-defined]
    bson_module.regex = regex_module  # type: ignore[attr-defined]
    bson_module.json_util = json_util_module  # type: ignore[attr-defined]

    sys.modules["bson"] = bson_module
    sys.modules["bson.regex"] = regex_module
    sys.modules["bson.json_util"] = json_util_module


def _ensure_agents() -> None:
    if "agents" in sys.modules:
        return

    try:
        import_module("agents")
        return
    except Exception:
        pass

    agents_module = types.ModuleType("agents")

    class _Placeholder:
        pass

    agents_module.__path__ = []  # type: ignore[attr-defined]
    agents_module.Agent = _Placeholder  # type: ignore[attr-defined]
    agents_module.Runner = _Placeholder  # type: ignore[attr-defined]
    agents_module.RunItemStreamEvent = _Placeholder  # type: ignore[attr-defined]
    agents_module.ModelSettings = _Placeholder  # type: ignore[attr-defined]
    agents_module.RunConfig = _Placeholder  # type: ignore[attr-defined]
    agents_module.FunctionTool = _Placeholder  # type: ignore[attr-defined]
    agents_module.SQLiteSession = _Placeholder  # type: ignore[attr-defined]

    function_tool_module = types.ModuleType("agents.function_tool")

    def function_tool(func):
        return func

    function_tool_module.function_tool = function_tool  # type: ignore[attr-defined]
    agents_module.function_tool = function_tool  # type: ignore[attr-defined]

    run_context_module = types.ModuleType("agents.run_context")

    class RunContextWrapper(dict):
        pass

    run_context_module.RunContextWrapper = RunContextWrapper  # type: ignore[attr-defined]
    agents_module.RunContextWrapper = RunContextWrapper  # type: ignore[attr-defined]

    extensions_module = types.ModuleType("agents.extensions")
    extensions_module.__path__ = []  # type: ignore[attr-defined]
    models_module = types.ModuleType("agents.extensions.models")
    models_module.__path__ = []  # type: ignore[attr-defined]
    litellm_module = types.ModuleType("agents.extensions.models.litellm_model")

    class LiteLLMModelPlaceholder:  # pragma: no cover - import-only placeholder
        pass

    litellm_module.LitellmModel = LiteLLMModelPlaceholder  # type: ignore[attr-defined]

    sys.modules["agents"] = agents_module
    sys.modules["agents.extensions"] = extensions_module
    sys.modules["agents.extensions.models"] = models_module
    sys.modules["agents.extensions.models.litellm_model"] = litellm_module
    sys.modules["agents.function_tool"] = function_tool_module
    sys.modules["agents.run_context"] = run_context_module


def _ensure_sqlglot() -> None:
    try:
        import_module("sqlglot")
        import_module("sqlglot.exp")
        return
    except Exception:
        pass

    if "sqlglot" in sys.modules:
        return

    sqlglot_module = types.ModuleType("sqlglot")
    exp_module = types.ModuleType("sqlglot.exp")
    for name in ("Delete", "Insert", "Update", "Create", "Alter", "Drop"):
        setattr(exp_module, name, type(name, (), {}))
    sqlglot_module.exp = exp_module  # type: ignore[attr-defined]

    def parse(query, dialect=None):
        return []

    sqlglot_module.parse = parse  # type: ignore[attr-defined]
    sys.modules["sqlglot"] = sqlglot_module
    sys.modules["sqlglot.exp"] = exp_module


_ensure_asyncpg()
_ensure_certifi()
_ensure_motor()
_ensure_bson()
_ensure_agents()
_ensure_sqlglot()
