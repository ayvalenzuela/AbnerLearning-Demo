"""Vision + structured output through the Message Batches API.

common.claude.batch_structured only sends text. This helper sends each item as an image
content block (base64 PNG/JPEG) plus text, and asks for JSON matching a Pydantic schema.
OFFLINE it calls the `offline` stand-in, which receives the image path so it can do real
pixel analysis (e.g. with Pillow) instead of returning canned answers.
"""
from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Callable, Type, TypeVar

from pydantic import BaseModel

from common.claude import MODEL, _client, _strict_schema, live

T = TypeVar("T", bound=BaseModel)


def image_block(path: str | Path) -> dict:
    p = Path(path)
    media = mimetypes.guess_type(p.name)[0] or "image/png"
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media,
                   "data": base64.standard_b64encode(p.read_bytes()).decode()},
    }


def batch_vision_structured(
    *,
    system: str,
    items: dict[str, dict],
    schema: Type[T],
    offline: Callable[[str, str, Path], T],
    poll_seconds: int = 20,
    max_tokens: int = 4000,
) -> dict[str, T]:
    """items: custom_id -> {"text": str, "image": path}. Returns custom_id -> parsed schema."""
    if not live():
        return {cid: offline(cid, it["text"], Path(it["image"])) for cid, it in items.items()}
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
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user",
                               "content": [image_block(it["image"]), {"type": "text", "text": it["text"]}]}],
                    output_config=fmt,
                ),
            )
            for cid, it in items.items()
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
