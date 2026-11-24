"""Tool-using agent loop on the Messages API, for event-driven agents (build 08).

LIVE    - client.messages.create(model=MODEL, tools=...) with the default (auto) tool choice.
          Loop while stop_reason == "tool_use": append the assistant turn, run every tool_use
          block, and send all tool_result blocks back in ONE user message.
OFFLINE - a rule-based `offline_policy` decides which tools to call each turn. The SAME tool
          functions run against the same data, so the tool calls in the trace are real.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from common.claude import MODEL, _client, live


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict
    fn: Callable[..., Any]

    def api(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.input_schema}


@dataclass
class AgentRun:
    calls: list[dict] = field(default_factory=list)  # {"turn", "name", "input", "output"}
    final_text: str = ""
    turns: int = 0


def run_agent(
    *,
    system: str,
    prompt: str,
    tools: list[Tool],
    offline_policy: Callable[[list[dict]], list[tuple[str, dict]]],
    max_turns: int = 6,
) -> AgentRun:
    """Run one agent episode. `offline_policy(calls_so_far)` returns the next tool calls ([] = done)."""
    by_name = {t.name: t for t in tools}
    run = AgentRun()

    if not live():
        while run.turns < max_turns:
            planned = offline_policy(run.calls)
            if not planned:
                break
            run.turns += 1
            for name, args in planned:  # several calls in one turn = parallel tool use
                run.calls.append({"turn": run.turns, "name": name, "input": args,
                                  "output": by_name[name].fn(**args)})
        run.final_text = "(offline policy finished)"
        return run

    client = _client()
    msgs: list[dict] = [{"role": "user", "content": prompt}]
    resp = None
    for _ in range(max_turns):
        resp = client.messages.create(model=MODEL, max_tokens=16000, system=system,
                                      tools=[t.api() for t in tools], messages=msgs)
        if resp.stop_reason != "tool_use":
            break
        run.turns += 1
        msgs.append({"role": "assistant", "content": resp.content})
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            try:
                out, err = by_name[b.name].fn(**b.input), False
            except Exception as e:  # report the failure to the model instead of crashing
                out, err = {"error": str(e)}, True
            run.calls.append({"turn": run.turns, "name": b.name, "input": b.input, "output": out})
            results.append({"type": "tool_result", "tool_use_id": b.id,
                            "content": json.dumps(out, default=str), "is_error": err})
        msgs.append({"role": "user", "content": results})
    if resp is not None:
        run.final_text = "".join(b.text for b in resp.content if b.type == "text")
    return run
