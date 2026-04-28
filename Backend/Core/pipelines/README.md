# Pipeline preprocessing

`preprocessing.py` là entry chính của Layer 2.

## Luồng chạy

1. Load artifact Layer 1 từ các source store đã cấu hình.
2. Chuẩn hóa mỗi artifact thành `SourceRecord`.
3. Đưa từng `SourceRecord` qua các processor (`sht30`, `npk`, `meteo`).
4. Processor nào nhận diện được sensor thì tạo snapshot Layer 2.
5. Ghi `history.jsonl`, `latest.json`, `state.json` và `manifest.json`.

## Data model

- `SourceRecord`: contract đầu vào chung cho mọi processor.
- `SourceStore`: vị trí đọc history/latest của một nguồn Layer 1.
- `Layer2Target`: vị trí ghi output cho một stream/sensor cụ thể.
- `Layer2RunState`: bộ nhớ tạm trong một lần chạy pipeline.
- `Layer2Result`: kết quả tổng kết sau khi chạy.

## Nguyên tắc

Pipeline chỉ điều phối. Nó không nên chứa logic riêng của SHT30, NPK hoặc Meteo.

Nếu cần sửa cách đọc/ghi hoặc chống trùng record, sửa tại pipeline. Nếu cần sửa cách hiểu dữ liệu cảm biến, sửa trong `processors/`.
