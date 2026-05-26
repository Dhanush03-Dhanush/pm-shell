from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def open_editor(initial_text: str = "", *, suffix: str = ".md") -> Optional[str]:
    # Returns None if the editor exits non-zero or saves an empty file.
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vi"
    if not sys.stdin.isatty():
        raise RuntimeError(
            "Cannot open $EDITOR in a non-interactive shell. "
            "Pass the text inline instead."
        )

    with tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False) as tf:
        tf.write(initial_text)
        path = Path(tf.name)

    try:
        cmd = shlex.split(editor) + [str(path)]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            return None
        text = path.read_text(encoding="utf-8")
        return text if text.strip() else None
    finally:
        try:
            path.unlink()
        except OSError:
            pass
