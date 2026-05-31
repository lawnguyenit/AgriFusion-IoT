# Backend Config

## Mục đích

`Backend/Config` là nguồn chuẩn duy nhất cho:

- env loader
- runtime settings
- path registry
- helper coercion/time
- JSON/JSONL storage
- CSV helper dùng chung

## Input

- `Backend/Services/.env`
- đường dẫn repo/backend hiện tại
- payload JSON/JSONL/CSV do các module khác đưa vào

## Output

- object settings/path dùng chung cho `Core`, `Services`, `Benchmark`
- helper IO và coercion tái sử dụng

## Thành phần chính

```text
Config/
|-- env.py
|-- runtime.py
|-- paths.py
|-- common.py
|-- storage.py
`-- IO/
    `-- io_csv.py
```

## Command chạy nếu có

Không có command chạy riêng. Các module này được import bởi `Backend/main.py` và các pipeline backend khác.

## Giả định xử lý

- `runtime.py` là nguồn chuẩn cho runtime settings.
- `paths.py` là nguồn chuẩn cho path nội bộ backend.
- `storage.py` là nguồn chuẩn cho JSON/JSONL IO.

## Rủi ro / giới hạn hiện tại

- `IO/io_csv.py` vẫn còn một số comment/naming cũ và có thể tiếp tục được làm gọn ở đợt kỹ thuật sau nếu cần.
