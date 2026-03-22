from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ExportSettings:
    services_dir: Path = field(default_factory=lambda: Path(__file__).resolve().parent)
    node_id: str = "Node2"
    node_slug: str = "node2"
    latest_meta_path: str = "Node2/latest/meta"
    latest_current_path: str = "Node2/latest/current"
    telemetry_root_path: str = "Node2/telemetry"
    timezone_name: str = "Asia/Ho_Chi_Minh"
    primary_poll_after_sec: int = 3900
    retry_after_no_change_sec: int = 300
    no_change_retry_limit: int = 1

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def server_dir(self) -> Path:
        return self.services_dir.parent

    @property
    def base_dir(self) -> Path:
        return self.server_dir / "Firebase_data"

    @property
    def new_raw_dir(self) -> Path:
        return self.base_dir / "new_raw"

    @property
    def latest_payload_path(self) -> Path:
        return self.new_raw_dir / "latest.json"

    @property
    def latest_meta_local_path(self) -> Path:
        return self.new_raw_dir / "latest_meta.json"

    @property
    def sync_state_path(self) -> Path:
        return self.new_raw_dir / "sync_state.json"

    @property
    def history_root(self) -> Path:
        return self.base_dir / "history"


SETTINGS = ExportSettings()
