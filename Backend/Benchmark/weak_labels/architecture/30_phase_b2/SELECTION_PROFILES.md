# B2 selection profiles

Mỗi lần freeze B2 nhận một selection profile YAML riêng.

Profile hiện hành:

`lifecycle/phase_b_contract/config/q10_k3_primary_diagnostics.yaml`

- Primary: `Q10-K3` trên `E1_PRIMARY_7D_V1`.
- Diagnostic: `Q05/Q15/Q20×K3` và `Q10×K2/K4/K6` trên
  `E1_DIAGNOSTIC_5D_V1`.

`K6` là giá trị cụ thể; không dùng tên ẩn như `K_collapse`. Muốn thử cấu hình
khác, tạo một YAML profile khác và chạy B2 như một run riêng.
