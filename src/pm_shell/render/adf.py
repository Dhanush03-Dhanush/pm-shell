from __future__ import annotations

from typing import Any, Optional

# Each block-level type contributes a paragraph break in plain rendering.
_BLOCK_NODES = {
    "doc",
    "paragraph",
    "heading",
    "blockquote",
    "bulletList",
    "orderedList",
    "listItem",
    "codeBlock",
    "panel",
    "rule",
}

_BULLET_PREFIX = "  - "


def adf_to_plain(node: Any) -> str:
    # Best-effort ADF → plain text for terminal display; not round-trip fidelity.
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")

    if node_type == "text":
        return node.get("text", "")
    if node_type == "hardBreak":
        return "\n"
    if node_type == "rule":
        return "\n---\n"

    children = node.get("content") or []
    parts = [adf_to_plain(c) for c in children]
    inner = "".join(parts)

    if node_type == "listItem":
        return _BULLET_PREFIX + inner.strip() + "\n"
    if node_type in ("paragraph", "heading"):
        return inner.strip() + "\n"
    if node_type == "codeBlock":
        return "\n" + inner.rstrip() + "\n"
    if node_type in _BLOCK_NODES:
        return inner

    return inner


def plain_to_adf(text: Optional[str]) -> Optional[dict[str, Any]]:
    # Empty input → None so the field round-trips to a cleared description.
    if text is None:
        return None
    cleaned = text.strip("\n")
    if not cleaned.strip():
        return None
    paragraphs = [p for p in cleaned.split("\n\n")]
    content = []
    for para in paragraphs:
        if not para.strip():
            continue
        content.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": para}],
            }
        )
    return {"type": "doc", "version": 1, "content": content}
