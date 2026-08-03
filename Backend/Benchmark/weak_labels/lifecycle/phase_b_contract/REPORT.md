# Phase B — Semantic Contract

Phase B không phải một bước duy nhất. Nó là một chuỗi tuyến tính gồm:

1. **B1 Decision Pack** — tổng hợp bằng chứng E1 và đưa ra candidate.
2. **B2 Contract Freeze** — human review, ký quyết định và đóng semantic
   contract.

## Tóm tắt xử lý

```text
Phase A candidate evidence
→ B1: replay evidence, lập compatibility matrix, phân tích Q/K và fold support
→ human semantic review
→ B2: khóa Q/K, resolver, derived-evidence, continuity, window và provenance
→ frozen semantic contract cho Phase C
```

### B1 — Phân tích và đề xuất

B1 biến audit output thành **decision pack**: nó kiểm tra các trạng thái
evidence có quan sát được không, candidate Q/K có đủ support không, và vấn đề
nào cần quyết định. B1 không được tạo benchmark label và không được tự trở
thành authority.

### B2 — Quyết định và đóng contract

B2 nhận decision đã review, kiểm tra hash và ghi lại semantic contract bất
biến. Contract này là nguồn duy nhất để Phase C đọc threshold, công thức,
continuity, window, compatibility matrix và resolver. Nếu review chưa hoàn
tất hoặc contract thiếu trường bắt buộc, B2 dừng và không cho Phase C chạy.

```mermaid
flowchart LR
    A["Phase A PASS\nCandidate evidence"] --> B1["B1 Decision Pack\n81-state matrix + Q/K geometry"]
    B1 --> C{ "Human semantic review" }
    C -->|REJECT / AMEND| D["Contract amendment\nquay lại B1"]
    C -->|APPROVED + hash match| B2["B2 Contract Freeze\nQ/K + resolver + windows + formulas"]
    B2 --> E["Frozen semantic contract"]
    E --> F["Frozen Protocol Registry\nCONTRACT_FROZEN"]
    F --> G["Phase C preflight"]
```

## B1 — Decision Pack

### Sơ đồ B1

- [Sơ đồ tổng quan B1](b1_flow_overview.mmd)
- [Sơ đồ chi tiết B1](b1_flow_detail.mmd)

### Ngưỡng được B1 kiểm tra

Một evidence chỉ trở thành `POSITIVE` khi giá trị quan sát hoặc derived value
thỏa đúng comparator và threshold tương ứng. B1 phải báo cả **giá trị**,
**đơn vị**, **nguồn threshold** và **trạng thái authority**:

Ở đây cần tách rõ: `Q10` là **quantile level = 0.10**, còn `59.96%` là
**threshold value được tính từ Q10** trên cohort E1. Phase A tính các giá trị
candidate; B1 so sánh chúng; chỉ B2 mới được chọn Q primary và freeze giá trị.

| Evidence | Điều kiện candidate | Threshold hiện tại | Cách xác định | Trạng thái |
|---|---|---:|---|---|
| `low` | soil moisture `<=` Q | Q05 `58.65`, Q10 `59.96`, Q15 `61.127`, Q20 `62.03` `%` | Quantile tuyến tính trên `E1_DISCOVERY_TRAIN_V1` (1.850 record) | Candidate; chưa chọn primary |
| `thermal` | VPD `>=` threshold | `2.5 kPa` | Fixed reference, không fit từ E1 | Cần B2 review |
| `moisture_rise` | strict moisture delta `>=` threshold | `5 percentage points` | Fixed reference, không fit từ E1 | Cần B2 review |
| `ec_shift` | `abs(strict EC delta) >=` threshold | Q95 `6.0` (đơn vị phải đọc từ canonical schema) | Q95 trên E1 discovery; zero-mass `87.2%` | `PHASE_B_DECISION_REQUIRED` |

Vì vậy B1 không chỉ đếm số flag. Nó phải kiểm tra: threshold có provenance
không, được fit hay cố định, comparator có đúng không, dữ liệu nằm ở hai phía
threshold ra sao, và threshold đó có đủ ý nghĩa để đưa vào contract hay chưa.

`59.96`, `2.5`, `5.0` và `6.0` trong B1 đều là **candidate/reference values**;
chưa được coi là frozen authority cho Phase C cho đến khi B2 review và ký hash.

### Giá trị được so sánh với threshold

Threshold chỉ có ý nghĩa khi cách tạo giá trị đầu vào cũng được khóa:

| Evidence | Giá trị trước comparator | Dependency |
|---|---|---|
| `low` | `npk.soil_moisture_pct` | Current observation, soil sensor evaluable |
| `thermal` | `VPD = 0.6108 × exp(17.27T/(T+237.3)) × (1 - RH/100)` | `T` tính bằng °C, `RH` bằng %, SHT valid |
| `moisture_rise` | `current_moisture - strict_previous_moisture` | Strict previous observation hợp lệ |
| `ec_shift` | `abs(current_ec - strict_previous_ec)` | Strict previous observation hợp lệ |

Nếu thiếu current value hoặc dependency interval không hợp lệ, evidence phải là
`NOT_EVALUABLE`, không được biến thành `NEGATIVE`.

### Vấn đề phát hiện khi kiểm tra threshold

Code hiện tại đã dùng `2.5`, `5.0` và `6.0` để tạo candidate evidence, nhưng
hai giá trị đầu là fixed reference và chưa có bằng chứng fit từ dữ liệu. Ngoài
ra, đơn vị của `npk.ec` chưa được khai báo đầy đủ trong threshold contract.
Phase A còn chưa ghi rõ chính sách clipping RH, null/infinity và rounding cho
VPD; native Phase C yêu cầu các policy này phải có trong derived-evidence
registry để tránh Phase A và Phase C tính khác nhau.
Một rủi ro implementation khác là `PhaseBConfig` hiện chứa Q05/Q10/Q15/Q20
như default literals thay vì bắt buộc đọc và đối chiếu trực tiếp với
`Phase A threshold_registry.csv`. Trước B2, các giá trị này phải được lấy từ
artifact có hash; nếu không, B1 có thể chạy với một Q khác mà không phát hiện
được provenance mismatch.
Do đó đây là **giả định đang được audit**, không phải kết luận khoa học đã
được chứng minh. B2 bắt buộc phải quyết định lại hoặc ký rõ ba điểm này trước
khi Phase C được phép sử dụng chúng.

### Dữ liệu vào

- Phase A `PASS` run.
- Parent Protocol Registry `PHASE_A_AUDIT`.
- E1 canonical history.
- Candidate Q values từ discovery cohort.

### Xử lý có ý nghĩa khoa học

| Khối | Nội dung | Tham số/contract |
|---|---|---|
| Point contract replay | Chiếu evidence states thành candidate point resolutions | 4 evidence states; low precedence; context incomplete |
| Compatibility matrix | Liệt kê mọi tổ hợp evidence | `3^4 = 81` trạng thái: POSITIVE/NEGATIVE/NOT_EVALUABLE |
| Reachability audit | Phân biệt observed, unobserved, structurally unreachable | Không tự xóa trạng thái chưa quan sát |
| Q geometry | So sánh Q05/Q10/Q15/Q20 | Q10 `59.96` chỉ là một candidate |
| K geometry | Đếm event/anchor theo observation count | K candidate scan; chưa chọn primary K |
| Fold support | Chiếu event support vào primary/diagnostic folds | Primary 7-day; diagnostic 5-day; không dùng model score |
| Kill criteria | Ghi vấn đề cần quyết định | EC degeneracy, support, compatibility gaps |

### Output B1

```text
resolution/point_compatibility_matrix.csv
resolution/point_contract_replay.parquet
thresholds/candidate_threshold_audit.csv
thresholds/threshold_provenance_check.yaml
thresholds/threshold_boundary_cases.parquet
operationalization/qk_geometry.parquet
operationalization/k_regime_registry.csv
operationalization/qk_fold_support.csv
kill_criteria_report.yaml
phase_b1_status.yaml
```

B1 **không** tạo benchmark labels.

## B2 — Contract Freeze

### Dữ liệu vào

- B1 decision pack.
- Human-reviewed `review_decision.yaml`.
- `reviewed_decision_pack_hash` phải khớp manifest B1.
- `selected_primary_q` và `selected_primary_k` phải tồn tại trong candidate geometry.
- `selected_primary_k` phải tồn tại trong geometry scan.

### Nội dung cần đóng

```text
primary Q/K operationalization
point compatibility + resolver precedence
derived-evidence formulas, units, null policies
strict continuity and window semantics
threshold comparator and exact values
deterministic identity policy
future-target freeze timestamp
```

### Output B2

```text
semantic_contract/<run_id>/
  ontology/
  evidence/
  thresholds/
  continuity/
  operationalization/
  resolution/
  compatibility/
  provenance/
  run_metadata/
```

## Trạng thái run hiện tại

Run lịch sử: `phase_b_decision_pack_20260731_183543`

```text
status = PRIMARY_SELECTION_REVIEW_REQUIRED
selected_primary_operationalization = NONE
labels_materialized = false
model_training_performed = false
```

Vì vậy B1 hiện chỉ phù hợp để review. Chưa được dùng để gán nhãn.

## Rủi ro cần review trước B2

- EC delta có zero-mass rất cao.
- Các Q/K candidate phải được review theo fold support; B1 không tự chọn
  Q10-K3 hoặc bất kỳ operationalization nào làm primary.
- `UNRESOLVED_ENVIRONMENTAL` đang được matrix đánh dấu train-eligible; đây
  phải là quyết định khoa học rõ ràng.
- Contract B2 hiện còn cần bổ sung đầy đủ derived-evidence registry và các
  artifact mà Phase C preflight yêu cầu; không được tự điền mặc định.
