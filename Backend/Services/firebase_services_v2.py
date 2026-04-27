from importlib.util import find_spec
from pathlib import Path

import dotenv


class FirebaseServiceV2:
    def __init__(self) -> None:
        self.env_path = Path(__file__).parent / ".env"
        self.key_path = None
        self.db_url = None

    def load_env(self) -> None:
        """
        Kiểm tra sự tồn tại của file .env và đọc các biến môi trường cần thiết.
        """
        if find_spec("dotenv") is None:
            raise ModuleNotFoundError(
                "Missing Python dependency 'python-dotenv'. Run: pip install python-dotenv"
            )

        if not self.env_path.exists():
            raise FileNotFoundError(f"Missing .env file at {self.env_path}")

        dotenv_values = dotenv.dotenv_values(self.env_path)
        self.key_path = dotenv_values.get("FIREBASE_KEY_PATH")
        self.db_url = dotenv_values.get("DATABASE_URL")

        if not self.key_path:
            raise ValueError("FIREBASE_KEY_PATH not found in .env")
        if not self.db_url:
            raise ValueError("DATABASE_URL not found in .env")

    def initialize_firebase_connection(self) -> None:
        """
        Kiểm tra thư viện firebase_admin và khởi tạo kết nối Firebase.
        """
        if find_spec("firebase_admin") is None:
            raise ModuleNotFoundError(
                "Missing Python dependency 'firebase_admin'. Run: pip install firebase-admin"
            )

        import firebase_admin  # noqa: F401
        from firebase_admin import credentials, initialize_app

        self.load_env()

        assert self.key_path is not None
        absolute_key_path = (self.env_path.parent / self.key_path).expanduser().resolve()
        if not absolute_key_path.exists():
            raise FileNotFoundError(f"Firebase key not found: {absolute_key_path}")

        try:
            firebase_admin.get_app()
        except ValueError:
            initialize_app(
                credentials.Certificate(str(absolute_key_path)),
                {"databaseURL": self.db_url},
            )

        print("Firebase connection initialized successfully")

    def save_data(self, path: str, data: dict) -> None:
        """
        Lưu dữ liệu vào Firebase Realtime Database tại đường dẫn được chỉ định.
        """
        import firebase_admin  # noqa: F401
        from firebase_admin import db

        ref = db.reference(path)
        ref.set(data)
        print(f"Data saved to Firebase at path: {path}")

    def pull_data(self, path: str) -> dict:
        """
        Lấy dữ liệu từ Firebase Realtime Database tại đường dẫn được chỉ định.
        """
        import firebase_admin  # noqa: F401
        from firebase_admin import db

        ref = db.reference(path)
        data = ref.get()

        

        if data is None:
            print(f"No data found at path: {path}")
            return {}

        return data
