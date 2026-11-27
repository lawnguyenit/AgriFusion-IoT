from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agrifusion.settings.env import PROJECT_ROOT


def _firebase_modules() -> tuple[Any, Any, Any]:
    """Import firebase_admin lazily: importing this module must not require it."""
    try:
        import firebase_admin
        from firebase_admin import credentials, db
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Missing Python dependency 'firebase_admin'. Run: python -m pip install -e ."
        ) from exc
    return firebase_admin, credentials, db


class FirebaseRTDBClient:
    def __init__(self) -> None:
        firebase_admin, credentials, db = _firebase_modules()
        configured_key_path = os.getenv("FIREBASE_KEY_PATH")
        database_url = os.getenv("DATABASE_URL")

        if not configured_key_path:
            raise ValueError("Missing FIREBASE_KEY_PATH in .env")
        if not database_url:
            raise ValueError("Missing DATABASE_URL in .env")

        absolute_key_path = self._resolve_key_path(configured_key_path)
        if not absolute_key_path.exists():
            raise FileNotFoundError(f"Firebase key not found: {absolute_key_path}")

        if not firebase_admin._apps:
            credentials_payload = credentials.Certificate(str(absolute_key_path))
            firebase_admin.initialize_app(credentials_payload, {"databaseURL": database_url})

        self.root_ref = db.reference("/")

    def pull_data(self, node_path: str) -> Any:
        try:
            clean_path = node_path.strip("/") if node_path else ""
            target_ref = self.root_ref.child(clean_path) if clean_path else self.root_ref
            data = target_ref.get()
            if data is not None:
                print(f"Pulled data successfully from '{clean_path or '/'}'")
                return data
            print(f"Node '{clean_path or '/'}' has no data")
            return None
        except Exception as exc:
            print(f"Firebase pull error: {exc!r}")
            return None

    def read(self, node_path: str) -> Any:
        """Strict read: unlike ``pull_data`` it raises on errors (None means the node is empty)."""
        clean_path = node_path.strip("/") if node_path else ""
        target_ref = self.root_ref.child(clean_path) if clean_path else self.root_ref
        return target_ref.get()

    def update(self, paths: dict[str, Any]) -> None:
        """One atomic multi-path update. Keys are paths relative to the root; a ``None`` value deletes."""
        if not paths:
            return
        self.root_ref.update(paths)

    @staticmethod
    def _resolve_key_path(configured_key_path: str) -> Path:
        candidate = Path(configured_key_path).expanduser()
        if candidate.is_absolute():
            return candidate.resolve()

        root_relative = (PROJECT_ROOT / candidate).resolve()
        if root_relative.exists():
            return root_relative

        # Legacy: key paths used to be relative to Backend/ (and Backend/Services/).
        legacy_backend_relative = (PROJECT_ROOT / "Backend" / candidate).resolve()
        if legacy_backend_relative.exists():
            return legacy_backend_relative

        legacy_services_relative = (PROJECT_ROOT / "Backend" / "Services" / candidate).resolve()
        if legacy_services_relative.exists():
            return legacy_services_relative

        return root_relative
