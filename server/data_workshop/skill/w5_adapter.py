"""Server-only AgentKit transport and event normalization for the W5 Skill Agent."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx


class W5AdapterError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class W5Invocation:
    business_goal: str
    mcp_capability_refs: list[str]
    knowledge_resource_refs: list[str]
    target_skill: str
    revision: str | None
    session_id: str
    delegated_auth_ref: str | None


class W5SkillAgentAdapter:
    """Invoke the deployed W5 AgentKit runtime without browser-visible credentials."""

    def __init__(
        self,
        *,
        runtime_id: str | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        region: str | None = None,
        cli_path: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.runtime_id = runtime_id if runtime_id is not None else os.getenv("W5_SKILL_AGENT_RUNTIME_ID", "")
        self.endpoint = endpoint if endpoint is not None else os.getenv("W5_SKILL_AGENT_ENDPOINT", "")
        self.api_key = api_key if api_key is not None else os.getenv("W5_SKILL_AGENT_API_KEY", "")
        self.region = region if region is not None else os.getenv("W5_SKILL_AGENT_REGION", "cn-beijing")
        self.cli_path = cli_path if cli_path is not None else os.getenv("AGENTKIT_CLI_PATH", "agentkit")
        self.timeout = timeout or float(os.getenv("W5_SKILL_AGENT_TIMEOUT_SECONDS", "120"))

    async def invoke(self, invocation: W5Invocation) -> AsyncIterator[dict[str, Any]]:
        if not self.runtime_id and not self.endpoint:
            raise W5AdapterError("BLOCKED_CONFIG", "W5 production transport 尚未配置。")
        if not invocation.delegated_auth_ref:
            raise W5AdapterError("BLOCKED_AUTH", "请完成 OAuth 授权或重新授权后继续。")

        request = {
            "business_goal": invocation.business_goal,
            "mcp_capability_refs": invocation.mcp_capability_refs,
            "knowledge_resource_refs": invocation.knowledge_resource_refs,
            "target_skill": invocation.target_skill,
            "revision": invocation.revision,
            "session_id": invocation.session_id,
            "delegated_auth_ref": invocation.delegated_auth_ref,
        }
        if self.endpoint:
            async for event in self._invoke_endpoint(request, invocation):
                yield event
            return

        command = [self.cli_path, "invoke", "run"]
        command.extend(["--runtime-id", self.runtime_id, "--region", self.region])
        command.extend(
            [
                "--raw",
                "--payload",
                json.dumps({"prompt": json.dumps(request, ensure_ascii=False)}, ensure_ascii=False),
                "--headers",
                json.dumps(
                    {
                        "delegated_auth_ref": invocation.delegated_auth_ref,
                        "session_id": invocation.session_id,
                    }
                ),
            ]
        )
        process: asyncio.subprocess.Process | None = None
        stderr_task: asyncio.Task[bytes] | None = None
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "COLUMNS": "10000", "NO_COLOR": "1", "TERM": "dumb"},
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
            raise W5AdapterError("RETRYABLE", "W5 调用超时，可稍后重试。", retryable=True) from exc
        except asyncio.CancelledError as exc:
            if process is not None:
                await self._terminate(process)
            raise W5AdapterError("CANCELLED", "W5 调用已停止。") from exc
        except OSError as exc:
            raise W5AdapterError("BLOCKED_CONFIG", "AgentKit CLI 不可用或未正确配置。") from exc

        if process.returncode != 0:
            detail = stderr.decode(errors="replace").strip() or "AgentKit 调用失败"
            if "401" in detail or "403" in detail or "BLOCKED_AUTH" in detail:
                raise W5AdapterError("BLOCKED_AUTH", "W5 拒绝了委托授权，请重新授权。")
            if any(
                marker in detail.casefold()
                for marker in ("blocked_config", "config", "not deployed", "failed to obtain runtime", "api key")
            ):
                raise W5AdapterError("BLOCKED_CONFIG", "W5 production transport 尚未正确配置。")
            raise W5AdapterError("RETRYABLE", "W5 AgentKit 调用失败，可稍后重试。", retryable=True)

    async def _invoke_endpoint(
        self,
        request: dict[str, Any],
        invocation: W5Invocation,
    ) -> AsyncIterator[dict[str, Any]]:
        if not self.api_key:
            raise W5AdapterError("BLOCKED_CONFIG", "W5 endpoint API key 尚未配置。")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "text/event-stream, application/json",
            "Content-Type": "application/json",
            "delegated_auth_ref": invocation.delegated_auth_ref or "",
            "session_id": invocation.session_id,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.endpoint.rstrip('/')}/invoke",
                    json={"prompt": json.dumps(request, ensure_ascii=False)},
                    headers=headers,
                ) as response:
                    if response.status_code in {401, 403}:
                        raise W5AdapterError("BLOCKED_AUTH", "W5 拒绝了委托授权，请重新授权。")
                    if response.status_code >= 400:
                        raise W5AdapterError(
                            "RETRYABLE",
                            f"W5 调用失败（{response.status_code}）。",
                            retryable=True,
                        )
                    if "text/event-stream" in response.headers.get("content-type", "").casefold():
                        async for line in response.aiter_lines():
                            event = self.parse_event(line)
                            if event is not None:
                                yield event
                    else:
                        event = self._extract_result(response.json())
                        if event is not None:
                            yield event
        except W5AdapterError:
            raise
        except httpx.TimeoutException as exc:
            raise W5AdapterError("RETRYABLE", "W5 调用超时，可稍后重试。", retryable=True) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise W5AdapterError("RETRYABLE", "W5 响应无效，可稍后重试。", retryable=True) from exc

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
        if not value or value.startswith(":") or value.startswith("event:"):
            return None
        if value.startswith("data:"):
            value = value[5:].strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return {"type": "observation", "value": parsed}
        result = W5SkillAgentAdapter._extract_result(parsed)
        if result is not None:
            return result
        return parsed if isinstance(parsed.get("type"), str) else None

    @staticmethod
    def _extract_result(value: Any) -> dict[str, Any] | None:
        """Find the W5 InvocationResult inside AgentKit/ADK stream envelopes."""
        if isinstance(value, dict):
            if (
                isinstance(value.get("status"), str)
                and isinstance(value.get("target_skill"), str)
                and any(key in value for key in ("artifact", "validation", "events"))
            ):
                return value
            for key in ("response", "functionResponse", "function_response", "result"):
                nested = value.get(key)
                found = W5SkillAgentAdapter._extract_result(nested)
                if found is not None:
                    return found
            for key in ("content", "message", "data", "parts"):
                nested = value.get(key)
                found = W5SkillAgentAdapter._extract_result(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = W5SkillAgentAdapter._extract_result(item)
                if found is not None:
                    return found
        elif isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return W5SkillAgentAdapter._extract_result(parsed)
        return None
