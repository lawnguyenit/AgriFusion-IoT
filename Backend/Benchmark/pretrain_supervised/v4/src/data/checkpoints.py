from __future__ import annotations

from pathlib import Path

from Backend.Benchmark.pretrain_supervised.v4.src.data.contracts import ExperimentCheckpoint


EXPERIMENT_TO_SOURCE_KIND = {
    "exp6": "layer2_exp6",
}


def discover_latest_checkpoint_for_experiment(
    *,
    experiment_name: str,
    benchmark_version: str,
    search_roots: list[Path],
) -> ExperimentCheckpoint:
    source_kind = EXPERIMENT_TO_SOURCE_KIND[experiment_name]
    candidates: list[ExperimentCheckpoint] = []

    for root in search_roots:
        if not root.exists():
            continue
        for checkpoint_path in root.rglob("pretrain_checkpoint.pt"):
            run_dir = checkpoint_path.parent
            report_path = run_dir / "pretrain_report.json"
            config_path = run_dir / "pretrain_config.yaml"
            if not report_path.exists() or not config_path.exists():
                continue
            config_map = _read_simple_yaml(config_path)
            if config_map.get("benchmark_version") != benchmark_version:
                continue
            if config_map.get("source_kind") != source_kind:
                continue
            candidates.append(
                ExperimentCheckpoint(
                    experiment_name=experiment_name,
                    source_kind=source_kind,
                    checkpoint_path=checkpoint_path,
                    run_dir=run_dir,
                    report_path=report_path,
                    config_path=config_path,
                )
            )

    if not candidates:
        raise FileNotFoundError(
            f"No pretrain checkpoint found for {benchmark_version}/{source_kind}. "
            "Run the matching pretrain experiment first."
        )
    return max(candidates, key=lambda item: item.checkpoint_path.stat().st_mtime)


def _read_simple_yaml(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip().strip('"')
        result[key] = value
    return result

