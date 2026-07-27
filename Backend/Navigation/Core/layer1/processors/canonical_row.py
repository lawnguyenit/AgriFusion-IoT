from __future__ import annotations

from ..contracts import SourceRecord
from .common import as_dict, tri_or
from .context import build_record_and_context_fields
from .npk.canonical import extract_npk_fields
from .sht30.canonical import extract_sht30_fields
from .status import build_sensor_branch


class CanonicalRowBuilder:
    def build(self, source_record: SourceRecord) -> dict[str, object]:
        payload = source_record.payload
        packet = as_dict(payload.get("packet"))
        sensors = as_dict(payload.get("sensors"))
        packet_sht = as_dict(packet.get("sht30_data"))
        packet_npk = as_dict(packet.get("npk_data"))
        sensor_sht = as_dict(sensors.get("sht30"))
        sensor_npk = as_dict(sensors.get("npk"))

        packet_present_sht = bool(packet_sht)
        packet_present_npk = bool(packet_npk)

        context_fields = build_record_and_context_fields(source_record)
        sht_fields = extract_sht30_fields(packet_sht)
        npk_fields = extract_npk_fields(packet_npk)
        sht_status = build_sensor_branch(
            packet_present=packet_present_sht,
            sensor_status=sensor_sht,
            normalized_prefix="sht",
        )
        npk_status = build_sensor_branch(
            packet_present=packet_present_npk,
            sensor_status=sensor_npk,
            normalized_prefix="npk",
            protocol_flags=(
                npk_fields["npk.crc_ok"],
                npk_fields["npk.frame_ok"],
                npk_fields["npk.signal_present"],
                npk_fields["npk.values_valid"],
            ),
        )

        row: dict[str, object] = {}
        for key, value in context_fields.items():
            if key.startswith("record."):
                row[key] = value
        row["sensor.any_fault"] = tri_or(sht_status["sht.fault"], npk_status["npk.fault"])
        row["sensor.all_packets_missing"] = (not packet_present_sht) and (not packet_present_npk)
        for key, value in context_fields.items():
            if not key.startswith("record."):
                row[key] = value
        row.update(sht_fields)
        row.update(npk_fields)
        row.update(sht_status)
        row.update(npk_status)
        return row
