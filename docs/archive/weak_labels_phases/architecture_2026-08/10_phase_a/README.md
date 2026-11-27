# Phase A — Data Audit và Candidate Evidence

```yaml
status: IMPLEMENTED
authority: SUPPORT_AND_CANDIDATE
next_consumer: B1
label_authority: false
```

## Nhiệm vụ chính

Phase A nối tiếp Layer1 để đọc, kiểm tra và chuẩn hóa cách quan sát dữ liệu
trước khi B1 phân tích threshold/persistence.

```text
Layer1 canonical
  → environment membership
  → integrity/applicability
  → continuity/window evidence
  → primitive evidence và Q candidates
```

Phase A không sửa canonical values, không chọn Q/K primary, không tạo label
authority và không train model.

E1 được audit đầy đủ. E2/E3 bị structural/sealed theo Protocol Registry.
