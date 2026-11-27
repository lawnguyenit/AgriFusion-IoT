# Phase A — Readiness Audit

## Vai trò trong lifecycle

Phase A là **audit-only**. Nó kiểm tra dữ liệu và tạo candidate evidence;
nó không tạo benchmark label, không thay resolver và không train model.

## Tóm tắt xử lý

```text
Layer1 canonical
→ chuẩn hóa identity, provenance và environment membership
→ chia E1 / E2 / E3 theo Protocol Registry
→ kiểm tra duplicate, timestamp, source hash và mismatch
→ kiểm tra technical applicability, continuity và window
→ tính diagnostic evidence/Q trên E1
→ xuất readiness report cho Phase B
```

Phase A chỉ chuẩn hóa **schema và tính truy vết**, không sửa giá trị
canonical. E1 được audit đầy đủ; E2/E3 chỉ được structural-audit theo chính
sách visibility. Các evidence và threshold ở đây là candidate diagnostics,
chưa phải nhãn hoặc contract cuối.

```mermaid
flowchart LR
    A["Layer1 canonical\n4,681 records"] --> B["Protocol Registry\nEnvironment + visibility + fold rules"]
    B --> C["A1 Canonical identity\nrecord ID, timestamp, source hash"]
    C --> D["A2 Environment audit\nE1 full / E2-E3 structural-only"]
    D --> E["A3 Continuity diagnostics\ndeployment, strict, window, dependency"]
    E --> F["A4 Rule applicability\nsoil / SHT / delta availability"]
    F --> G["A5 E1 threshold diagnostics\nQ05/Q10/Q15/Q20, EC Q95"]
    G --> H["A6 Primitive evidence\nLOW, thermal, rise, EC"]
    H --> I["A7 Candidate inventory\nresolution candidates + support"]
    I --> J{ "Readiness gate" }
    J -->|PASS| K["Candidate artifacts\nSTOP before label changes"]
    J -->|FAIL| L["Fix input/protocol issue"]
    X["Optional legacy reference"] -.-> G
    X -.-> I
```

## Dữ liệu và tham số của từng khối

| Khối | Dữ liệu vào | Quy tắc/tham số | Dữ liệu ra |
|---|---|---|---|
| Canonical identity | Layer1 history + manifest | `record.id` global unique, timestamp parseable, source hash | Integrity audit, canonical manifest |
| Environment audit | Canonical structural columns | E1 full visibility; E2/E3 structural-only; membership exclusive | Environment membership audit |
| Continuity | E1 timestamp/segment fields | Deployment boundary; strict cadence `13 ≤ Δt ≤ 17` phút; windows 3h/8h; K candidates 3/4 | Strict, window, dependency audits |
| Applicability | Sensor validity + canonical values | Tách `low_target_eligibility` khỏi `full_point_ontology_eligibility` | Rule-specific applicability frame |
| Threshold diagnostics | E1 discovery cohort | `E1_DISCOVERY_TRAIN_V1`, Q via linear quantile; không fit E2/E3 | Candidate threshold registry + sensitivity |
| Evidence | Applicable sensor values + derived deltas | Low, thermal, moisture-rise, EC-shift; missing evidence là `NOT_EVALUABLE` | Primitive evidence frame |
| Candidate inventory | Evidence flags + continuity | Record-unique scope và fold-projection scope riêng | Combination inventory + candidate report |
| Readiness gate | Toàn bộ audit artifacts | Integrity/safety checks; `PHASE_B_DECISION_REQUIRED` không làm mất dữ liệu | `phase_a_readiness.yaml` |

## Kết quả run hiện tại

Run: `phase_a_readiness_20260731_183423`

- Overall core status: `PASS`.
- E1: 3,291 records; E2: 517; E3: 873.
- Discovery Q10 candidate: `59.96` từ 1,850 records.
- 27 records không đạt low-target eligibility.
- 2,324 records có strict previous observation; 967 strict breaks.
- EC delta có 87.2% zero-mass và vẫn là `PHASE_B_DECISION_REQUIRED`.
- Legacy comparison: `NOT_AVAILABLE`, không chặn Phase A.

## Giới hạn authority

Các file trong `candidate_resolution/`, `evidence_inventory/` và
`threshold_diagnostics/` chỉ là audit/candidate output. Phase B được phép đọc
chúng để tạo decision pack; Phase C không được dùng chúng như frozen contract.

## Artifacts chính

```text
canonical_integrity/
continuity/
technical_applicability/
threshold_diagnostics/
evidence_inventory/
candidate_resolution/
legacy_compatibility/
phase_a_readiness.yaml
```
