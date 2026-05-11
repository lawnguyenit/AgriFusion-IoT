# Dataset Outputs

Thư mục này chứa các CSV được sinh từ fuzzy benchmark pipeline.

## File output chính

- `flb_input_aligned.csv`
- `flb_input_with_events.csv`
- `flb_membership.csv`
- `flb_pressure.csv`
- `flb_temporal_dynamics.csv`
- `flb_output_prediction.csv`
- `flb_pathway_interpretation.csv`

## Mục đích

- Đây là output trung gian và output cuối của pipeline.
- Không sửa tay nếu muốn giữ tính tái lập.
- Nếu cần thay đổi, nên chạy lại pipeline từ `prepare_layer2_fuzzy.py`.

## Debug nhanh

- Nếu số dòng giữa các CSV không khớp, xem file ngay trước đó trong chuỗi layer.
- Nếu cần đối chiếu, dùng `timestamp` làm khóa chính.
- Với `flb_input_with_events.csv`, ưu tiên đọc `sample_time_local` để phân tích event và giữ `timestamp` để join với các layer sau.

## Lưu ý

- Đây là artifact sinh ra, không phải source of truth.
- Không xóa output cũ nếu chưa có yêu cầu rõ ràng.
