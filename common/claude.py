"""Shared Claude helper used by all ten builds.

Two modes:
  LIVE    - ANTHROPIC_API_KEY is set: calls the real Claude API (structured output via
            client.messages.parse, Batches API, vision, citations).
  OFFLINE - no key: a deterministic, rule-based stand-in produces output with the SAME
            schema, so the whole pipeline (data -> code -> AI step -> checks -> output)
            runs end to end on any laptop. Every trace step is labelled with its mode,
            so nobody mistakes offline output for model output.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Type, TypeVar

from pydantic import BaseModel

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
T = TypeVar("T", bound=BaseModel)


def live() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and os.environ.get("FORCE_OFFLINE") != "1"


def mode() -> str:
    return "LIVE (Claude API)" if live() else "OFFLINE (rule-based stand-in, same schema)"


def _client():
    import anthropic  # imported lazily so offline mode needs no SDK

    return anthropic.Anthropic()


def ask_structured(
    *,
    system: str,
    content: str | list,
    schema: Type[T],
    offline: Callable[[], T],
    max_tokens: int = 16000,
) -> T:
    """One Claude call that must return JSON matching `schema` (a Pydantic model)."""
    if not live():
        return offline()
    resp = _client().messages.parse(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=schema,
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request")
    return resp.parsed_output


def batch_structured(
    *,
    system: str,
    items: dict[str, str],
    schema: Type[T],
    offline: Callable[[str, str], T],
    poll_seconds: int = 20,
) -> dict[str, T]:
    """Run many structured calls through the Message Batches API (50% cheaper, async).

    `items` maps custom_id -> user prompt. Results are keyed by custom_id (never by order).
    """
    if not live():
        return {cid: offline(cid, text) for cid, text in items.items()}
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    client = _client()
    fmt = {"format": {"type": "json_schema", "schema": _strict_schema(schema)}}
    batch = client.messages.batches.create(
        requests=[
            Request(
                custom_id=cid,
                params=MessageCreateParamsNonStreaming(
                    model=MODEL,
                    max_tokens=4000,
                    system=system,
                    messages=[{"role": "user", "content": text}],
                    output_config=fmt,
                ),
            )
            for cid, text in items.items()
        ]
    )
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(poll_seconds)
    out: dict[str, T] = {}
    for r in client.messages.batches.results(batch.id):
        if r.result.type == "succeeded":
            text = "".join(b.text for b in r.result.message.content if b.type == "text")
            out[r.custom_id] = schema.model_validate_json(text)
    return out


def _strict_schema(schema: Type[BaseModel]) -> dict:
    s = schema.model_json_schema()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                node["additionalProperties"] = False
                node.setdefault("required", list(node.get("properties", {}).keys()))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(s)
    return s


class Trace:
    """Records every pipeline step so the portfolio site can replay the build visually."""

    def __init__(self, build_id: str, title: str, out_dir: Path):
        self.data = {"build": build_id, "title": title, "mode": mode(), "model": MODEL, "steps": []}
        self.out_dir = out_dir
        out_dir.mkdir(parents=True, exist_ok=True)

    def step(self, title: str, *, what: str, code: str = "", output=None, kind: str = "code"):
        """kind: code | ai | human | check | io"""
        if not isinstance(output, str):
            output = json.dumps(output, indent=2, default=str)
        n = len(self.data["steps"]) + 1
        self.data["steps"].append(
            {"n": n, "title": title, "kind": kind, "what": what, "code": code.strip(), "output": output}
        )
        tag = {"ai": "CLAUDE", "human": "HUMAN", "check": "CHECK", "io": "DATA"}.get(kind, "CODE")
        print(f"\n[{n}] {tag} | {title}\n    {what}")
        preview = output if len(output) < 900 else output[:900] + "\n    ..."
        print("    " + preview.replace("\n", "\n    "))

    def arch(self, nodes: list[dict]):
        """Architecture diagram as an ordered flow: [{"label": str, "kind": data|code|ai|human|system, "note": str}]"""
        self.data["arch"] = nodes

    def story(self, **kv):
        """Case-study text: situation, constraints, replay (str each), problem_cost (str)."""
        self.data["story"] = kv

    def metrics(self, **kv):
        self.data["metrics"] = kv
        print("\nRESULTS:", json.dumps(kv, indent=2))

    def save(self):
        p = self.out_dir / "trace.json"
        p.write_text(json.dumps(self.data, indent=2, default=str))
        print(f"\nTrace written to {p}")
