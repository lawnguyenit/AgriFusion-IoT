# Layer1 Pipeline

## Mục đích

`preprocessing.py` là entrypoint chuẩn của Layer1 preprocessing. Nó đọc Layer0 artifacts, chạy qua từng processor, rồi ghi snapshot chuẩn hoá ra `Output_data/Layer1`.

## Input

- `Backend/Output_data/Layer0/Firebase_data/**`
- `Backend/Output_data/Layer0/OpenMeteo_Data/**`

## Output

- `Backend/Output_data/Layer1/<stream>/history.jsonl`
- `Backend/Output_data/Layer1/<stream>/latest.json`
- `Backend/Output_data/Layer1/<stream>/state.json`
- `Backend/Output_data/Layer1/manifest.json`

## Data model chính

- `SourceRecord`: contract đầu vào chung cho mọi processor.
- `SourceStore`: vị trí đọc history/latest của một nguồn Layer0.
- `Layer2Target`: target output cho một stream logic.
- `Layer2RunState`: bộ nhớ tạm của một lần chạy.
- `Layer1Result`: kết quả tổng kết của pipeline sau khi chạy xong.

## Command chạy

```powershell
python Backend\main.py --only-layer1
python Backend\main.py --to-layer layer1 --source firebase --node-id Node1 --latest-only
```

## Giả định xử lý

- Pipeline chỉ điều phối, không chứa business logic sensor-specific.
- Logic cảm biến nằm trong `processors/`.
- IO, helper coercion, runtime settings được lấy từ `Backend/Config`, không tự định nghĩa lại trong pipeline.

## Rủi ro / giới hạn hiện tại

- Tên class nội bộ `Layer2Target` và `Layer2RunState` vẫn đang mang legacy naming dù pipeline đã được chuẩn hoá thành Layer1. Chúng chưa ảnh hưởng schema output nhưng có thể tiếp tục được dọn ở đợt sau.
