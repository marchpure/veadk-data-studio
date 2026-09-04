"""Server-only adapter for the deployed W5 AgentKit Skill Agent."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


class W5AdapterError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class W5Invocation:
    business_goal: str
    mcp_capability_refs: list[str]
    knowledge_resource_refs: list[str]
    target_skill: str | None
    revision: str | None
    session_id: str
    delegated_auth_ref: str | None


class W5SkillAgentAdapter:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        auth_provider: str | None = None,
        runtime_id: str | None = None,
        region: str | None = None,
        cli_path: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("SKILL_AGENT_BASE_URL", "")).rstrip("/")
        self.timeout = timeout or float(os.getenv("SKILL_AGENT_TIMEOUT_SECONDS", "60"))
        self.auth_provider = auth_provider or os.getenv("SKILL_AGENT_DELEGATED_AUTH_PROVIDER", "")
        self.runtime_id = runtime_id or os.getenv("SKILL_AGENT_RUNTIME_ID", "")
        self.region = region or os.getenv("SKILL_AGENT_REGION", "cn-beijing")
        self.cli_path = cli_path or os.getenv("AGENTKIT_CLI_PATH", "agentkit")

    def delegated_auth_ref(self, auth: Any) -> str | None:
        if not self.auth_provider:
            return None
        module, separator, function_name = self.auth_provider.partition(":")
        if not separator:
            raise W5AdapterError("CONFIG_ERROR", "Delegated auth provider must be module:function")
        value = getattr(importlib.import_module(module), function_name)(auth)
        return value if isinstance(value, str) and value else None

    async def invoke(self, invocation: W5Invocation) -> AsyncIterator[dict[str, Any]]:
        if not invocation.delegated_auth_ref:
            raise W5AdapterError("BLOCKED_AUTH", "Complete OAuth or re-authorize to continue.")
        if self.base_url and not self.runtime_id:
            raise W5AdapterError("CONFIG_ERROR", "REST endpoint transport is not an approved W5 contract")
        if not self.runtime_id:
            raise W5AdapterError("CONFIG_ERROR", "SKILL_AGENT_RUNTIME_ID is not configured")
        request = {
            "business_goal": invocation.business_goal,
            "mcp_capability_refs": invocation.mcp_capability_refs,
            "knowledge_resource_refs": invocation.knowledge_resource_refs,
            "target_skill": invocation.target_skill,
            "revision": invocation.revision,
            "session_id": invocation.session_id,
            "delegated_auth_ref": invocation.delegated_auth_ref,
        }
        command = [
            self.cli_path, "invoke", "run",
            "--runtime-id", self.runtime_id,
            "--region", self.region,
            "--raw",
            "--payload", json.dumps({"prompt": json.dumps(request, ensure_ascii=False)}),
            "--headers", json.dumps({
                "delegated_auth_ref": invocation.delegated_auth_ref,
                "session_id": invocation.session_id,
            }),
        ]
        process = None
        stderr_task = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stderr_task = asyncio.create_task(process.stderr.read()) if process.stderr else None
            deadline = asyncio.get_running_loop().time() + self.timeout
            while process.stdout:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError
                line = await asyncio.wait_for(process.stdout.readline(), timeout=remaining)
                if not line:
                    break
                event = self.parse_event(line.decode(errors="replace"))
                if event is not None:
                    yield event
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError
            await asyncio.wait_for(process.wait(), timeout=remaining)
            stderr = await stderr_task if stderr_task else b""
        except TimeoutError as exc:
            if process is not None:
                await self._terminate(process)
            raise W5AdapterError("RETRYABLE", "W5 invocation timed out", retryable=True) from exc
        except asyncio.CancelledError as exc:
            if process is not None:
                await self._terminate(process)
            raise W5AdapterError("CANCELLED", "W5 invocation cancelled") from exc
        except OSError as exc:
            raise W5AdapterError("RETRYABLE", f"AgentKit invocation failed: {exc}", retryable=True) from exc
        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip() or "AgentKit invocation failed"
            if "401" in detail or "403" in detail or "BLOCKED_AUTH" in detail:
                raise W5AdapterError("BLOCKED_AUTH", detail)
            raise W5AdapterError("RETRYABLE", detail, retryable=True)
        if stderr_task and not stderr_task.done():
            stderr_task.cancel()

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=2)
        except TimeoutError:
            process.kill()
            await process.wait()

    @staticmethod
    def parse_event(line: str) -> dict[str, Any] | None:
        value = line.strip()
        if not value or value.startswith(":"):
            return None
        if value.startswith("data:"):
            value = value[5:].strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"type": "observation", "text": value}
        return parsed if isinstance(parsed, dict) else {"type": "observation", "value": parsed}
