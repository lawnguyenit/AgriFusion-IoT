from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    from Config.env import BACKEND_DIR
except ModuleNotFoundError:
    from ...Config.env import BACKEND_DIR

try:
    import firebase_admin
    from firebase_admin import credentials, db
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Missing Python dependency 'firebase_admin'. Run: pip install -r Backend\\requirements.txt"
    ) from exc


class FirebaseRTDBClient:
    def __init__(self) -> None:
        relative_key_path = os.getenv("FIREBASE_KEY_PATH")
        database_url = os.getenv("DATABASE_URL")

        if not relative_key_path:
            raise ValueError("Missing FIREBASE_KEY_PATH in Backend/.env")
        if not database_url:
            raise ValueError("Missing DATABASE_URL in Backend/.env")

        absolute_key_path = Path(BACKEND_DIR, relative_key_path).resolve()
        if not absolute_key_path.exists():
            raise FileNotFoundError(f"Firebase key not found: {absolute_key_path}")

        if not firebase_admin._apps:
            credentials_payload = credentials.Certificate(str(absolute_key_path))
            firebase_admin.initialize_app(credentials_payload, {"databaseURL": database_url})

        self.root_ref = db.reference("/")

    def pull_data(self, node_path: str = "Node1/telemetry") -> Any:
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

    def pull_sensor_data(self, node_path: str = "Node1") -> Any:
        return self.pull_data(node_path=node_path)

    def set_data(self, node_path: str, payload: Any) -> bool:
        try:
            clean_path = node_path.strip("/") if node_path else ""
            target_ref = self.root_ref.child(clean_path) if clean_path else self.root_ref
            target_ref.set(payload)
            print(f"Set data successfully at '{clean_path or '/'}'")
            return True
        except Exception as exc:
            print(f"Firebase set error: {exc!r}")
            return False

    def delete_data(self, node_path: str) -> bool:
        try:
            clean_path = node_path.strip("/") if node_path else ""
            target_ref = self.root_ref.child(clean_path) if clean_path else self.root_ref
            target_ref.delete()
            print(f"Deleted data successfully at '{clean_path or '/'}'")
            return True
        except Exception as exc:
            print(f"Firebase delete error: {exc!r}")
            return False

    def update_data(self, node_path: str, payload: dict[str, Any]) -> bool:
        try:
            clean_path = node_path.strip("/") if node_path else ""
            target_ref = self.root_ref.child(clean_path) if clean_path else self.root_ref
            target_ref.update(payload)
            print(f"Updated data successfully at '{clean_path or '/'}'")
            return True
        except Exception as exc:
            print(f"Firebase update error: {exc!r}")
            return False
