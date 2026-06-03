# Backend Core

## Mục đích

`Backend/Core` chỉ chứa logic xử lý dữ liệu nội bộ sau khi Layer0 raw artifacts đã có sẵn trên máy.

Core không còn là nơi giữ runtime settings, env loader hay service client. Những phần đó đã được gom về `Backend/Config` và `Backend/Services`.

## Input

- `Backend/Output_data/Layer0/**`
- `Backend/Output_data/Layer1/**` cho các bước fusion/canonical về sau

## Output

- `Backend/Output_data/Layer1/**`
- `Backend/Output_data/Layer2.5/**`
- dataset trung gian cho benchmark/canonical

## Cấu trúc

```text
Core/
|-- layer1/
|-- layer2/
|-- fusion/
|-- canonical/
|-- contracts/
`-- utils/              # compatibility wrapper sang Backend/Config
```

## Nguyên tắc

- `layer1/`: chuẩn hoá raw Layer0 thành snapshot theo stream.
- `layer2/`: feature builder tái sử dụng cho benchmark/runtime.
- `fusion/`: hợp nhất Layer1 thành super table Layer2.5.
- `canonical/`: đổi Layer2.5 sang format bảng/matrix cho ML.
- `utils/` không giữ implementation gốc nữa; implementation chuẩn nằm ở `Backend/Config`.

## Giả định xử lý

- Trục thời gian chính vẫn là `ts_server`.
- Schema output Layer1/Layer2.5 giữ ổn định để không làm gãy benchmark hiện có.
- `Layer1Result` là tên chuẩn cho kết quả preprocessing Layer1.

## Rủi ro / giới hạn hiện tại

- Một số tài liệu benchmark cũ vẫn có thể gọi Layer1 output bằng naming legacy.
- Output folder chưa rename vật lý để tránh migration dữ liệu lớn trong cùng đợt refactor này.
