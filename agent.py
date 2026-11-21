"""Baseline tool-calling agent loop (no security gateway)."""

import json
from dataclasses import dataclass, field
from typing import Callable

import config
from llm import ChatClient
from tools import ToolRegistry

SYSTEM_PROMPT = (
    "You are a mail assistant acting for the user {owner}. "
    "Use the provided tools to read and manage the user's mailbox. "
    "Answer in the language the user writes in. "
    "When the task is done, reply with a short summary of what you did."
)


@dataclass
class ToolCallRecord:
    name: str
    arguments: dict
    result: str


@dataclass
class AgentResult:
    final_text: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    stopped_at_step_limit: bool = False


def run_agent(
    client: ChatClient,
    registry: ToolRegistry,
    owner: str,
    user_message: str,
    max_steps: int = config.MAX_AGENT_STEPS,
    on_tool_call: Callable[[ToolCallRecord], None] | None = None,
) -> AgentResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(owner=owner)},
        {"role": "user", "content": user_message},
    ]
    records: list[ToolCallRecord] = []

    for _ in range(max_steps):
        reply = client.chat(messages, tools=registry.schemas())
        tool_calls = reply.get("tool_calls") or []
        messages.append({
            "role": "assistant",
            "content": reply.get("content") or "",
            **({"tool_calls": tool_calls} if tool_calls else {}),
        })
        if not tool_calls:
            return AgentResult(final_text=reply.get("content") or "", tool_calls=records)

        for call in tool_calls:
            name = call["function"]["name"]
            raw_args = call["function"].get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                arguments = None

            if isinstance(arguments, dict):
                result = registry.execute(name, arguments)
            else:
                arguments = {"_raw": raw_args}
                result = json.dumps({"error": "Tool arguments were not a valid JSON object"})

            record = ToolCallRecord(name=name, arguments=arguments, result=result)
            records.append(record)
            if on_tool_call:
                on_tool_call(record)
            messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})

    return AgentResult(
        final_text="(step limit reached before the agent finished)",
        tool_calls=records,
        stopped_at_step_limit=True,
    )
