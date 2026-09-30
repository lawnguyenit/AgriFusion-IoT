from __future__ import annotations

import pandas as pd

from .contracts import ExternalLabelConfig
from .profiles import ExternalLabelProfile, TargetSpec
from .support import build_support_rows
from .temporal import assign_binary_candidate, continuous_tail_run_lengths


def build_target_candidates(
    *,
    frame: pd.DataFrame,
    in_calibration: pd.Series,
    entity_key: str,
    profile: ExternalLabelProfile,
    target: TargetSpec,
    config: ExternalLabelConfig,
    cadence_by_entity: dict[str, float],
) -> tuple[pd.DataFrame, list[dict[str, object]], list[dict[str, object]]]:
    outputs = pd.DataFrame({"sample_id": frame["sample_id"]})
    registry_rows: list[dict[str, object]] = []
    support_rows: list[dict[str, object]] = []
    for share in config.tail_shares:
        candidate, registry, support = _build_quantile_candidate(
            frame=frame,
            in_calibration=in_calibration,
            entity_key=entity_key,
            profile=profile,
            target=target,
            share=share,
            config=config,
            cadence_by_entity=cadence_by_entity,
        )
        outputs = outputs.merge(candidate, on="sample_id", how="left", validate="one_to_one")
        registry_rows.extend(registry)
        support_rows.extend(support)
    return outputs, registry_rows, support_rows


def _build_quantile_candidate(
    *,
    frame: pd.DataFrame,
    in_calibration: pd.Series,
    entity_key: str,
    profile: ExternalLabelProfile,
    target: TargetSpec,
    share: float,
    config: ExternalLabelConfig,
    cadence_by_entity: dict[str, float],
) -> tuple[pd.DataFrame, list[dict[str, object]], list[dict[str, object]]]:
    values = frame[target.measurement_column]
    fit_values = values.loc[in_calibration].dropna()
    if fit_values.empty:
        raise ValueError(f"Calibration values are absent for target {target.target_id}.")
    quantile_level = share if target.tail_direction == "lower" else 1.0 - share
    threshold = float(fit_values.quantile(quantile_level, interpolation="linear"))
    if target.tail_direction == "lower":
        tail_mask = values.le(threshold) & values.notna()
    else:
        tail_mask = values.ge(threshold) & values.notna()
    runs = continuous_tail_run_lengths(
        frame, tail_mask, profile.timestamp_column, entity_key, cadence_by_entity, config
    )
    q_id = _candidate_id(target.target_id, share)
    return _build_tau_candidates(
        frame=frame,
        in_calibration=in_calibration,
        entity_key=entity_key,
        profile=profile,
        target=target,
        share=share,
        q_id=q_id,
        config=config,
        cadence_by_entity=cadence_by_entity,
        values=values,
        tail_mask=tail_mask,
        run_lengths=runs,
        quantile_level=quantile_level,
        threshold=threshold,
        fit_count=len(fit_values),
    )


def _build_tau_candidates(
    *,
    frame: pd.DataFrame,
    in_calibration: pd.Series,
    entity_key: str,
    profile: ExternalLabelProfile,
    target: TargetSpec,
    share: float,
    q_id: str,
    config: ExternalLabelConfig,
    cadence_by_entity: dict[str, float],
    values: pd.Series,
    tail_mask: pd.Series,
    run_lengths: pd.Series,
    quantile_level: float,
    threshold: float,
    fit_count: int,
) -> tuple[pd.DataFrame, list[dict[str, object]], list[dict[str, object]]]:
    columns = pd.DataFrame({"sample_id": frame["sample_id"]})
    registries: list[dict[str, object]] = []
    supports: list[dict[str, object]] = []
    for tau in config.tau_minutes:
        labels, statuses, required_by_entity = assign_binary_candidate(
            frame, values, tail_mask, run_lengths, entity_key, cadence_by_entity, int(tau)
        )
        label_column = _label_column(target.target_id, share, int(tau))
        status_column = _status_column(target.target_id, share, int(tau))
        columns[label_column] = labels.reset_index(drop=True)
        columns[status_column] = statuses.reset_index(drop=True)
        registries.append(
            _registry_row(
                profile=profile,
                target=target,
                q_id=q_id,
                share=share,
                tau=int(tau),
                quantile_level=quantile_level,
                threshold=threshold,
                fit_count=fit_count,
                label_column=label_column,
                status_column=status_column,
            )
        )
        supports.extend(_support_for_tau(
            frame=frame,
            in_calibration=in_calibration,
            entity_key=entity_key,
            profile=profile,
            target=target,
            q_id=q_id,
            share=share,
            tau=int(tau),
            labels=labels,
            statuses=statuses,
            tail_mask=tail_mask,
            run_lengths=run_lengths,
            required_by_entity=required_by_entity,
            cadence_by_entity=cadence_by_entity,
        ))
    return columns, registries, supports


def _support_for_tau(
    *,
    frame: pd.DataFrame,
    in_calibration: pd.Series,
    entity_key: str,
    profile: ExternalLabelProfile,
    target: TargetSpec,
    q_id: str,
    share: float,
    tau: int,
    labels: pd.Series,
    statuses: pd.Series,
    tail_mask: pd.Series,
    run_lengths: pd.Series,
    required_by_entity: dict[str, int],
    cadence_by_entity: dict[str, float],
) -> list[dict[str, object]]:
    return build_support_rows(
        frame=frame,
        in_calibration=in_calibration,
        entity_key=entity_key,
        profile=profile,
        target=target,
        q_id=q_id,
        tail_share=share,
        tau_minutes=tau,
        labels=labels,
        statuses=statuses,
        tail_mask=tail_mask,
        run_lengths=run_lengths,
        required_by_entity=required_by_entity,
        cadence_by_entity=cadence_by_entity,
        timestamp_column=profile.timestamp_column,
    )


def _registry_row(
    *,
    profile: ExternalLabelProfile,
    target: TargetSpec,
    q_id: str,
    share: float,
    tau: int,
    quantile_level: float,
    threshold: float,
    fit_count: int,
    label_column: str,
    status_column: str,
) -> dict[str, object]:
    joint_q_id = _candidate_id(target.target_id if len(profile.targets) == 1 else "joint", share)
    return {
        "dataset_id": profile.dataset_id,
        "target_id": target.target_id,
        "measurement_column": target.measurement_column,
        "evidence_kind": target.evidence_kind,
        "input_feature_candidates": "|".join(target.input_feature_candidates),
        "positive_label": target.positive_label,
        "tail_direction": target.tail_direction,
        "q_id": q_id,
        "tail_share": float(share),
        "threshold_quantile_level": float(quantile_level),
        "threshold_value": threshold,
        "threshold_fit_count": int(fit_count),
        "tau_minutes": int(tau),
        "label_column": label_column,
        "status_column": status_column,
        "joint_label_column": _joint_column(joint_q_id, tau),
        "candidate_status": "SENSITIVITY_CANDIDATE_NOT_PRIMARY",
    }


def add_joint_labels(
    label_frame: pd.DataFrame,
    profile: ExternalLabelProfile,
    config: ExternalLabelConfig,
) -> None:
    if len(profile.targets) == 1:
        target = profile.targets[0]
        for share in config.tail_shares:
            q_id = _candidate_id(target.target_id, share)
            for tau in config.tau_minutes:
                label_column = _label_column(target.target_id, share, int(tau))
                joint = pd.Series("UNRES", index=label_frame.index, dtype="string")
                joint.loc[label_frame[label_column].eq(0).fillna(False)] = "REF"
                joint.loc[label_frame[label_column].eq(1).fillna(False)] = target.positive_label
                label_frame[_joint_column(q_id, int(tau))] = joint
        return

    if len(profile.targets) != 2:
        return
    first, second = profile.targets
    for share in config.tail_shares:
        q_id = _candidate_id("joint", share)
        for tau in config.tau_minutes:
            first_label = label_frame[_label_column(first.target_id, share, int(tau))]
            second_label = label_frame[_label_column(second.target_id, share, int(tau))]
            joint = pd.Series("UNRES", index=label_frame.index, dtype="string")
            complete = first_label.notna() & second_label.notna()
            joint.loc[complete & first_label.eq(0) & second_label.eq(0)] = "REF"
            joint.loc[complete & first_label.eq(1) & second_label.eq(0)] = first.positive_label
            joint.loc[complete & first_label.eq(0) & second_label.eq(1)] = second.positive_label
            joint.loc[complete & first_label.eq(1) & second_label.eq(1)] = f"{first.positive_label}+{second.positive_label}"
            label_frame[_joint_column(q_id, int(tau))] = joint


def _candidate_id(target_id: str, share: float) -> str:
    return f"{target_id}_q{int(round(share * 100)):02d}"


def _label_column(target_id: str, share: float, tau: int) -> str:
    return f"label_{target_id}_q{int(round(share * 100)):02d}_tau{tau:03d}m"


def _status_column(target_id: str, share: float, tau: int) -> str:
    return f"status_{target_id}_q{int(round(share * 100)):02d}_tau{tau:03d}m"


def _joint_column(q_id: str, tau: int) -> str:
    return f"joint_label_{q_id}_tau{tau:03d}m"
