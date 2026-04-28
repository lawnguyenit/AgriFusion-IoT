# Tiện ích Core

`utils/` chứa helper kỹ thuật dùng chung cho pipeline và processor trong `Core`.

## File chính

| File | Vai trò |
| --- | --- |
| `common.py` | Ép kiểu số, xử lý timestamp, thống kê cửa sổ thời gian và nhãn trend mô tả. |
| `storage.py` | Đọc/ghi JSON và JSONL theo cách ổn định. |

## Nguyên tắc

Không đặt logic nông học, logic sensor đặc thù, confidence heuristic hoặc rule suy luận vào package này.

Nếu một hàm cần hiểu cảm biến cụ thể, nó nên nằm trong `processors/`. Nếu một hàm ghép nhiều nguồn, nó nên nằm trong `fusion/`. Nếu một hàm chuẩn hóa dữ liệu cho mô hình, nó nên nằm trong `canonical/`.
