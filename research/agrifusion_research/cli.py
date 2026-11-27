"""One entry point for the research lane.

    python -m agrifusion_research <stage> [stage args...]
    python -m agrifusion_research external <step> [args...]
    python -m agrifusion_research experiment <name> [<study>] [args...]
    agrifusion-research ...              (console script, same thing)
    python -m agrifusion_research list   (every command and the module it runs)

Each command runs the existing ``main()`` of its module unchanged (arguments after the command
name are passed through), so ``<command> --help`` shows that module's own options. Commands
that read earlier runs take ``--inputs <file.yaml>`` (see core/common/run_inputs.py).
"""
from __future__ import annotations

import importlib
import sys
from collections.abc import Sequence

P = "agrifusion_research"

# Core pipeline, in run order.
STAGES: dict[str, tuple[str, str]] = {
    "protocol-registry": (f"{P}.core.protocol_registry.main", "freeze E1/E2/E3 protocol registry from Layer1"),
    "dataset-views": (f"{P}.core.dataset_views.main", "materialize feature views X from Layer1"),
    "weak-labels": (f"{P}.core.weak_labels.lifecycle.phase_c_native.main", "native weak-label engine (labels y)"),
    "weak-labels-analysis": (f"{P}.core.weak_labels.analysis.main", "audit-only UNRES origin split"),
    "evaluation-protocols": (f"{P}.core.evaluation_protocols.main", "folds + frozen runner contract"),
    "e1e2-split-audit": (f"{P}.core.evaluation_protocols.e1e2_split_audit.main", "E1/E2 split audit"),
    "validity-lifecycle": (f"{P}.core.gates.validity_lifecycle.main", "gate: re-audit locked sample universe"),
    "pretrain-audit": (f"{P}.core.gates.pretrain_audit.main", "gate: X/y/split key audit before fitting"),
    "model": (f"{P}.core.model_suite.cli", "model suite (train/evaluate from a runner contract)"),
    "model-smoke": (f"{P}.core.model_suite.protocol_training.smoke_main", "staged smoke training on a protocol run"),
    "model-full": (f"{P}.core.model_suite.protocol_training.full_main", "staged full training on a protocol run"),
    "multilabel": (f"{P}.core.model_suite.multilabel.main", "independent binary heads on a reviewed audit"),
}

EXTERNAL: dict[str, tuple[str, str]] = {
    "intake": (f"{P}.external.intake.main", "preserve + canonicalize one external dataset"),
    "features": (f"{P}.external.features.main", "feature superset for an intake run"),
    "labels": (f"{P}.external.labels.main", "weak-label candidates for an intake run"),
    "splits": (f"{P}.external.splits.main", "timestamp-block splits"),
    "claims": (f"{P}.external.claims.main", "claim inventory for review"),
    "support-continuity": (f"{P}.external.support_audit.continuity_main", "continuity support sensitivity"),
    "support-refresh": (f"{P}.external.support_audit.refresh_continuity_main", "refresh continuity audit"),
    "support-grid": (f"{P}.external.support_audit.grid_main", "support grid audit"),
}

# One-off studies: experiment <name> [<study>]; the first study is the default.
EXPERIMENTS: dict[str, dict[str, str]] = {
    "k_window_variants": {
        "main": f"{P}.experiments.k_window_variants.main",
        "ordered": f"{P}.experiments.k_window_variants.ordered_main",
        "robustness": f"{P}.experiments.k_window_variants.robustness_main",
        "embedding": f"{P}.experiments.k_window_variants.embedding_main",
        "semantic": f"{P}.experiments.k_window_variants.semantic_main",
        "configured": f"{P}.experiments.k_window_variants.configured_main",
        "rq1": f"{P}.experiments.k_window_variants.rq1_main",
        "rq1_program": f"{P}.experiments.k_window_variants.rq1_program_main",
        "rq1_review_controls": f"{P}.experiments.k_window_variants.rq1_review_controls_main",
    },
    "wade_calibration": {"main": f"{P}.experiments.wade_calibration.main"},
    "posthoc_model_analysis": {"main": f"{P}.experiments.posthoc_model_analysis.main"},
    "stuard_controls": {
        "controls": f"{P}.experiments.stuard_controls.stuard_controls_main",
        "acquisition": f"{P}.experiments.stuard_controls.stuard_acquisition_controls_main",
    },
    "paper_tables": {"main": f"{P}.experiments.paper_tables.main"},
    "weak_labels_phases": {
        "phase_a": f"{P}.experiments.weak_labels_phases.phase_a_readiness.main",
        "phase_b": f"{P}.experiments.weak_labels_phases.phase_b_contract.main",
        "phase_b_boundary": f"{P}.experiments.weak_labels_phases.phase_b_contract.boundary_experiment",
        "semantic_draft": f"{P}.experiments.weak_labels_phases.semantic_label_draft",
    },
    "temporary_robustness_probe": {"main": f"{P}.experiments.temporary_robustness_probe.main"},
    "source_intake": {"main": f"{P}.experiments.source_intake.main"},
}


def all_commands() -> dict[str, str]:
    """{"<command words>": "<module>"} for every runnable command (used by --help and tests)."""
    commands = {name: module for name, (module, _) in STAGES.items()}
    commands.update({f"external {name}": module for name, (module, _) in EXTERNAL.items()})
    for name, studies in EXPERIMENTS.items():
        commands.update({f"experiment {name} {study}": module for study, module in studies.items()})
    return commands


def _usage() -> str:
    lines = [__doc__.strip(), "", "stages:"]
    lines += [f"  {name:<22} {text}" for name, (_, text) in STAGES.items()]
    lines += ["", "external <step>:"]
    lines += [f"  {name:<22} {text}" for name, (_, text) in EXTERNAL.items()]
    lines += ["", "experiment <name> [<study>]:"]
    lines += [f"  {name:<26} {' | '.join(studies)}" for name, studies in EXPERIMENTS.items()]
    return "\n".join(lines)


def resolve(argv: Sequence[str]) -> tuple[str, str, list[str]]:
    """Return (command words, module, remaining args) or raise SystemExit with usage."""
    args = list(argv)
    if not args or args[0] in {"-h", "--help", "help"}:
        raise SystemExit(_usage())
    head = args.pop(0)
    if head in STAGES:
        return head, STAGES[head][0], args
    if head == "external" and args and args[0] in EXTERNAL:
        step = args.pop(0)
        return f"external {step}", EXTERNAL[step][0], args
    if head == "experiment" and args and args[0] in EXPERIMENTS:
        name = args.pop(0)
        studies = EXPERIMENTS[name]
        study = args.pop(0) if args and args[0] in studies else next(iter(studies))
        return f"experiment {name} {study}", studies[study], args
    raise SystemExit(f"unknown command: {' '.join([head, *args[:1]])}\n\n{_usage()}")


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["list"]:
        for words, module in all_commands().items():
            print(f"{words:<45} {module}")
        return 0
    words, module_name, rest = resolve(argv)
    module = importlib.import_module(module_name)
    saved = sys.argv
    sys.argv = [f"agrifusion-research {words}", *rest]
    try:
        result = module.main()
    finally:
        sys.argv = saved
    return int(result or 0)


if __name__ == "__main__":
    raise SystemExit(main())
