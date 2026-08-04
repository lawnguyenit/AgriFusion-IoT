# Weak Labels — Architecture Map

## Mục đích

Folder này mô tả **Weak Label làm gì**, theo lifecycle từ dữ liệu Layer1 đến
label authority. Đây là tài liệu kiến trúc, không phải runtime package và
không tạo thêm một execution pipeline.

## Đọc theo thứ tự

```text
00_shared → 10_phase_a → 20_phase_b1 → 30_phase_b2 → 40_phase_c → 90_handoffs
```

Mỗi phase có `README.md`, `core_flow.mmd`, `support_flow.mmd`,
`inputs_outputs.md`, và `artifact_map.md`.

## Trạng thái

```yaml
architecture_status: DOCUMENTED
runtime_changed: false
label_authority_changed: false
```

- `IMPLEMENTED`: đã có code và output quan sát được.
- `PARTIAL`: có code nhưng còn thiếu kiểm chứng hoặc output.
- `PLANNED`: thuộc thiết kế đích.
- `BLOCKED`: chưa thể đi tiếp vì thiếu tiền điều kiện.
