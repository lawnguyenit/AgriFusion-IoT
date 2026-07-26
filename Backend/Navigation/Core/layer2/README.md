# Core Layer2 Feature Builders

## 1. Mục đích

`Backend/Core/layer2` chứa các helper sinh feature time-series dùng lại cho benchmark và các bước phân tích downstream. Đây không phải là bước bắt buộc trong đường đi tối thiểu từ Firebase lên web, nhưng là một phần quan trọng để tái lập quá trình tạo đặc trưng.

## 2. Kiến trúc xử lý

```text
DataFrame đầu vào
-> builders.py
-> timeseries.py
-> feature bundle đầu ra
```

## 3. Input

DataFrame chuẩn hóa có các cột kiểu:

- `timestamp`
- `soil_temp`
- `soil_humidity`
- `air_temp`
- `air_humidity`
- `EC`

## 4. Output

- DataFrame hoặc bundle feature có:
  - cột gốc
  - cột delta
  - cột range/window
  - cột slope
  - cột saturation/exposure nếu cần

## 5. Ví dụ kết quả

```text
timestamp
soil_temp
soil_humidity
air_temp
air_humidity
EC
air_temp_delta_1step
soil_humidity_range_3h
EC_slope_3h
```

## 6. Cách tái lập

Module này được gọi gián tiếp từ benchmark dataset builder. Không có command riêng trong flow chính lên web.

## 7. Thư viện cần cài

- `numpy`
- `pandas`

## 8. Giả định xử lý

- `timestamp` là Unix epoch.
- Cửa sổ là backward-looking, không nhìn tương lai.

## 9. Rủi ro và giới hạn

- Một số ngưỡng kỹ thuật vẫn đang nằm trong code, chưa tách thành config riêng.
