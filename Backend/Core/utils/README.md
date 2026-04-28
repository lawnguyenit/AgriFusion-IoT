# Tiện ích Core

`utils/` chứa helper kỹ thuật dùng chung cho các processor và pipeline trong `Core`.

- `common.py`: ép kiểu số, xử lý timestamp, thống kê cửa sổ thời gian, trend và confidence helper.
- `storage.py`: đọc/ghi JSON và JSONL.

Không đặt logic nông học, logic sensor đặc thù hoặc rule suy luận vào package này. Những phần đó nên nằm trong `processors/`, `fusion/` hoặc `canonical/`.
