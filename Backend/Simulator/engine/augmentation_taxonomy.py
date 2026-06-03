from __future__ import annotations

from typing import Any


PRIMARY_METHOD_BY_SCENARIO: dict[str, str] = {
    "normal_context": "seed_replay_baseline",
    "packet_loss": "missing_value_simulation",
    "rain_or_fertigation_context": "rule_based_simulation",
    "rain_humid_context": "rule_based_simulation",
    "fertigation_spike": "rule_based_simulation",
    "water_deficit": "rule_based_simulation",
}

SECONDARY_METHODS_BY_SCENARIO: dict[str, list[str]] = {
    "packet_loss": ["rule_based_simulation"],
}

METHOD_DESCRIPTIONS: dict[str, str] = {
    "gaussian_noise_augmentation": "Khong duoc su dung trong simulator hien tai; khong co buoc cong noise Gaussian vao sensor.",
    "missing_value_simulation": "Mo phong thieu ban ghi hoac outage bang cach giu timestamp du kien nhung danh dau record_present=0.",
    "rule_based_simulation": "Sinh hoac mutate gia tri theo kich ban, nguong, khung gio va phase onset/peak/stabilizing/recovery.",
    "seed_replay_baseline": "Tai su dung seed Layer1 gan khung gio de chen normal_context ma khong doi schema benchmark.",
}


def build_augmentation_taxonomy(rows: list[dict[str, Any]]) -> dict[str, Any]:
    family_summary: dict[str, dict[str, Any]] = {
        "gaussian_noise_augmentation": {
            "used": False,
            "row_count": 0,
            "episode_count": 0,
            "scenario_labels": [],
            "description": METHOD_DESCRIPTIONS["gaussian_noise_augmentation"],
        },
        "missing_value_simulation": {
            "used": False,
            "row_count": 0,
            "episode_count": 0,
            "scenario_labels": [],
            "description": METHOD_DESCRIPTIONS["missing_value_simulation"],
        },
        "rule_based_simulation": {
            "used": False,
            "row_count": 0,
            "episode_count": 0,
            "scenario_labels": [],
            "description": METHOD_DESCRIPTIONS["rule_based_simulation"],
        },
        "seed_replay_baseline": {
            "used": False,
            "row_count": 0,
            "episode_count": 0,
            "scenario_labels": [],
            "description": METHOD_DESCRIPTIONS["seed_replay_baseline"],
        },
    }
    scenario_episode_ids: dict[str, set[str]] = {}
    scenario_row_counts: dict[str, int] = {}

    for row in rows:
        scenario_label = str(row.get("scenario_label", "normal_context"))
        scenario_row_counts[scenario_label] = scenario_row_counts.get(scenario_label, 0) + 1
        episode_id = str(row.get("episode_id", "")).strip()
        if episode_id:
            scenario_episode_ids.setdefault(scenario_label, set()).add(episode_id)

    scenario_classification: dict[str, dict[str, Any]] = {}
    for scenario_label, row_count in sorted(scenario_row_counts.items()):
        primary_method = PRIMARY_METHOD_BY_SCENARIO.get(scenario_label, "rule_based_simulation")
        secondary_methods = list(SECONDARY_METHODS_BY_SCENARIO.get(scenario_label, []))
        episode_ids = scenario_episode_ids.get(scenario_label, set())
        scenario_classification[scenario_label] = {
            "primary_method": primary_method,
            "secondary_methods": secondary_methods,
            "uses_gaussian_noise": False,
            "row_count": row_count,
            "episode_count": len(episode_ids),
            "description": _scenario_description(scenario_label, primary_method),
        }

        family_entry = family_summary[primary_method]
        family_entry["used"] = row_count > 0
        family_entry["row_count"] += row_count
        family_entry["episode_count"] += len(episode_ids)
        family_entry["scenario_labels"].append(scenario_label)

    for family_name, family_entry in family_summary.items():
        family_entry["scenario_labels"] = sorted(set(family_entry["scenario_labels"]))
        if family_name == "gaussian_noise_augmentation":
            family_entry["used"] = False

    return {
        "taxonomy_version": "simulator_v1",
        "family_summary": family_summary,
        "scenario_classification": scenario_classification,
        "notes": [
            "Family summary la phan loai primary khong chong lap; packet_loss duoc dem vao missing_value_simulation.",
            "packet_loss van co secondary_method = rule_based_simulation vi duration va khung gio outage duoc sap lich theo rule.",
            "Gaussian Noise Augmentation hien khong duoc ap dung trong generator nay.",
        ],
    }


def _scenario_description(scenario_label: str, primary_method: str) -> str:
    if scenario_label == "packet_loss":
        return "Sinh outage bang missing rows tren gap-aware timeline; thoi diem va thoi luong duoc rang buoc boi rule theo khung gio."
    if scenario_label == "normal_context":
        return "Chen baseline tu seed Layer1 theo slot gio; khong tao noise Gaussian."
    if scenario_label == "rain_or_fertigation_context":
        return "Sinh ngu canh gop co bieu hien nghieng ve mua-am hoac tuoi-bon tuy theo khung gio, nhung giu mot nhan canonical."
    if primary_method == "rule_based_simulation":
        return "Mutate sensor theo quy tac scenario va phase progression."
    return "Scenario synthetic duoc phan loai theo co che primary cua generator."
