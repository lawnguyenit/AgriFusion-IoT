# Telemetry Runtime Simulator

## 1. Mục đích

`telemetry_runtime_simulator` tạo dữ liệu demo có kiểm soát trong Firebase RTDB để trình diễn luồng từ inject -> Layer0 -> Layer1 -> publish -> web mà không cần chờ node thật.

## 2. Kiến trúc xử lý

```text
đọc latest/current làm seed
-> chọn template
-> dựng sequence demo
-> ghi Node1/telemetry/<date>/<event>
-> cập nhật latest/current và latest/meta
-> ghi status event phục vụ audit
```

## 3. Template hỗ trợ

- `0`: `normal_context`
- `1`: `packet_loss_outage`
- `2`: `water_deficit`
- `3`: `rain_or_fertigation_context`
- `4`: alias tương thích ngược của template `3`

## 4. Input

- `Node1/latest/current`
- `Node1/latest/meta`
- tùy chọn `Node1/telemetry/<date>`
- `template_id`
- `inject_date_key`
- `inject_sample_datetime`

## 5. Output

- `Node1/telemetry/<date>/<event>`
- `Node1/latest/current`
- `Node1/latest/meta`
- `Node1/live`
- `Node1/status_events/<event>_demo`

## 6. Chế độ hoạt động

### 6.1. Single-record injection

- inject một record tại một timestamp

### 6.2. Bootstrap baseline

- tạo nền bình thường từ `00:00 -> 12:00`

### 6.3. Episode injection

- tạo chuỗi record sau 12h theo một pattern cụ thể

## 7. Ví dụ kết quả

```json
{
  "template_id": 2,
  "template_name": "water_deficit",
  "telemetry_path": "Node1/telemetry/2026-05-20/1779258600",
  "sample_ts": 1779258600
}
```

## 8. Cách tái lập

### 8.1. Inject một record

```powershell
python Backend\main.py --inject-telemetry-template 0
```

### 8.2. Inject một record tại thời điểm xác định

```powershell
python Backend\main.py --inject-telemetry-template 2 --inject-sample-datetime 2026-05-20T14:30
```

### 8.3. Bootstrap baseline

```powershell
python Backend\main.py --demo-bootstrap-day --server-cycle-skip-super-table
```

## 9. Thư viện cần cài

- `firebase-admin`
- `python-dotenv`

## 10. Giả định xử lý

- Firebase đã có `latest/current` hợp lệ để làm seed cấu trúc.
- Ngày demo mặc định `2026-05-20` được giữ riêng cho mục đích trình diễn.

## 11. Rủi ro và giới hạn

- Dữ liệu demo là dữ liệu tổng hợp có kiểm soát, không dùng làm ground truth train.
- Chạy lặp lại trên cùng timestamp sẽ ghi đè record cũ.
