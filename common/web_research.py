"""Account research with Claude's web search server tool (build 10).

LIVE    - one messages.create call with the web_search server tool. Anthropic runs the searches; we
          continue on stop_reason == "pause_turn" and collect every result URL the model saw.
OFFLINE - a local, synthetic "search index" scored by keyword overlap, returning the same hit shape.
Either way the caller turns the hits into a schema with common.claude.ask_structured.
"""
from __future__ import annotations

import re
from typing import Callable

from common.claude import MODEL, _client, live

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}


def keyword_search(index: list[dict], query: str, k: int = 5) -> list[dict]:
    """Tiny offline search engine: score = query words found in title (x2) + text."""
    words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 2]
    scored = []
    for doc in index:
        title, text = doc["title"].lower(), doc["text"].lower()
        s = sum(2 * (w in title) + (w in text) for w in words)
        if s:
            scored.append((s, doc))
    return [d for _, d in sorted(scored, key=lambda x: -x[0])[:k]]


def research(company: str, queries: list[str], offline_search: Callable[[str], list[dict]]) -> dict:
    """Return {"text": findings written by the model (LIVE) or '', "hits": [{title,url,date,text,query}]}."""
    if not live():
        hits, seen = [], set()
        for q in queries:
            for h in offline_search(q):
                if h["url"] not in seen:
                    seen.add(h["url"])
                    hits.append({**h, "query": q})
        return {"text": "", "hits": hits}

    client = _client()
    msgs = [{"role": "user", "content": (
        f"Research the company '{company}' for a sales proposal. Run these searches: {queries}. "
        "Report recent news (last 6 months), hiring signals and tech stack. For each finding give the "
        "source URL and date. Ignore results about other companies with similar names.")}]
    blocks: list = []
    for _ in range(4):  # server tool loop: send the partial turn back while the API pauses it
        resp = client.messages.create(model=MODEL, max_tokens=16000, tools=[WEB_SEARCH_TOOL], messages=msgs)
        blocks += resp.content
        if resp.stop_reason != "pause_turn":
            break
        msgs = msgs[:1] + [{"role": "assistant", "content": blocks}]
    text, hits = [], []
    for b in blocks:
        if b.type == "text":
            text.append(b.text)
        elif b.type == "web_search_tool_result" and isinstance(b.content, list):
            hits += [{"title": r.title, "url": r.url, "date": getattr(r, "page_age", None) or "", "text": "",
                      "query": ""} for r in b.content]
    return {"text": "".join(text), "hits": hits}
