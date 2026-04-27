import os

from dotenv import load_dotenv

try:
    import firebase_admin
    from firebase_admin import credentials, db
except ModuleNotFoundError as exc:
    raise ModuleNotFoundError(
        "Missing Python dependency 'firebase_admin'. Run: pip install -r SERVER\\requirements.txt"
    ) from exc


class FirebaseService:
    def __init__(self):
        current_dir = os.path.dirname(__file__)
        dotenv_path = os.path.join(current_dir, ".env")

        load_dotenv(dotenv_path=dotenv_path)

        relative_key_path = os.getenv("FIREBASE_KEY_PATH")
        db_url = os.getenv("DATABASE_URL")

        if not relative_key_path:
            raise ValueError("Missing FIREBASE_KEY_PATH in Services/.env")
        if not db_url:
            raise ValueError("Missing DATABASE_URL in Services/.env")

        absolute_key_path = os.path.abspath(os.path.join(current_dir, relative_key_path))
        if not os.path.exists(absolute_key_path):
            raise FileNotFoundError(f"Firebase key not found: {absolute_key_path}")

        if not firebase_admin._apps:
            cred = credentials.Certificate(absolute_key_path)
            firebase_admin.initialize_app(cred, {"databaseURL": db_url})

        self.root_ref = db.reference("/")

    def pull_data(self, node_path: str = "Node1/telemetry"):
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

    def pull_sensor_data(self, node_path: str = "Node1"):
        return self.pull_data(node_path=node_path)
