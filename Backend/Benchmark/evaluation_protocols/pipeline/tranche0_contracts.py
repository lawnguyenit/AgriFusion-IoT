from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from Backend.Benchmark.common.digests import DEFAULT_DIGEST_CONFIG, dataframe_digest, stable_digest
from Backend.Benchmark.common.provenance import resolve_code_commit
from Backend.Benchmark.evaluation_protocols.diagnostics.folds import RollingFoldSpec
from Backend.Benchmark.evaluation_protocols.scope import PRIMARY_FOLD_IDS


_NATIVE_LABEL_RENAMES = {
    "normal_point": "reference_context_point",
    "unknown_environment_point": "unresolved_environmental_evidence_point",
    "normal_window_context": "reference_context_at_anchor",
    "unknown_environment_window": "unresolved_environmental_evidence_at_anchor",
}


def _native_label_contract(value: object) -> object:
    if isinstance(value, str):
        return _NATIVE_LABEL_RENAMES.get(value, value)
    if isinstance(value, list):
        return [_native_label_contract(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_native_label_contract(item) for item in value)
    if isinstance(value, dict):
        return {key: _native_label_contract(item) for key, item in value.items()}
    return value


def _native_label_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ("required_class_support", "label_name", "target"):
        if column in result.columns:
            result[column] = result[column].map(_native_label_contract)
    return result


SENSITIVITY_ONLY_COMPARISON_IDS: frozenset[str] = frozenset(
    {
        "CMP_HISTORY_MINI_8H",
        "CMP_HISTORY_FULL_8H",
    }
)
SECONDARY_CLAIM_IDS: frozenset[str] = frozenset(
    {
        "C_HISTORY_8H_MINI",
        "C_HISTORY_8H_FULL",
    }
)


ABALATION_SUBSETS: tuple[dict[str, object], ...] = (
    {
        "subset_id": "v0_core",
        "semantic_arm_id": "base_5",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht", "npk_core"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "baseline_snapshot",
    },
    {
        "subset_id": "v0_plus_ph",
        "semantic_arm_id": "plus_ph",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht", "npk_core", "npk_ph"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "ph_increment",
    },
    {
        "subset_id": "v0_plus_npk",
        "semantic_arm_id": "plus_npk",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht", "npk_core", "npk_ph", "npk_nutrients"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "npk_increment",
    },
    {
        "subset_id": "v1_full",
        "semantic_arm_id": "full_9",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht", "npk_all"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v1_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "full_snapshot",
    },
    {
        "subset_id": "v1_without_ph",
        "semantic_arm_id": "plus_npk",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht", "npk_core", "npk_nutrients"],
        "excluded_feature_families": ["npk_ph"],
        "forbidden_root_sources": ["npk.ph"],
        "target_id": "v1_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "ph_removal",
    },
    {
        "subset_id": "v1_without_npk",
        "base_matrix_id": "v0_minimal_sensor",
        "semantic_arm_id": "plus_ph",
        "included_feature_families": ["sht", "npk_core", "npk_ph"],
        "excluded_feature_families": ["npk_nutrients"],
        "forbidden_root_sources": ["npk.n_proxy", "npk.p_proxy", "npk.k_proxy"],
        "target_id": "v1_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "npk_removal",
    },
    {
        "subset_id": "v0_without_direct_row_source",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht", "npk_core_minus_direct_row_source"],
        "excluded_feature_families": ["direct_row_source"],
        "forbidden_root_sources": ["npk.soil_moisture_pct"],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "direct_row_source_removal",
    },
    {
        "subset_id": "v0_without_direct_source_family",
        "base_matrix_id": "v0_minimal_sensor",
        "included_feature_families": ["sht"],
        "excluded_feature_families": ["direct_source_family"],
        "forbidden_root_sources": ["npk.soil_moisture_pct"],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "direct_source_family_removal",
    },
    {
        "subset_id": "metadata_observation_only",
        "base_matrix_id": "shared_metadata",
        "included_feature_families": ["observation_metadata"],
        "excluded_feature_families": ["rule_metadata"],
        "forbidden_root_sources": [],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "observation_process_probe",
    },
    {
        "subset_id": "metadata_rule_source_only",
        "base_matrix_id": "shared_metadata",
        "included_feature_families": ["rule_metadata"],
        "excluded_feature_families": ["observation_metadata"],
        "forbidden_root_sources": [],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "rule_metadata_probe",
    },
    {
        "subset_id": "metadata_all",
        "base_matrix_id": "shared_metadata",
        "included_feature_families": ["observation_metadata", "rule_metadata"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v0_point_train",
        "history_horizon": 0,
        "comparison_population_policy": "MATCHED_POINT_ANCHORS",
        "scientific_role": "diagnostic_metadata_probe",
    },
    {
        "subset_id": "v2_mini_same_y_3h",
        "base_matrix_id": "v2_minimal_sensor_window_3h",
        "included_feature_families": ["snapshot_minimal", "history_3h_minimal"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v2_same_y_3h",
        "history_horizon": 3,
        "comparison_population_policy": "MATCHED_3H_ANCHORS",
        "scientific_role": "history_3h_minimal",
    },
    {
        "subset_id": "v2_full_same_y_3h",
        "base_matrix_id": "v2_sensor_row_window_3h",
        "included_feature_families": ["snapshot_full", "history_3h_full"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v2_same_y_3h",
        "history_horizon": 3,
        "comparison_population_policy": "MATCHED_3H_ANCHORS",
        "scientific_role": "history_3h_full",
    },
    {
        "subset_id": "v2_mini_same_y_8h",
        "base_matrix_id": "v2_minimal_sensor_window_8h",
        "included_feature_families": ["snapshot_minimal", "history_8h_minimal"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v2_same_y_8h",
        "history_horizon": 8,
        "comparison_population_policy": "MATCHED_8H_ANCHORS",
        "scientific_role": "history_8h_minimal",
    },
    {
        "subset_id": "v2_full_same_y_8h",
        "base_matrix_id": "v2_sensor_row_window_8h",
        "included_feature_families": ["snapshot_full", "history_8h_full"],
        "excluded_feature_families": [],
        "forbidden_root_sources": [],
        "target_id": "v2_same_y_8h",
        "history_horizon": 8,
        "comparison_population_policy": "MATCHED_8H_ANCHORS",
        "scientific_role": "history_8h_full",
    },
)


COMPARISON_SPECS: tuple[dict[str, object], ...] = (
    {
        "comparison_id": "CMP_PH_INCREMENT",
        "claim_id": "C_PH_INCREMENT",
        "estimand_id": "PH_INCREMENT_FIXED",
        "baseline_arm_id": "v0_core",
        "treatment_arm_id": "v0_plus_ph",
        "baseline_semantic_arm_id": "base_5",
        "treatment_semantic_arm_id": "plus_ph",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "point snapshot with pH increment only",
    },
    {
        "comparison_id": "CMP_NPK_INCREMENT",
        "claim_id": "C_NPK_INCREMENT",
        "estimand_id": "NPK_INCREMENT_FIXED",
        "baseline_arm_id": "v0_plus_ph",
        "treatment_arm_id": "v0_plus_npk",
        "baseline_semantic_arm_id": "plus_ph",
        "treatment_semantic_arm_id": "plus_npk",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "point snapshot with NPK increment only",
    },
    {
        "comparison_id": "CMP_PH_REMOVAL",
        "claim_id": "C_PH_REMOVAL",
        "estimand_id": "PH_REMOVAL_FIXED",
        "baseline_arm_id": "v1_full",
        "treatment_arm_id": "v1_without_ph",
        "baseline_semantic_arm_id": "full_9",
        "treatment_semantic_arm_id": "plus_npk",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "full snapshot with pH removed only",
    },
    {
        "comparison_id": "CMP_NPK_REMOVAL",
        "claim_id": "C_NPK_REMOVAL",
        "estimand_id": "NPK_REMOVAL_FIXED",
        "baseline_arm_id": "v1_full",
        "treatment_arm_id": "v1_without_npk",
        "baseline_semantic_arm_id": "full_9",
        "treatment_semantic_arm_id": "plus_ph",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "full snapshot with NPK removed only",
    },
    {
        "comparison_id": "CMP_DIRECT_ROW_SOURCE_REMOVAL",
        "claim_id": "C_DIRECT_RULE_DEPENDENCE",
        "estimand_id": "DIRECT_ROW_SOURCE_REMOVAL",
        "baseline_arm_id": "v0_core",
        "treatment_arm_id": "v0_without_direct_row_source",
        "baseline_semantic_arm_id": "base_5",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "direct row-source removal only",
    },
    {
        "comparison_id": "CMP_DIRECT_SOURCE_FAMILY_REMOVAL",
        "claim_id": "C_DIRECT_SOURCE_FAMILY_DEPENDENCE",
        "estimand_id": "DIRECT_SOURCE_FAMILY_REMOVAL",
        "baseline_arm_id": "v0_core",
        "treatment_arm_id": "v0_without_direct_source_family",
        "baseline_semantic_arm_id": "base_5",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "transitive source-family removal only",
    },
    {
        "comparison_id": "CMP_HISTORY_MINI_3H",
        "claim_id": "C_HISTORY_3H_MINI",
        "estimand_id": "HISTORY_3H_MINI_FIXED",
        "baseline_arm_id": "v0_core",
        "treatment_arm_id": "v2_mini_same_y_3h",
        "baseline_semantic_arm_id": "base_5",
        "treatment_semantic_arm_id": "base_5_history_3h",
        "comparison_population_id": "MATCHED_3H_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "same-Y 3h minimal history effect only",
    },
    {
        "comparison_id": "CMP_HISTORY_FULL_3H",
        "claim_id": "C_HISTORY_3H_FULL",
        "estimand_id": "HISTORY_3H_FULL_FIXED",
        "baseline_arm_id": "v1_full",
        "treatment_arm_id": "v2_full_same_y_3h",
        "baseline_semantic_arm_id": "full_9",
        "treatment_semantic_arm_id": "full_9_history_3h",
        "comparison_population_id": "MATCHED_3H_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "same-Y 3h full history effect only",
    },
    {
        "comparison_id": "CMP_HISTORY_MINI_8H",
        "claim_id": "C_HISTORY_8H_MINI",
        "estimand_id": "HISTORY_8H_MINI_FIXED",
        "baseline_arm_id": "v0_core",
        "treatment_arm_id": "v2_mini_same_y_8h",
        "baseline_semantic_arm_id": "base_5",
        "comparison_population_id": "MATCHED_8H_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "same-Y 8h minimal history effect only",
    },
    {
        "comparison_id": "CMP_HISTORY_FULL_8H",
        "claim_id": "C_HISTORY_8H_FULL",
        "estimand_id": "HISTORY_8H_FULL_FIXED",
        "baseline_arm_id": "v1_full",
        "treatment_arm_id": "v2_full_same_y_8h",
        "baseline_semantic_arm_id": "full_9",
        "comparison_population_id": "MATCHED_8H_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "same-Y 8h full history effect only",
    },
    {
        "comparison_id": "CMP_OBSERVATION_METADATA",
        "claim_id": "C_OBSERVATION_METADATA",
        "estimand_id": "OBSERVATION_METADATA_FIXED",
        "baseline_arm_id": "v0_core",
        "treatment_arm_id": "metadata_observation_only",
        "comparison_population_id": "MATCHED_POINT_ANCHORS",
        "pairing_key": "record.id",
        "primary_metric_id": "macro_f1_3class",
        "required_class_support": "normal_point|low_relative_moisture_point|unknown_environment_point",
        "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
        "interpretation_limit": "observation-metadata-only diagnostic",
    },
)


CLAIM_SPECS: tuple[dict[str, object], ...] = (
    {
        "claim_id": "C_PH_INCREMENT",
        "research_question": "RQ1",
        "statement": "Adding pH to the minimal snapshot may improve point prediction.",
        "claim_priority": "PRIMARY",
        "primary_comparison": "CMP_PH_INCREMENT",
        "baseline_semantic_arm_id": "base_5",
        "treatment_semantic_arm_id": "plus_ph",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost", "ft_transformer"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_POINT_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0"],
        "interpretation_limit": ["does not establish causal soil mechanism"],
    },
    {
        "claim_id": "C_NPK_INCREMENT",
        "research_question": "RQ1",
        "statement": "Adding NPK-related channels to the point snapshot may improve point prediction.",
        "claim_priority": "PRIMARY",
        "primary_comparison": "CMP_NPK_INCREMENT",
        "baseline_semantic_arm_id": "base_5",
        "treatment_semantic_arm_id": "plus_npk",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost", "ft_transformer"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_POINT_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0"],
        "interpretation_limit": ["does not establish nutrient causality"],
    },
    {
        "claim_id": "C_DIRECT_RULE_DEPENDENCE",
        "research_question": "RQ2",
        "statement": "Point targets may depend directly on the current-row rule source.",
        "claim_priority": "PRIMARY",
        "primary_comparison": "CMP_DIRECT_ROW_SOURCE_REMOVAL",
        "baseline_semantic_arm_id": "base_5",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_POINT_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["rule-removal effect == 0"],
        "interpretation_limit": ["tests direct row-source dependence only"],
    },
    {
        "claim_id": "C_DIRECT_SOURCE_FAMILY_DEPENDENCE",
        "research_question": "RQ2",
        "statement": "Point targets may depend on the full source family behind the direct rule measurement.",
        "claim_priority": "PRIMARY",
        "primary_comparison": "CMP_DIRECT_SOURCE_FAMILY_REMOVAL",
        "baseline_semantic_arm_id": "base_5",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_POINT_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["family-removal effect == 0"],
        "interpretation_limit": ["tests transitive source-family dependence only"],
    },
    {
        "claim_id": "C_HISTORY_3H_MINI",
        "research_question": "RQ3",
        "statement": "Three-hour past-looking minimal history provides information beyond the current-row snapshot.",
        "claim_priority": "PRIMARY",
        "primary_comparison": "CMP_HISTORY_MINI_3H",
        "baseline_semantic_arm_id": "base_5",
        "treatment_semantic_arm_id": "base_5_history_3h",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost", "ft_transformer"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_3H_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0", "effect disappears in E2"],
        "interpretation_limit": ["same-Y history effect only", "does not establish causal environmental mechanism"],
    },
    {
        "claim_id": "C_HISTORY_3H_FULL",
        "research_question": "RQ3",
        "statement": "Three-hour full history provides information beyond the current-row full snapshot.",
        "claim_priority": "PRIMARY",
        "primary_comparison": "CMP_HISTORY_FULL_3H",
        "baseline_semantic_arm_id": "full_9",
        "treatment_semantic_arm_id": "full_9_history_3h",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost", "ft_transformer"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_3H_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0", "effect disappears in E2"],
        "interpretation_limit": ["same-Y history effect only"],
    },
    {
        "claim_id": "C_HISTORY_8H_MINI",
        "research_question": "RQ3",
        "statement": "Eight-hour minimal history provides information beyond the current-row snapshot.",
        "claim_priority": "SECONDARY",
        "primary_comparison": "CMP_HISTORY_MINI_8H",
        "baseline_semantic_arm_id": "base_5",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost", "ft_transformer"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_8H_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0"],
        "interpretation_limit": ["same-Y history effect only"],
    },
    {
        "claim_id": "C_HISTORY_8H_FULL",
        "research_question": "RQ3",
        "statement": "Eight-hour full history provides information beyond the current-row full snapshot.",
        "claim_priority": "SECONDARY",
        "primary_comparison": "CMP_HISTORY_FULL_8H",
        "baseline_semantic_arm_id": "full_9",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost", "ft_transformer"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_8H_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0"],
        "interpretation_limit": ["same-Y history effect only"],
    },
    {
        "claim_id": "C_OBSERVATION_METADATA",
        "research_question": "RQ4",
        "statement": "Observation-process metadata alone may explain part of target predictability.",
        "claim_priority": "DIAGNOSTIC",
        "primary_comparison": "CMP_OBSERVATION_METADATA",
        "stress_environments": ["E2", "E3"],
        "primary_model_profile": "logistic_regression",
        "secondary_model_profiles": ["xgboost"],
        "primary_tuning_policy": "FIXED_PROFILE_PRIMARY",
        "required_population": "MATCHED_POINT_ANCHORS",
        "required_support": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
        "disconfirming_result": ["matched effect <= 0"],
        "interpretation_limit": ["diagnostic only"],
    },
)


def build_environment_registry(
    working: pd.DataFrame,
    protocol_environment_manifest: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for environment in protocol_environment_manifest.to_dict(orient="records"):
        start_local = pd.Timestamp(str(environment["start_time"]))
        end_local = pd.Timestamp(str(environment["end_time"]))
        observed = working.loc[
            (working["timestamp_local"] >= start_local)
            & (working["timestamp_local"] < end_local)
            & (
                working["deployment_domain_name"].astype("string")
                == str(environment["deployment_id"])
            ),
            ["timestamp_local"],
        ].copy()
        rows.append(
            {
                "environment_id": environment["environment_id"],
                "legacy_environment_alias": environment["legacy_environment_alias"],
                "deployment_id": environment["deployment_id"],
                "position_id": environment["position_id"],
                "phase_id": environment["phase_id"],
                "acquisition_regime_id": environment["acquisition_regime_id"],
                "start_local": environment["start_time"],
                "end_local": environment["end_time"],
                "protocol_role": environment["protocol_role"],
                "historical_exposure_status": environment["historical_exposure_status"],
                "boundary_basis": "upstream protocol_registry environment fact",
                "boundary_origin": "PROTOCOL_REGISTRY",
                "boundary_status": "PROTOCOL_GOVERNED",
                "analysis_status": _environment_analysis_status(str(environment["environment_id"])),
                "start_inclusive": True,
                "end_exclusive": True,
                "timezone": "Asia/Ho_Chi_Minh",
                "observed_first_timestamp": (
                    observed["timestamp_local"].min().isoformat() if not observed.empty else pd.NA
                ),
                "observed_last_timestamp": (
                    observed["timestamp_local"].max().isoformat() if not observed.empty else pd.NA
                ),
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def _environment_analysis_status(environment_id: str) -> str:
    if environment_id == "E1":
        return "SOURCE_DISCOVERY"
    if environment_id == "E2":
        return "SOURCE_ACQUISITION_STRESS"
    if environment_id == "E3_TARGET_PREEXPOSED":
        return "PROTOCOL_LOCKED_TRANSPORT_REEVALUATION"
    return "UNASSIGNED"


def build_sample_environment_manifest(working: pd.DataFrame, environment_registry: pd.DataFrame) -> pd.DataFrame:
    specs = environment_registry.to_dict(orient="records")
    rows: list[dict[str, object]] = []
    for row in working.loc[:, ["record.id", "timestamp_local", "deployment_domain_name", "record.segment_id"]].itertuples(index=False):
        timestamp = pd.Timestamp(row[1])
        environment_id = "UNASSIGNED"
        analysis_status = "UNASSIGNED"
        boundary_status = "UNASSIGNED"
        for spec in specs:
            start_local = pd.Timestamp(spec["start_local"])
            end_local = pd.Timestamp(spec["end_local"])
            if (
                str(row[2]) == str(spec["deployment_id"])
                and start_local <= timestamp < end_local
            ):
                environment_id = str(spec["environment_id"])
                analysis_status = str(spec["analysis_status"])
                boundary_status = str(spec["boundary_status"])
                break
        rows.append(
            {
                "sample_id": str(row[0]),
                "timestamp_local": timestamp.isoformat(),
                "deployment_id": str(row[2]),
                "segment_id": str(row[3]),
                "environment_id": environment_id,
                "analysis_status": analysis_status,
                "boundary_status": boundary_status,
            }
        )
    manifest = pd.DataFrame(rows).convert_dtypes()
    duplicates = manifest.loc[manifest["sample_id"].astype("string").duplicated(keep=False), ["sample_id"]]
    if not duplicates.empty:
        raise ValueError(f"sample_environment_manifest has duplicate sample_id values: {duplicates.to_dict(orient='records')}")
    return manifest


def build_e1_fold_registry(
    *,
    fold_specs: list[RollingFoldSpec],
    threshold_fit_manifest_hash: str,
    preprocessing_fit_manifest_hash: str,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for spec in fold_specs:
        rows.append(
            {
                "fold_id": spec.fold_id,
                "train_start": spec.train_start.isoformat(),
                "train_end": spec.train_end.isoformat(),
                "purge_train_val_start": spec.train_end.isoformat(),
                "purge_train_val_end": (spec.validation_start + pd.Timedelta(hours=8)).isoformat(),
                "validation_start": spec.validation_start.isoformat(),
                "validation_end": spec.validation_end.isoformat(),
                "purge_val_test_start": spec.validation_end.isoformat(),
                "purge_val_test_end": (spec.test_start + pd.Timedelta(hours=8)).isoformat(),
                "test_start": spec.test_start.isoformat(),
                "test_end": spec.test_end.isoformat(),
                "maximum_history_horizon": 8,
                "threshold_fit_manifest_hash": threshold_fit_manifest_hash,
                "preprocessing_fit_manifest_hash": preprocessing_fit_manifest_hash,
                "analysis_status": "PRIMARY_LOCKED" if spec.fold_id in PRIMARY_FOLD_IDS else "SECONDARY_EXPLORATORY",
            }
        )
    return pd.DataFrame(rows).convert_dtypes()


def build_claim_registry(repo_root: Path) -> dict[str, object]:
    git_commit = resolve_code_commit(repo_root)
    claims: list[dict[str, object]] = []
    for claim in CLAIM_SPECS:
        claim_id = str(claim["claim_id"])
        claims.append(
            {
                **claim,
                "claim_priority": "SECONDARY" if claim_id in SECONDARY_CLAIM_IDS else claim["claim_priority"],
                "environment_metric_contract": {
                    "E1": {
                        "metric_id": "macro_f1_3class",
                        "required_classes": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
                        "comparison_allowed": True,
                    },
                    "E2": {
                        "metric_id": "macro_f1_3class",
                        "required_classes": ["normal_point", "low_relative_moisture_point", "unknown_environment_point"],
                        "fallback_status": "PARTIAL",
                    },
                    "E3": {
                        "metric_id": "observed_support_metrics",
                        "estimable_classes": ["low_relative_moisture_point", "unknown_environment_point"],
                        "non_estimable_classes": ["normal_point"],
                        "cross_environment_score_delta_allowed": False,
                    },
                },
                "cross_environment_comparability": {
                    "E1_to_E2": True,
                    "E1_to_E3": False,
                    "E2_to_E3": False,
                },
                "fallback_estimability_policy": {
                    "unsupported_class_metric_value": "NaN",
                    "partial_environment_state": "PARTIAL",
                },
                "primary_metric_contract": "environment_metric_contract",
            }
        )
    registry = {
        "registry_version": "claim_registry.v1",
        "frozen_at": "2026-07-26T00:00:00+07:00",
        "git_commit": git_commit,
        "config_hash": stable_digest(CLAIM_SPECS),
        "parent_registry_version": "none",
        "change_reason": "initial tranche-0 preregistered claim registry",
        "results_available_at_freeze": False,
        "claims": claims,
        "slice_registry": {
            "registered_slices": [
                "environment_id",
                "partition",
                "day_id",
                "segment_id",
                "eligibility_status",
                "gap_regime",
            ]
        },
    }
    return _native_label_contract(registry)


def build_comparison_registry() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for comparison in COMPARISON_SPECS:
        comparison_id = str(comparison["comparison_id"])
        rows.append(
            {
                **comparison,
                "analysis_status": "SENSITIVITY_ONLY" if comparison_id in SENSITIVITY_ONLY_COMPARISON_IDS else "PRIMARY_LOCKED",
            }
        )
    return _native_label_frame(pd.DataFrame(rows).convert_dtypes())


def build_experiment_registry() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for comparison in COMPARISON_SPECS:
        claim_id = str(comparison["claim_id"])
        comparison_id = str(comparison["comparison_id"])
        analysis_status = "SENSITIVITY_ONLY" if comparison_id in SENSITIVITY_ONLY_COMPARISON_IDS else "PRIMARY_LOCKED"
        for arm_type, arm_id in (("baseline", comparison["baseline_arm_id"]), ("treatment", comparison["treatment_arm_id"])):
            subset = _subset_by_id(str(arm_id))
            rows.append(
                {
                    "experiment_id": f"{claim_id}__{arm_type}",
                    "protocol_id": _protocol_id_for_subset(subset_id=str(subset["subset_id"])),
                    "arm_id": str(arm_id),
                    "comparison_id": str(comparison["comparison_id"]),
                    "estimand_id": str(comparison["estimand_id"]),
                    "feature_subset_id": str(subset["subset_id"]),
                    "target_id": str(subset["target_id"]),
                    "threshold_policy_id": "TRAIN_ONLY_THRESHOLD_POLICY",
                    "preprocessing_policy_id": "TRAIN_ONLY_PREPROCESSING_POLICY",
                    "model_profile_id": "logistic_regression",
                    "tuning_policy_id": str(comparison["tuning_policy_id"]),
                    "comparison_population_id": str(comparison["comparison_population_id"]),
                    "train_manifest_path": _train_manifest_name(str(subset["subset_id"])),
                    "selection_manifest_path": _selection_manifest_name(str(subset["subset_id"])),
                    "eval_manifest_path": _eval_manifest_name(str(subset["subset_id"])),
                    "sample_hash_key": "evaluation_contract_digest",
                    "analysis_status": analysis_status,
                }
            )
    rows.extend(
        [
            {
                "experiment_id": "EXPANSION_OPERATIONAL_E1",
                "protocol_id": "P_E1_TO_E3",
                "arm_id": "EXPANSION_ARM_E1",
                "comparison_id": "CMP_SOURCE_EXPANSION_OPERATIONAL",
                "estimand_id": "OPERATIONAL_EXPANSION",
                "feature_subset_id": "v1_full",
                "target_id": "v1_point_train",
                "threshold_policy_id": "TRAIN_ONLY_THRESHOLD_POLICY",
                "preprocessing_policy_id": "TRAIN_ONLY_PREPROCESSING_POLICY",
                "model_profile_id": "logistic_regression",
                "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
                "comparison_population_id": "E3_LOCKED",
                "train_manifest_path": "source_expansion_operational_manifest.parquet",
                "selection_manifest_path": "source_expansion_operational_manifest.parquet",
                "eval_manifest_path": "deployment_transport_manifest.parquet",
                "sample_hash_key": "evaluation_contract_digest",
                "analysis_status": "PRIMARY_LOCKED",
            },
            {
                "experiment_id": "EXPANSION_OPERATIONAL_E1E2",
                "protocol_id": "P_E1E2_TO_E3",
                "arm_id": "EXPANSION_ARM_E1E2",
                "comparison_id": "CMP_SOURCE_EXPANSION_OPERATIONAL",
                "estimand_id": "OPERATIONAL_EXPANSION",
                "feature_subset_id": "v1_full",
                "target_id": "v1_point_train",
                "threshold_policy_id": "TRAIN_ONLY_THRESHOLD_POLICY",
                "preprocessing_policy_id": "TRAIN_ONLY_PREPROCESSING_POLICY",
                "model_profile_id": "logistic_regression",
                "tuning_policy_id": "FIXED_PROFILE_PRIMARY",
                "comparison_population_id": "E3_LOCKED",
                "train_manifest_path": "source_expansion_operational_manifest.parquet",
                "selection_manifest_path": "source_expansion_operational_manifest.parquet",
                "eval_manifest_path": "deployment_transport_manifest.parquet",
                "sample_hash_key": "evaluation_contract_digest",
                "analysis_status": "SECONDARY_EXPLORATORY",
            },
        ]
    )
    return pd.DataFrame(rows).convert_dtypes()


def build_legacy_to_v2_equivalence_report(
    *,
    task_training_manifest: pd.DataFrame,
    comparison_training_manifest: pd.DataFrame,
    frozen_target_manifest: pd.DataFrame,
    discovery_training_manifest: pd.DataFrame,
    temporal_falsification_manifest: pd.DataFrame,
    source_expansion_operational_manifest: pd.DataFrame,
    deployment_transport_manifest: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        _equivalence_row(
            legacy_manifest="task_training_manifest.parquet",
            new_manifest="discovery_training_manifest.parquet",
            legacy_df=task_training_manifest.loc[task_training_manifest["partition"].astype("string").isin(["train", "validation", "test"])].copy(),
            new_df=discovery_training_manifest.copy(),
            difference_reason="v2 adds contract digests and environment assignment columns",
        ),
        _equivalence_row(
            legacy_manifest="comparison_training_manifest.parquet",
            new_manifest="temporal_falsification_manifest.parquet",
            legacy_df=comparison_training_manifest.copy(),
            new_df=temporal_falsification_manifest.copy(),
            difference_reason="temporal falsification is comparison-scoped and exploratory",
        ),
        _equivalence_row(
            legacy_manifest="frozen_target_manifest.parquet",
            new_manifest="deployment_transport_manifest.parquet",
            legacy_df=frozen_target_manifest.copy(),
            new_df=deployment_transport_manifest.copy(),
            difference_reason="transport manifest adds environment-aware metric contract fields",
        ),
        _equivalence_row(
            legacy_manifest="task_training_manifest.parquet",
            new_manifest="source_expansion_operational_manifest.parquet",
            legacy_df=task_training_manifest.copy(),
            new_df=source_expansion_operational_manifest.copy(),
            difference_reason="operational expansion reuses v1_full and locked E3 target scope",
        ),
    ]
    return pd.DataFrame(rows).convert_dtypes()


def extend_manifest_with_contracts(
    manifest: pd.DataFrame,
    *,
    sample_environment_manifest: pd.DataFrame,
    ontology_id: str,
) -> pd.DataFrame:
    environment_lookup = sample_environment_manifest.set_index("sample_id")[
        ["timestamp_local", "deployment_id", "segment_id", "environment_id", "analysis_status", "boundary_status"]
    ]
    working = manifest.copy()
    if "sample_id" not in working.columns:
        working["sample_id"] = working["record_id"].astype("string")
    working = working.merge(
        environment_lookup,
        left_on="sample_id",
        right_index=True,
        how="left",
    )
    working["environment_id"] = working["environment_id"].fillna("UNASSIGNED").astype("string")
    working["analysis_status"] = working["analysis_status"].fillna("UNASSIGNED").astype("string")
    working["boundary_status"] = working["boundary_status"].fillna("UNASSIGNED").astype("string")
    if "partition" not in working.columns and "effective_partition" in working.columns:
        working["partition"] = working["effective_partition"].astype("string")
    if "day_id" not in working.columns:
        working["day_id"] = pd.to_datetime(working["timestamp_local"], errors="coerce").dt.strftime("%Y-%m-%d").astype("string")
    if "gap_regime" not in working.columns:
        working["gap_regime"] = "unknown"
    if "eligibility_status" not in working.columns:
        if "final_trainability" in working.columns:
            working["eligibility_status"] = working["final_trainability"].map(lambda value: "eligible" if bool(value) else "excluded")
        else:
            working["eligibility_status"] = "eligible"
    if "target" not in working.columns:
        working["target"] = working.get("label_name", pd.Series([pd.NA] * len(working), dtype="string")).astype("string")
    working["ontology_id"] = ontology_id
    working["population_digest"] = _group_digest(working, ["sample_id"], ["sample_id"])
    working["evaluation_contract_digest"] = _group_digest(
        working,
        ["sample_id", "target", "partition", "environment_id", "eligibility_status", "ontology_id"],
        ["sample_id", "partition"],
    )
    working["feature_contract_digest"] = _feature_contract_digest_series(working)
    return working.convert_dtypes()


def build_runner_contract_v2_payload(
    *,
    claim_registry_path: Path,
    comparison_registry_path: Path,
    experiment_registry_path: Path,
    environment_registry_path: Path,
) -> dict[str, object]:
    return {
        "contract_version": "runner_contract.v2",
        "digest_config": dict(DEFAULT_DIGEST_CONFIG),
        "registries": {
            "claim_registry_path": str(claim_registry_path),
            "comparison_registry_path": str(comparison_registry_path),
            "experiment_registry_path": str(experiment_registry_path),
            "environment_registry_path": str(environment_registry_path),
        },
    }


def _subset_by_id(subset_id: str) -> dict[str, object]:
    for subset in ABALATION_SUBSETS:
        if str(subset["subset_id"]) == subset_id:
            return subset
    raise KeyError(f"Unknown ablation subset: {subset_id}")


def _protocol_id_for_subset(*, subset_id: str) -> str:
    if "3h" in subset_id or "8h" in subset_id:
        return "P_E1_DISCOVERY"
    return "P_E1_DISCOVERY"


def _train_manifest_name(subset_id: str) -> str:
    if "3h" in subset_id or "8h" in subset_id:
        return "discovery_training_manifest.parquet"
    return "discovery_training_manifest.parquet"


def _selection_manifest_name(subset_id: str) -> str:
    return _train_manifest_name(subset_id)


def _eval_manifest_name(subset_id: str) -> str:
    if "3h" in subset_id or "8h" in subset_id:
        return "temporal_falsification_manifest.parquet"
    return "deployment_transport_manifest.parquet"


def _group_digest(frame: pd.DataFrame, columns: list[str], sort_columns: list[str]) -> pd.Series:
    digest = dataframe_digest(frame, columns=columns, sort_columns=sort_columns, config=dict(DEFAULT_DIGEST_CONFIG))
    return pd.Series([digest] * len(frame), index=frame.index, dtype="string")


def _feature_contract_digest_series(frame: pd.DataFrame) -> pd.Series:
    if "feature_view_id" not in frame.columns:
        return pd.Series(["UNSPECIFIED_FEATURE_CONTRACT"] * len(frame), index=frame.index, dtype="string")
    payload_by_index: dict[int, str] = {}
    for (_, feature_view_id), group in frame.groupby(
        [frame.get("feature_source_view_id", frame["feature_view_id"]).astype("string"), frame["feature_view_id"].astype("string")],
        dropna=False,
        sort=False,
    ):
        ordered_feature_names = []
        if "allowed_feature_columns_json" in group.columns:
            candidate = group["allowed_feature_columns_json"].dropna().astype("string").unique().tolist()
            if candidate:
                ordered_feature_names = json.loads(candidate[0])
        digest = stable_digest(
            {
                "sample_id": group["sample_id"].astype("string").tolist(),
                "ordered_feature_names": ordered_feature_names,
                "feature_view_version": str(feature_view_id),
            }
        )
        for index in group.index:
            payload_by_index[int(index)] = digest
    return pd.Series([payload_by_index.get(int(index), "UNSPECIFIED_FEATURE_CONTRACT") for index in frame.index], index=frame.index, dtype="string")


def _equivalence_row(
    *,
    legacy_manifest: str,
    new_manifest: str,
    legacy_df: pd.DataFrame,
    new_df: pd.DataFrame,
    difference_reason: str,
) -> dict[str, object]:
    legacy_samples = set(legacy_df.get("sample_id", pd.Series(dtype="string")).astype("string").dropna().tolist())
    new_samples = set(new_df.get("sample_id", pd.Series(dtype="string")).astype("string").dropna().tolist())
    legacy_digest = dataframe_digest(
        pd.DataFrame({"sample_id": sorted(legacy_samples)}),
        columns=["sample_id"],
        sort_columns=["sample_id"],
        config=dict(DEFAULT_DIGEST_CONFIG),
    ) if legacy_samples else "empty"
    new_digest = dataframe_digest(
        pd.DataFrame({"sample_id": sorted(new_samples)}),
        columns=["sample_id"],
        sort_columns=["sample_id"],
        config=dict(DEFAULT_DIGEST_CONFIG),
    ) if new_samples else "empty"
    return {
        "legacy_manifest": legacy_manifest,
        "new_manifest": new_manifest,
        "legacy_sample_count": len(legacy_samples),
        "new_sample_count": len(new_samples),
        "intersection_count": len(legacy_samples & new_samples),
        "legacy_only_count": len(legacy_samples - new_samples),
        "new_only_count": len(new_samples - legacy_samples),
        "sample_hash_equal": legacy_digest == new_digest,
        "difference_reason": difference_reason,
    }


def metric_contract_for_environment(environment_id: str) -> dict[str, object]:
    if environment_id in {"E1", "E2"}:
        return {
            "metric_id": "macro_f1_3class",
            "required_classes": ["reference_context_point", "low_relative_moisture_point", "unresolved_environmental_evidence_point"],
            "comparison_allowed": True,
        }
    return {
        "metric_id": "observed_support_metrics",
        "estimable_classes": ["low_relative_moisture_point", "unresolved_environmental_evidence_point"],
        "non_estimable_classes": ["reference_context_point"],
        "cross_environment_score_delta_allowed": False,
    }


def comparison_lookup_json(comparison_registry: pd.DataFrame) -> str:
    payload = comparison_registry.to_dict(orient="records")
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
