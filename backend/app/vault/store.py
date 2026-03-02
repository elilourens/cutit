import re
import threading
from collections import defaultdict
from typing import Dict

import ollama

from app.config import settings


class VaultStore:
    """In-memory session-scoped vault mapping fake values → real values."""

    def __init__(self):
        self._store: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._real_to_fake: Dict[str, Dict[str, str]] = defaultdict(dict)
        self._lock = threading.Lock()

    def put(self, session_id: str, fake: str, real: str) -> None:
        with self._lock:
            self._store[session_id][fake] = real
            self._real_to_fake[session_id][real] = fake

    def fake_for(self, session_id: str, real: str) -> str | None:
        """Return existing fake for a real value, if any."""
        with self._lock:
            return self._real_to_fake[session_id].get(real)

    def get_session(self, session_id: str) -> Dict[str, str]:
        """Return {fake: real} mapping for the session."""
        with self._lock:
            return dict(self._store.get(session_id, {}))

    def restore(self, session_id: str, text: str) -> str:
        """Replace all fakes in text with their real values (exact match)."""
        mapping = self.get_session(session_id)
        for fake, real in mapping.items():
            text = text.replace(fake, real)
        return text

    async def ollama_restore(self, session_id: str, text: str) -> str:
        """
        Use Ollama to reconstruct text — handles partial names, titles, and
        any variant forms the cloud may have derived from a fake value.
        Falls back to simple string replace on failure.
        """
        mapping = self.get_session(session_id)
        if not mapping:
            return text

        # First do simple replace to catch obvious exact matches
        simple = self.restore(session_id, text)

        # Only include fakes whose full string OR any significant token still
        # appears in the text. This catches "Dr Voss" when the fake was
        # "Dr Elijah Voss", while excluding fakes fully handled by simple replace
        # (e.g. emails where no meaningful token remains).
        _skip_tokens = {"dr", "mr", "mrs", "ms", "prof", "sir", "rev"}
        def _referenced(fake: str) -> bool:
            if fake in simple:
                return True
            text_lower = simple.lower()
            tokens = re.split(r"[\s\-_@.]+", fake.lower())
            return any(t in text_lower for t in tokens if len(t) > 3 and t not in _skip_tokens)

        present = {fake: real for fake, real in mapping.items() if _referenced(fake)}
        if not present:
            return simple

        mapping_lines = "\n".join(f'- "{fake}" → "{real}"' for fake, real in present.items())
        prompt = (
            "You are a find-and-replace engine. "
            "In the text below, substitute each fake placeholder with its real value exactly where it appears. "
            "NEVER add, remove, rephrase, or comment on anything else.\n\n"
            f"Replacements (fake → real):\n{mapping_lines}\n\n"
            "Rules:\n"
            "- Only replace exact occurrences of the fake values listed above.\n"
            "- Output the text with those substitutions made and nothing else changed.\n"
            "- Do NOT add notes, disclaimers, or any text that was not in the original.\n"
            "- Do NOT explain what you did.\n\n"
            f"Text:\n{simple}\n\nOutput:"
        )
        try:
            resp = ollama.generate(
                model=settings.ollama_model,
                prompt=prompt,
                options={"temperature": 0.0},
            )
            result = resp["response"].strip()
            return result if result else simple
        except Exception:
            return simple

    def all_sessions(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return {k: dict(v) for k, v in self._store.items()}

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
            self._real_to_fake.pop(session_id, None)


vault = VaultStore()
