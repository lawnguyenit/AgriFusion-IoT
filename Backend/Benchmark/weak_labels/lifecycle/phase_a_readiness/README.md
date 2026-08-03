# Phase A — Data Audit / Readiness

Phase A nối tiếp dữ liệu `Layer1 canonical` và kiểm tra nó trước khi xây
semantic contract. Đây là **audit-only**, không phải label builder.

```text
Layer1 canonical
→ identity/provenance + environment membership
→ duplicate/timestamp/source-hash audit
→ technical applicability + continuity/window audit
→ candidate evidence và candidate threshold trên E1
→ readiness report cho Phase B
```

## Phạm vi

- E1 được đọc đầy đủ để audit và tính diagnostic evidence.
- E2/E3 chỉ structural-audit theo Protocol Registry.
- Canonical values không bị sửa.
- Không materialize Point, Same-Y hoặc Temporal labels.
- Không chọn Q/K primary và không freeze resolver.

## Q và threshold trong Phase A

`Q05`, `Q10`, `Q15`, `Q20` là **quantile levels**. Phase A dùng chúng để
tính các candidate threshold values trên `E1_DISCOVERY_TRAIN_V1`:

```text
Q05 → candidate moisture threshold
Q10 → candidate moisture threshold
Q15 → candidate moisture threshold
Q20 → candidate moisture threshold
```

Phase A không quyết định Q10 là semantic contract. B1 so sánh các candidate;
B2 mới chọn và freeze operationalization.

## Tài liệu

- [Báo cáo Phase A](REPORT.md)
- [Sơ đồ tổng quan](flow_overview.mmd)
- [Sơ đồ chi tiết](flow_detail.mmd)

## Output authority

Các output của Phase A trong `artifacts/phase_a/<run_id>/` là audit/candidate
evidence. Chúng được Phase B đọc để review, nhưng không được Phase C dùng như
frozen label contract.
