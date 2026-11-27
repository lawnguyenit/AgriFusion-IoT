from __future__ import annotations

import json
from pathlib import Path


def load_segment_manifest(layer1_manifest_path: Path | None) -> tuple[Path, dict[str, object]]:
    if layer1_manifest_path is None:
        raise ValueError("This dataset view requires a Layer1 manifest so the segment cadence can be loaded.")
    if not layer1_manifest_path.exists():
        raise ValueError(f"Layer1 manifest not found: {layer1_manifest_path}")

    layer1_manifest = json.loads(layer1_manifest_path.read_text(encoding="utf-8"))
    candidate_paths: list[Path] = []

    output_paths = layer1_manifest.get("output_paths")
    if isinstance(output_paths, dict):
        segment_manifest_value = output_paths.get("segment_manifest_path")
        if isinstance(segment_manifest_value, str) and segment_manifest_value.strip():
            candidate_paths.append(Path(segment_manifest_value))

    candidate_paths.append(layer1_manifest_path.parent / "segments" / "segments_manifest.json")
    candidate_paths.append(layer1_manifest_path.parent / "segments_manifest.json")

    for candidate_path in candidate_paths:
        if candidate_path.exists():
            payload = json.loads(candidate_path.read_text(encoding="utf-8"))
            segments = payload.get("segments")
            if not isinstance(segments, list):
                raise ValueError(f"Invalid segment manifest structure at {candidate_path}: missing 'segments' list.")
            return candidate_path, payload

    searched = ", ".join(str(path) for path in candidate_paths)
    raise ValueError(
        "This dataset view requires a Layer1 segment manifest, but none was found. "
        f"Searched: {searched}"
    )
