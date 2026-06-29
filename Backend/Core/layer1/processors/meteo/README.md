# Bộ xử lý Meteo

## 1. Mục đích

Module này chuẩn hóa dữ liệu thời tiết từ Open-Meteo thành stream `meteo` trong `Layer1`.

Nó không fetch API trực tiếp. Việc lấy dữ liệu thuộc `Backend/Services/layer0_ingestion/sources/open_meteo.py`.

## 2. Kiến trúc xử lý

```text
raw meteo từ Layer0
-> MeteoProcessor
-> perception
-> memory.windows
-> fuzzy_signals
-> external_weather
```

## 3. Input

- `packet.meteo_data`
- metadata nguồn từ `SourceRecord`
- history meteo cùng stream
- peer history `sht30` cho phần `external_weather`

## 4. Output

- stream output: `Backend/Output_data/Layer1/meteo/*`
- perception chính:
  - `temp_air_c`
  - `humidity_air_pct`
  - `rain_mm`
  - `precipitation_mm`
  - `dew_point_c`
  - `cloud_cover_pct`
  - `soil_temp_0_7cm_c`
  - `et0_mm`

## 5. Kiến trúc dữ liệu đặc thù

- ERA5 archive và IFS forecast cùng được nhập vào một stream logic `meteo`.
- `external_weather` được tính thêm để phản ánh:
  - nền ẩm
  - mưa
  - drying demand
  - quan hệ macro-micro với SHT30

## 6. Ví dụ kết quả

```json
{
  "processor_name": "meteo_preprocessor",
  "sensor_id": "meteo",
  "provider": "open-meteo-ifs",
  "perception": {
    "temp_air_c": 28.2305,
    "humidity_air_pct": 80.0,
    "rain_mm": 0.0,
    "cloud_cover_pct": 99.0,
    "et0_mm": 0.0359
  }
}
```

## 7. Cách tái lập

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1 --sync-meteo --meteo-mode all
python Backend\main.py --only-layer1
```

## 8. Thư viện cần cài

- `openmeteo-requests`
- `requests-cache`
- `retry-requests`

Phần processor dùng lại môi trường chung `Backend/requirements.txt`.

## 9. Giả định xử lý

- nhiệt độ, độ ẩm và mưa là các trường lõi bắt buộc để nhận record meteo
- `sensor_id` của meteo được chuẩn hóa về một target chung

## 10. Rủi ro và giới hạn

- meteo forecast ở runtime vẫn là dữ liệu ngoại sinh, không phải đo tại vườn
- `external_weather` là lớp diễn giải bổ sung, không phải ground truth
