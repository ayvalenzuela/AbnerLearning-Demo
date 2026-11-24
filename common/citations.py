"""Claude citations helper (document blocks with citations enabled).

Citations cannot be combined with structured output, so this returns the response as a
list of text blocks, each carrying the passages it cites. Callers parse the text.

LIVE    - sends each document as a {"type": "document", ..., "citations": {"enabled": True}}
          content block and reads `.citations` (cited_text, document_title) off each text block.
OFFLINE - the caller's rule-based stand-in returns blocks in the same shape.
"""
from __future__ import annotations

from typing import Callable

from pydantic import BaseModel

from common.claude import MODEL, _client, live


class Citation(BaseModel):
    cited_text: str
    document_title: str


class CitedBlock(BaseModel):
    text: str
    citations: list[Citation] = []


def ask_cited(
    *,
    system: str,
    documents: list[dict],
    prompt: str,
    offline: Callable[[], list[CitedBlock]],
    max_tokens: int = 8000,
) -> list[CitedBlock]:
    """documents: [{"title": str, "text": str}]. Returns the answer as cited text blocks."""
    if not live():
        return offline()
    content = [
        {
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": d["text"]},
            "title": d["title"],
            "citations": {"enabled": True},
        }
        for d in documents
    ]
    content.append({"type": "text", "text": prompt})
    resp = _client().messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": content}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined this request")
    out: list[CitedBlock] = []
    for b in resp.content:
        if b.type != "text":
            continue
        cites = [
            Citation(cited_text=c.cited_text, document_title=getattr(c, "document_title", None) or "")
            for c in (getattr(b, "citations", None) or [])
        ]
        out.append(CitedBlock(text=b.text, citations=cites))
    return out
