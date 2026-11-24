"""Agent tool-use loop on the Claude Messages API, with an offline stand-in.

LIVE    - Claude decides which tools to call. We loop while stop_reason == "tool_use",
          run every tool_use block, and return all tool_result blocks in ONE user message.
OFFLINE - a deterministic planner picks the next tool from the message content and the
          results so far. Tools are the same Python functions in both modes, so every
          tool call (and its real result) is recorded identically for the trace.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from common.claude import MODEL, _client, live


@dataclass
class AgentRun:
    calls: list[dict] = field(default_factory=list)  # [{"tool", "input", "result"}]
    final: str = ""
    turns: int = 0


def run_agent(
    *,
    system: str,
    user: str,
    tools: list[dict],
    handlers: dict[str, Callable[..., object]],
    offline_planner: Callable[[str, list[dict]], dict],
    max_turns: int = 12,
) -> AgentRun:
    """Run one agent task to completion.

    tools:            [{"name", "description", "input_schema"}] sent to Claude.
    handlers:         tool name -> Python function(**input) returning a JSON-able result.
    offline_planner:  (user, calls_so_far) -> {"tool": name, "input": {...}} or {"final": text}.
    """
    run = AgentRun()

    def call(name: str, args: dict):
        try:
            result = handlers[name](**args)
        except Exception as e:  # report tool errors back to the model instead of crashing
            result = {"error": f"{type(e).__name__}: {e}"}
        run.calls.append({"tool": name, "input": args, "result": result})
        return result

    if not live():
        for _ in range(max_turns):
            run.turns += 1
            nxt = offline_planner(user, run.calls)
            if "final" in nxt:
                run.final = nxt["final"]
                return run
            call(nxt["tool"], nxt["input"])
        run.final = "(stopped: max turns reached)"
        return run

    client = _client()
    msgs: list[dict] = [{"role": "user", "content": user}]
    resp = None
    for _ in range(max_turns):
        run.turns += 1
        resp = client.messages.create(
            model=MODEL, max_tokens=16000, system=system, tools=tools, messages=msgs
        )
        if resp.stop_reason != "tool_use":
            break
        msgs.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type == "tool_use":
                out = call(block.name, dict(block.input))
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id,
                     "content": json.dumps(out, default=str)}
                )
        msgs.append({"role": "user", "content": results})
    if resp is not None and resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request")
    run.final = "".join(b.text for b in resp.content if b.type == "text") if resp else ""
    return run
