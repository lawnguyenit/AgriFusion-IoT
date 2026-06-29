# Backend Core

## 1. Mục đích

`Backend/Core` chứa phần xử lý dữ liệu nội bộ sau khi raw artifact đã được kéo về máy. Đây là nơi diễn ra logic chuẩn hóa dữ liệu và hợp nhất dữ liệu, tách biệt hoàn toàn với phần giao tiếp Firebase/API.

## 2. Kiến trúc xử lý

```text
Core/
|-- layer1/
|   +-- pipelines/
|   +-- processors/
|   `-- signals/
|-- fusion/
|-- layer2/
|-- canonical/
|-- contracts/
`-- utils/
```

Vai trò từng nhánh:

- `layer1/`: đọc raw Layer0 và tạo snapshot theo stream.
- `fusion/`: hợp nhất snapshot thành `SuperTable`.
- `layer2/`: helper sinh feature time-window cho benchmark và reuse.
- `canonical/`: chuyển `SuperTable` sang dạng bảng chuẩn cho mô hình downstream.

## 3. Vị trí trong luồng

```text
Layer0 raw local
-> Core/layer1
-> Backend/Output_data/Layer1
-> Core/fusion
-> Backend/Output_data/SuperTable
```

## 4. Input

- `Backend/Output_data/Layer0/**`
- `Backend/Output_data/Layer1/**` cho các bước fusion/canonical về sau

## 5. Output

- `Backend/Output_data/Layer1/**`
- `Backend/Output_data/SuperTable/**`
- dữ liệu trung gian cho benchmark/canonical

## 6. Ví dụ kết quả

### 6.1. Snapshot theo stream

```json
{
  "sensor_id": "npk_7in1_1",
  "timestamps": {
    "ts_server": 1778387046
  },
  "perception": {
    "n_ppm": 43.0,
    "soil_humidity_pct": 55.8
  }
}
```

### 6.2. Hàng trong SuperTable

```json
{
  "ts_server": 1778387046,
  "sht30__sht30_1__perception__temp_air_c": 35.09,
  "npk__npk_7in1_1__perception__n_ppm": 43.0
}
```

## 7. Điểm cần đọc kỹ để tránh hiểu sai

- Tên pipeline hiện tại là `Layer1`, nhưng snapshot từng stream vẫn ghi `layer = "layer2"` trong payload do legacy contract.
- README giải thích lại để audit hiểu đúng, nhưng đợt này không đổi schema vì sẽ ảnh hưởng benchmark và runtime đang có.

## 8. Thư viện cần cài

- `numpy`
- `pandas`

## 9. Giả định xử lý

- `ts_server` là trục thời gian chuẩn.
- `Core` không tự đọc `.env` và không tự kết nối dịch vụ ngoài.
- Mọi path và settings đều đi qua `Backend/Config`.

## 10. Rủi ro và giới hạn

- Một số tên class/naming vẫn mang dấu vết lịch sử, nhất là vùng `layer1/pipelines`.
- Đổi contract output ở đây sẽ kéo theo thay đổi ở `Services/result_publisher`, `Benchmark` và `Frontend`.
