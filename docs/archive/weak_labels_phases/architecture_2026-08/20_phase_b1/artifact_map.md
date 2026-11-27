# Phase B1 — Artifact map

| Artifact | Ý nghĩa |
|---|---|
| `qk_geometry.parquet` | Hình học intrinsic của từng Q×K |
| `qk_fold_support.csv` | Support interval-safe của candidate theo Q×K×fold×split |
| `qk_anchor_safety_audit.parquet` | Đếm anchor raw, admissible, purge và boundary |
| `anchor_dependency_audit.parquet` | Chi tiết dependency interval của từng anchor |
| `qk_boundary_audit.parquet` | Event crossing boundary và mô phỏng dịch boundary |
| `qk_distribution_audit.parquet` | Phân phối candidate sau semantic/dependency admissibility |
| `k_regime_registry.csv` | Phân loại vùng hành vi của K |
| `point_compatibility_matrix.csv` | 81 tổ hợp evidence-state và candidate resolution |
| `threshold_boundary_cases.parquet` | Record nằm tại biên threshold |
| `phase_b1_status.yaml` | B1 đang chờ review, chưa freeze |

Các artifact này là candidate analysis, không phải label artifact. Boundary
adjustment chỉ được mô phỏng và báo cáo ở B1; không tự thay fold policy.
