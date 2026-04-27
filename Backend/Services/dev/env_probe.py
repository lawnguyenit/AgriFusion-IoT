import os
from pathlib import Path

import dotenv



SERVICES_DIR = Path(__file__).resolve().parents[1]
dotenv.load_dotenv(dotenv_path=SERVICES_DIR / ".env", override=False)


def _env_str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    print(f"Environment variable '{name}': {value!r}")
    if value is None:
        return default
    value = value.strip()
    return value or default

if __name__ == "__main__":
    node_id = _env_str("EXPORT_NODE_ID", "Node1") or "Node1"
    node_slug = _env_str("EXPORT_NODE_SLUG") or ""
    print(f"Node ID: {node_id}")
    print(f"Node Slug: {node_slug}")
