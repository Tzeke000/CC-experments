"""Optional live LLM tool-loop (OpenAI-compatible Chat Completions).

Blocked without API keys — see ``docs/making-things/agent-evals.md``.
Uses ``httpx2`` only (already a server dependency); no openai SDK pin.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

import httpx2

from evals.mt_agent.mock_session import MockToolSession
from evals.mt_agent.score import ToolCall

# Env vars for live runs (any one of the key vars is enough with a base URL).
ENV_KEY_CANDIDATES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",  # only used if base URL points at an Anthropic gateway
    "MAKING_THINGS_LLM_API_KEY",
)
ENV_BASE_URL = "MAKING_THINGS_LLM_BASE_URL"  # default https://api.openai.com/v1
ENV_MODEL = "MAKING_THINGS_LLM_MODEL"  # default gpt-4o-mini


@dataclass
class LiveLlmConfig:
    api_key: str
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> LiveLlmConfig | None:
        key = None
        for name in ENV_KEY_CANDIDATES:
            val = os.environ.get(name, "").strip()
            if val:
                key = val
                break
        if not key:
            return None
        return cls(
            api_key=key,
            base_url=os.environ.get(ENV_BASE_URL, "https://api.openai.com/v1").rstrip("/"),
            model=os.environ.get(ENV_MODEL, "gpt-4o-mini"),
        )


def tool_schemas_for_case(tool_names: list[str]) -> list[dict[str, Any]]:
    """Minimal function schemas — enough for the model to call Making Things tools."""
    schemas: list[dict[str, Any]] = []
    for name in tool_names:
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"Making Things MCP tool {name}",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    },
                },
            }
        )
    return schemas


async def run_live_llm_case(
    *,
    prompt: str,
    allowed_tools: list[str],
    max_steps: int = 12,
    session: MockToolSession | None = None,
) -> tuple[list[ToolCall], str]:
    """Run a Chat Completions tool loop against the mock tool session.

    Returns ``(calls, blocker_or_final_text)``. When config is missing, returns
    ``([], "BLOCKED: …")`` without raising.
    """
    cfg = LiveLlmConfig.from_env()
    if cfg is None:
        needed = ", ".join(ENV_KEY_CANDIDATES)
        return (
            [],
            f"BLOCKED: set one of [{needed}] (and optionally {ENV_BASE_URL}, {ENV_MODEL}) "
            "for live LLM agent evals.",
        )

    tools_session = session or MockToolSession()
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are a Godot Making Things agent. Call MCP tools to solve the task. "
                "Prefer the smallest tool sequence that satisfies the pass criteria. "
                "Never claim success while parse errors remain. "
                "Live mutate is runtime-only (persisted=false)."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    tools = tool_schemas_for_case(allowed_tools)
    final_text = ""

    async with httpx2.AsyncClient(timeout=60.0) as client:
        for _ in range(max_steps):
            resp = await client.post(
                f"{cfg.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {cfg.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                },
            )
            if resp.status_code >= 400:
                return (
                    tools_session.history,
                    f"BLOCKED: LLM HTTP {resp.status_code}: {resp.text[:400]}",
                )
            payload = resp.json()
            choice = payload["choices"][0]["message"]
            messages.append(choice)
            tool_calls = choice.get("tool_calls") or []
            if not tool_calls:
                final_text = str(choice.get("content") or "")
                break
            for tc in tool_calls:
                fn = tc["function"]
                name = fn["name"]
                try:
                    arguments = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                if name not in allowed_tools:
                    call = ToolCall(
                        name=name,
                        arguments=arguments,
                        ok=False,
                        error=f"tool not in allowed set: {allowed_tools}",
                    )
                    tools_session.history.append(call)
                    result_content = json.dumps({"error": call.error})
                else:
                    call = await tools_session.call_tool(name, arguments)
                    result_content = json.dumps(
                        call.result if call.ok else {"error": call.error}
                    )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result_content,
                    }
                )
        else:
            final_text = "max_steps exceeded"

    return tools_session.history, final_text
