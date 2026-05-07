# Configs

Thư mục này chứa threshold, weight và mapping cho fuzzy benchmark.

## File hiện có

- `flb_membership_thresholds.json`
- `flb_pressure_weights.json`
- `flb_dynamics_config.json`
- `flb_risk_levels.json`
- `flb_pathways.json`

## Mục đích

- Tách threshold/weight ra khỏi code.
- Dễ calibrate prototype mà không cần sửa logic từng layer.
- Dễ debug theo từng nhóm rule.

## Cách dùng

- Layer 2 đọc threshold cho membership.
- Layer 3 đọc weight cho pressure.
- Layer 3.5 đọc tau / window / dynamics setting.
- Layer 4 đọc threshold cho risk level.
- Layer 5 đọc mapping pathway và scoring.

## Lưu ý

- Đây là prototype config, chưa phải calibrated field config.
- Nếu sửa config, cần chạy lại pipeline để tạo output mới trong `dataset/`.
