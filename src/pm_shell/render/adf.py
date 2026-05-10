from __future__ import annotations

from typing import Any

# Block-level node types — each contributes a paragraph break in plain rendering.
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
    """Best-effort ADF (Atlassian Document Format) → plain text.

    Round-trip fidelity is not the goal; this is for terminal display only.
    """
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
