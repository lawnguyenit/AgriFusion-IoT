# Tiện ích Core

`utils/` chứa helper kỹ thuật dùng chung cho pipeline và processor trong `Core`.

## File chính

| File | Vai trò |
| --- | --- |
| `common.py` | Ép kiểu số, xử lý timestamp, thống kê cửa sổ thời gian, continuity metadata, flatten derived window signals và nhãn trend mô tả. |
| `storage.py` | Đọc/ghi JSON và JSONL theo cách ổn định. |

## Window stats

`build_window_stats()` là nguồn tính toán chính cho thống kê theo thời gian.

Mặc định hiện tại phản ánh cadence thực địa mới:

- `expected_interval_sec = 1800`: kỳ vọng 1 sample mỗi 30 phút.
- `max_regular_gap_sec = 2100`: gap tối đa 35 phút vẫn được xem là đều, để bù reconnect.
- `boundary_tolerance_sec = 300`: cho phép lấy sample lệch tối đa 5 phút trước biên window.

Hàm này không xóa sample gần nhau do reset khảo sát. Thay vào đó nó báo cáo qua các field như `near_duplicate_gap_count`, `min_gap_sec`, `large_gap_count`, `sample_coverage_ratio` và `gap_continuity_ratio`.

`build_derived_window_signals()` chỉ chuyển kết quả nested trong `memory.windows` thành feature phẳng cho downstream, không tự tính lại delta/trend.

## Nguyên tắc

Không đặt logic nông học, logic sensor đặc thù, confidence heuristic hoặc rule suy luận vào package này.
