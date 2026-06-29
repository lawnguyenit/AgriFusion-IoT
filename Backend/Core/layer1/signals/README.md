# Layer1 Signals

## 1. Mục đích

`signals/` là lớp sinh tín hiệu giải thích sau khi processor đã chuẩn hóa dữ liệu nguồn. Nó không thay processor và cũng không thay model runtime.

Vai trò của `signals/` là:

- diễn giải snapshot theo rule có ngưỡng
- tạo risk score và pressure accumulation
- tạo tín hiệu vĩ mô cho thời tiết

## 2. Kiến trúc xử lý

```text
signals/
|-- fuzzy_signals/
|   +-- sht30.py
|   +-- npk.py
|   +-- meteo.py
|   +-- engine.py
|   +-- adapters.py
|   `-- presentation.py
`-- external_weather/
    `-- evaluator.py
```

## 3. Input

- snapshot tạm thời hoặc snapshot đã chuẩn hóa từ processor
- history cùng stream
- với `external_weather`, có thể đọc thêm peer history từ `sht30`

## 4. Output

- `fuzzy_signals`
- `external_weather`

## 5. Ví dụ kết quả

```json
{
  "signals": {
    "soil_moisture_dry_leaning": {
      "is_active": true,
      "level": "watch",
      "risk_score": 0.1995
    }
  },
  "evaluated_signal_count": 8,
  "active_signal_count": 3
}
```

## 6. Cách tái lập

Signals được chạy gián tiếp khi gọi:

```powershell
python Backend\main.py --only-layer1
```

## 7. Thư viện cần cài

- không yêu cầu package ngoài riêng
- dùng chung môi trường `Backend/requirements.txt`

## 8. Giả định xử lý

- Signal là lớp giải thích kỹ thuật, không phải ground truth bệnh hay quyết định vận hành cuối cùng.
- Threshold và rule hiện được mã hóa trong code để dễ audit từng công thức.

## 9. Rủi ro và giới hạn

- Signal mạnh không đồng nghĩa label bệnh thật.
- Nếu history quá ngắn thì pressure accumulation và trend sẽ yếu hoặc không đủ dữ liệu.
