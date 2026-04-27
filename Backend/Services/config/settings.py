import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from zoneinfo import ZoneInfo

from .env import SERVICES_DIR, coerce_optional_path, env_int, env_path, env_str


def _slugify_node(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "node"


@dataclass(frozen=True)
class ExportSettings:
    services_dir: Path = field(default_factory=lambda: SERVICES_DIR)
    server_base_dir: Path | None = None
    source_type: str = field(default_factory=lambda: env_str("EXPORT_SOURCE", "firebase") or "firebase")
    input_json_path: Path | None = field(default_factory=lambda: env_path("EXPORT_INPUT_JSON"))
    node_id: str = field(default_factory=lambda: env_str("EXPORT_NODE_ID", "Node1") or "Node1")
    node_slug: str = field(default_factory=lambda: env_str("EXPORT_NODE_SLUG") or "")
    
    timezone_name: str = field(
        default_factory=lambda: env_str("EXPORT_TIMEZONE", "Asia/Ho_Chi_Minh") or "Asia/Ho_Chi_Minh"
    )
    primary_poll_after_sec: int = field(
        default_factory=lambda: env_int("EXPORT_PRIMARY_POLL_AFTER_SEC", 3900)
    )
    retry_after_no_change_sec: int = field(
        default_factory=lambda: env_int("EXPORT_RETRY_AFTER_NO_CHANGE_SEC", 300)
    )
    no_change_retry_limit: int = field(
        default_factory=lambda: env_int("EXPORT_NO_CHANGE_RETRY_LIMIT", 1)
    )
    npk_sensor_id: str = field(
        default_factory=lambda: env_str("EXPORT_NPK_SENSOR_ID", "npk_7in1_1") or "npk_7in1_1"
    )
    npk_sensor_type: str = field(
        default_factory=lambda: env_str("EXPORT_NPK_SENSOR_TYPE", "npk7in1") or "npk7in1"
    )
    sht30_sensor_id: str = field(
        default_factory=lambda: env_str("EXPORT_SHT30_SENSOR_ID", "sht30_1") or "sht30_1"
    )
    sht30_sensor_type: str = field(
        default_factory=lambda: env_str("EXPORT_SHT30_SENSOR_TYPE", "sht30_air") or "sht30_air"
    )

    def __post_init__(self) -> None:
        normalized_source = self.source_type.strip().lower()
        if normalized_source not in {"firebase", "json-export"}:
            raise ValueError(f"Unsupported export source '{self.source_type}'")
        object.__setattr__(self, "source_type", normalized_source)

        resolved_server_base_dir = (
            self.services_dir.parent if self.server_base_dir is None else Path(self.server_base_dir)
        )
        object.__setattr__(self, "server_base_dir", resolved_server_base_dir.resolve())

        if self.input_json_path is not None:
            object.__setattr__(
                self,
                "input_json_path",
                coerce_optional_path(self.input_json_path).resolve(),
            )

        if not self.node_slug:
            object.__setattr__(self, "node_slug", _slugify_node(self.node_id))

    def with_overrides(self, **kwargs: object) -> "ExportSettings":
        return replace(
            self,
            **{key: value for key, value in kwargs.items() if value is not None},
        )

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @property
    def server_dir(self) -> Path:
        return self.server_base_dir

    @property
    def output_data_root(self) -> Path:
        return self.server_dir / "Output_data"

    @property
    def layer1_root(self) -> Path:
        return self.output_data_root / "Layer1"

    @property
    def layer2_root(self) -> Path:
        return self.output_data_root / "Layer2"

    @property
    def layer25_root(self) -> Path:
        return self.output_data_root / "Layer2.5"

    @property
    def base_dir(self) -> Path:
        return self.layer1_root / "Firebase_data"

    @property
    def openmeteo_root(self) -> Path:
        return self.layer1_root / "OpenMeteo_Data"

    @property
    def meteo_data_root(self) -> Path:
        return self.openmeteo_root / "Meteo_data"

    @property
    def latest_meta_path(self) -> str:
        return f"{self.node_id}/latest/meta"

    @property
    def latest_current_path(self) -> str:
        return f"{self.node_id}/latest/current"

    @property
    def telemetry_root_path(self) -> str:
        return f"{self.node_id}/telemetry"

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
    def source_snapshot_path(self) -> Path:
        return self.new_raw_dir / "source_snapshot.json"

    @property
    def source_manifest_path(self) -> Path:
        return self.new_raw_dir / "source_manifest.json"

    @property
    def history_root(self) -> Path:
        return self.base_dir / "history"


SETTINGS = ExportSettings()
