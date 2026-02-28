import threading
from collections import defaultdict
from typing import Dict


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
        """Replace all fakes in text with their real values."""
        mapping = self.get_session(session_id)
        for fake, real in mapping.items():
            text = text.replace(fake, real)
        return text

    def all_sessions(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            return {k: dict(v) for k, v in self._store.items()}

    def clear_session(self, session_id: str) -> None:
        with self._lock:
            self._store.pop(session_id, None)
            self._real_to_fake.pop(session_id, None)


vault = VaultStore()
