# Core Layer1

## 1. Mục đích

`Backend/Core/layer1` là nơi biến raw artifact của `Layer0` thành snapshot đã chuẩn hóa theo từng stream logic:

- `sht30`
- `npk`
- `meteo`

Mỗi snapshot được thiết kế để:

- giữ lại dữ liệu đo đã chuẩn hóa
- thêm thống kê cửa sổ thời gian
- thêm signal giải thích được
- vẫn đủ đơn giản để debug lại từ raw

## 2. Kiến trúc xử lý

```text
layer1/
|-- pipelines/
|   `-- preprocessing.py
|-- processors/
|   |-- sht30/
|   |-- npk/
|   `-- meteo/
`-- signals/
    |-- fuzzy_signals/
    `-- external_weather/
```

## 3. Luồng xử lý nội bộ

```text
SourceRecord
-> processor theo stream
-> snapshot perception + memory
-> fuzzy_signals
-> external_weather (chỉ cho meteo)
-> history.jsonl / latest.json / state.json
```

## 4. Input

- `Backend/Output_data/Layer0/Firebase_data/**`
- `Backend/Output_data/Layer0/OpenMeteo_Data/**`

## 5. Output

- `Backend/Output_data/Layer1/sht30/*`
- `Backend/Output_data/Layer1/npk/*`
- `Backend/Output_data/Layer1/meteo/*`
- `Backend/Output_data/Layer1/manifest.json`

## 6. Ý nghĩa từng thành phần

- `processors/`: bóc và chuẩn hóa payload nguồn.
- `signals/fuzzy_signals/`: sinh tín hiệu mức độ, trend, risk score từ snapshot.
- `signals/external_weather/`: sinh tín hiệu thời tiết vĩ mô, nền ẩm, mưa, drying demand cho meteo.
- `pipelines/`: điều phối toàn bộ lần chạy và ghi output.

## 7. Ví dụ kết quả

```json
{
  "processor_name": "sht30_preprocessor",
  "sensor_id": "sht30_1",
  "perception": {
    "temp_air_c": 35.09,
    "humidity_air_pct": 69.09
  },
  "memory": {
    "window_hours": [3, 6, 24, 72]
  },
  "fuzzy_signals": {
    "evaluated_signal_count": 5
  }
}
```

## 8. Cách tái lập

```powershell
python Backend\main.py --only-layer1
```

Nếu cần build từ đầu:

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1
python Backend\main.py --only-layer1
```

## 9. Thư viện cần cài

- `numpy`
- `pandas`

## 10. Giả định xử lý

- Processor không được phép kéo dữ liệu trực tiếp từ Firebase.
- Raw phải đi qua `Layer0` trước khi vào `Layer1`.
- Mỗi stream có `history.jsonl`, `latest.json`, `state.json` riêng để debug độc lập.

## 11. Rủi ro và giới hạn

- Dữ liệu sparse hoặc mất continuity sẽ làm một số window chuyển sang `insufficient_samples`.
- Các signal ở đây là signal giải thích kỹ thuật, chưa phải kết luận nghiệp vụ cuối cùng.
