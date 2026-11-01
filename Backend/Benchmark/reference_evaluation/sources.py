"""Official raw-release intake and two explicit recorded-hour adapters."""
from pathlib import Path
import io
import json
import re
import shutil
import urllib.request
import uuid
import zipfile
import numpy as np
import pandas as pd
from .storage import atomic_json, now, sha256


def acquire_source(source, output_root, download=False, local_archive=None):
    folder = Path(output_root) / "raw" / source["dataset_id"]
    folder.mkdir(parents=True, exist_ok=True)
    pointer = folder / "LATEST.json"
    if local_archive:
        local = Path(local_archive).resolve()
        if not local.is_file():
            raise FileNotFoundError(local)
        key = sha256(local); release = folder / key
        release.mkdir(exist_ok=True)
        target = release / ("source.csv" if local.suffix.lower() == ".csv" else "source.zip")
        if not target.exists():
            shutil.copyfile(local, target)
        if sha256(target) != key:
            raise ValueError("Raw archive at its checksum-addressed path changed")
        origin = {"kind": "local_archive", "path": str(local)}
    elif pointer.exists():
        saved = json.loads(pointer.read_text())
        target = folder / saved["relative_path"]
        if not target.is_file() or sha256(target) != saved["sha256"]:
            raise ValueError("Immutable raw release changed/missing")
        return target, target.parent / "raw_manifest.json"
    elif download:
        temp = folder / ("download_" + uuid.uuid4().hex + ".partial")
        request = urllib.request.Request(source["download_url"], headers={"User-Agent": "AgriFusion-reference-evaluation/1"})
        with urllib.request.urlopen(request, timeout=90) as response, temp.open("wb") as f:
            shutil.copyfileobj(response, f)
        key = sha256(temp); release = folder / key; release.mkdir(exist_ok=True)
        target = release / "source.zip"
        if target.exists():
            if sha256(target) != key:
                raise ValueError("Raw checksum conflict")
            temp.unlink()
        else:
            temp.replace(target)
        origin = {"kind": "official_download", "url": source["download_url"]}
    else:
        raise FileNotFoundError(f"No raw release for {source['dataset_id']}; run audit --download or set runtime.local_archives")
    manifest = target.parent / "raw_manifest.json"
    value = {"dataset_id": source["dataset_id"], "doi": source["doi"],
             "official_landing_url": source["landing_url"], "official_download_url": source["download_url"],
             "acquired_at_utc": now(), "origin": origin, "file_name": target.name,
             "bytes": target.stat().st_size, "sha256": sha256(target),
             "license_reference": "See the official catalog; preserve its attribution and license metadata."}
    if not manifest.exists():
        atomic_json(manifest, value)
    elif json.loads(manifest.read_text())["sha256"] != value["sha256"]:
        raise ValueError("Raw manifest checksum conflict")
    atomic_json(pointer, {"relative_path": target.relative_to(folder).as_posix(), "sha256": value["sha256"]})
    return target, manifest


def _zip_members(payload, prefix="", depth=0):
    if depth > 3:
        raise ValueError("Unexpected nested archive depth")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name in sorted(archive.namelist()):
            if name.endswith("/"):
                continue
            if name.lower().endswith(".zip"):
                yield from _zip_members(archive.read(name), prefix + name + "!", depth+1)
            elif name.lower().endswith(".csv"):
                yield prefix + name, archive.read(name)


def read_beijing(path, expected_station_count=12):
    pieces = []; members = []
    for name, payload in _zip_members(Path(path).read_bytes()):
        if not re.search(r"(?:^|[!/])PRSA_Data_[^/!]+_20130301-20170228\.csv$", name):
            continue
        frame = pd.read_csv(io.BytesIO(payload))
        required = ["year", "month", "day", "hour", "station", "PM2.5"]
        if not set(required) <= set(frame):
            raise ValueError(f"Unexpected PRSA schema: {name}")
        timestamp = pd.to_datetime(frame[["year", "month", "day", "hour"]], errors="raise")
        entity = frame["station"].astype(str)
        if entity.nunique() != 1:
            raise ValueError("One station is required per PRSA member")
        keys = [f"beijing501:{s}:{i+1}" for i, s in enumerate(entity)]
        pieces.append(pd.DataFrame({"sample_id": keys, "entity": entity,
                                   "timestamp": timestamp.astype("int64"),
                                   "value": pd.to_numeric(frame["PM2.5"], errors="coerce"),
                                   "source_rows": [json.dumps([f"{name}:row:{i+1}"]) for i in range(len(frame))],
                                   "source_member": name, "source_max_timestamp": timestamp.astype("int64")}))
        members.append(name)
    if not pieces:
        raise ValueError("No official PRSA station CSV found; unrelated CSVs are not accepted")
    result = pd.concat(pieces, ignore_index=True)
    if len(members) != expected_station_count or result.entity.nunique() != expected_station_count:
        raise ValueError(f"Expected {expected_station_count} distinct PRSA station files")
    return result, {"adapter": "beijing-recorded-hour-v1", "members": members,
                    "time_basis": "source recorded wall time; no UTC assignment", "raw_rows": len(result)}


def read_appliances(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        payload, member = path.read_bytes(), path.name
    else:
        matches = [(n, b) for n, b in _zip_members(path.read_bytes())
                   if n.split("!")[-1].split("/")[-1] == "energydata_complete.csv"]
        if len(matches) != 1:
            raise ValueError("Expected exactly one energydata_complete.csv")
        member, payload = matches[0]
    frame = pd.read_csv(io.BytesIO(payload))
    if not {"date", "RH_1"} <= set(frame):
        raise ValueError("Appliances input requires date and RH_1")
    times = pd.to_datetime(frame["date"], errors="raise")
    if times.duplicated().any() or (times.dt.second != 0).any() or (times.dt.minute % 10 != 0).any() or (times.dt.microsecond != 0).any() or (times.dt.nanosecond != 0).any():
        raise ValueError("Duplicate or non-10-minute Appliances timestamp")
    frame = pd.DataFrame({"time": times, "value": pd.to_numeric(frame["RH_1"], errors="coerce"),
                          "source_row": np.arange(1, len(frame)+1)})
    frame["bin"] = frame.time.dt.floor("h")
    groups = {key: g for key, g in frame.groupby("bin", sort=True)}
    rows = []; incomplete = 0
    for start in pd.date_range(frame.time.min().floor("h"), frame.time.max().floor("h"), freq="h"):
        group = groups.get(start)
        ok = group is not None and len(group) == 6 and set(group.time.dt.minute) == set(range(0, 60, 10)) and np.isfinite(group.value).all()
        end = start + pd.Timedelta(hours=1)
        source_ids = [] if group is None else [f"{member}:row:{int(i)}" for i in group.source_row]
        rows.append({"sample_id": f"appliances374:house1:{end.isoformat()}", "entity": "house_1",
                     "timestamp": end.value, "value": float(group.value.mean()) if ok else np.nan,
                     "source_rows": json.dumps(source_ids), "source_member": member,
                     "source_min_timestamp": int(group.time.min().value) if group is not None else None,
                     "source_max_timestamp": int(group.time.max().value) if group is not None else None,
                     "bin_start": start.value, "bin_end": end.value,
                     "raw_slot_count": len(group) if group is not None else 0,
                     "valid_slot_count": int(np.isfinite(group.value).sum()) if group is not None else 0,
                     "aggregation_version": "hour_mean_six_slots_v1"})
        incomplete += int(not ok)
    return pd.DataFrame(rows), {"adapter": "appliances-hour-mean-six-slots-v1", "raw_rows": len(frame),
                               "canonical_rows": len(rows), "incomplete_bins": incomplete,
                               "time_basis": "source recorded wall time; no UTC assignment",
                               "bin_policy": "[h,h+1), label at h+1; six finite unique slots required"}


def read_source(source, path):
    if source["dataset_id"] == "beijing_multi_site_501":
        return read_beijing(path)
    if source["dataset_id"] == "appliances_energy_374":
        return read_appliances(path)
    raise ValueError("Unsupported source adapter")
