"""Persistent conversation history for AI Coach — survives restarts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

_HISTORY_DIR = Path(__file__).resolve().parents[2] / "data" / "ai_history"


class ConversationStore:
    """Stores and retrieves AI Coach conversations.

    Each conversation is saved as a separate JSON file in ``data/ai_history/``.
    Files are named by timestamp: ``{iso_timestamp}_{slug}.json``.
    """

    def __init__(self, history_dir: str | Path | None = None) -> None:
        self._dir = Path(history_dir or _HISTORY_DIR)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def save_conversation(
        self,
        messages: list[dict[str, str]],
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Save a conversation to disk.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            metadata: Optional dict with "goals", "focus", "label", etc.

        Returns:
            The file path of the saved conversation.
        """
        if not messages:
            return ""

        now = datetime.now()
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        label = (metadata or {}).get("label", "")
        slug = _to_slug(label) if label else _first_topic(messages)

        filename = f"{timestamp}_{slug}.json"
        path = self._dir / filename

        payload = {
            "saved_at": now.isoformat(),
            "message_count": len(messages),
            "metadata": metadata or {},
            "messages": messages,
        }

        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return str(path)

    def load_conversation(self, filepath: str | Path) -> list[dict[str, str]] | None:
        """Load a conversation from a file."""
        path = Path(filepath)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return data.get("messages", [])
        except (json.JSONDecodeError, KeyError):
            return None

    def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent conversations, newest first.

        Each entry: {"path": ..., "date": ..., "label": ..., "messages": N, "metadata": ...}
        """
        files = sorted(self._dir.iterdir(), reverse=True)[:limit]
        result = []
        for f in files:
            if f.suffix != ".json":
                continue
            try:
                data = json.loads(f.read_text())
                meta = data.get("metadata", {})
                result.append({
                    "path": str(f),
                    "date": meta.get("date", data.get("saved_at", f.stem[:15])),
                    "label": meta.get("label", f.stem[16:]),
                    "messages": data.get("message_count", len(data.get("messages", []))),
                    "metadata": meta,
                })
            except (json.JSONDecodeError, OSError):
                continue
        return result

    def delete_conversation(self, filepath: str | Path) -> bool:
        """Delete a saved conversation."""
        path = Path(filepath)
        if path.exists():
            path.unlink()
            return True
        return False

    @property
    def count(self) -> int:
        return len(list(self._dir.glob("*.json")))


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _to_slug(text: str) -> str:
    """Convert text to a filename-safe slug."""
    clean = "".join(c if c.isalnum() or c in " -_" else "" for c in text.lower())
    return clean.strip().replace(" ", "_")[:40] or "conversation"


def _first_topic(messages: list[dict[str, str]]) -> str:
    """Extract a short topic from the first user message."""
    for msg in messages:
        if msg.get("role") == "user":
            text = msg["content"][:60].strip()
            return _to_slug(text)
    return "conversation"
