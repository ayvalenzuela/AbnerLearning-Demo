"""Content blocks for sending a mixed document packet (PDFs, photos, text) to Claude in one call.

Used by build 09 (claims intake). The blocks go straight into common.claude.ask_structured(content=...),
so vision extraction gets the same schema-checked output and the same OFFLINE fallback as every build.
"""
from __future__ import annotations

import base64
from pathlib import Path

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
               ".gif": "image/gif"}


def _b64(path: Path) -> str:
    return base64.standard_b64encode(Path(path).read_bytes()).decode()


def image_block(path: Path) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[Path(path).suffix.lower()],
                                        "data": _b64(path)}}


def pdf_block(path: Path, title: str | None = None) -> dict:
    block = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": _b64(path)}}
    if title:
        block["title"] = title
    return block


def packet_content(files: list[Path], instructions: str) -> list[dict]:
    """PDFs become document blocks, images become image blocks, text files are inlined with their name."""
    blocks: list[dict] = []
    for f in files:
        f = Path(f)
        if f.suffix.lower() == ".pdf":
            blocks.append(pdf_block(f, title=f.name))
        elif f.suffix.lower() in IMAGE_TYPES:
            blocks.append({"type": "text", "text": f"Attachment: {f.name}"})
            blocks.append(image_block(f))
        else:
            blocks.append({"type": "text", "text": f"--- {f.name} ---\n{f.read_text()}"})
    blocks.append({"type": "text", "text": instructions})
    return blocks
