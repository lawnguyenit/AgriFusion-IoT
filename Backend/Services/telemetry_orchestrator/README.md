# Telemetry Orchestrator

## 1. Mục đích

`telemetry_orchestrator` nối nhiều bước rời rạc thành một chu kỳ demo hoàn chỉnh:

- inject telemetry demo
- sync dữ liệu đó về `Layer0`
- chạy `Layer1`
- tùy chọn chạy `SuperTable`
- publish `result/*`

## 2. Kiến trúc xử lý

```text
telemetry_runtime_simulator
-> layer0_ingestion
-> Core/layer1
-> Core/fusion (optional)
-> result_publisher
```

## 3. Input

- `Backend/Services/.env`
- Firebase telemetry dưới `Node1/telemetry`
- local backend pipeline đã cài đủ

## 4. Output

- local artifact trong `Backend/Output_data`
- dữ liệu `result/*` trên Firebase

## 5. Chế độ hoạt động

### 5.1. `run_once`

- latest-only cycle

### 5.2. `bootstrap_demo_day`

- inject nền bình thường `00:00 -> 12:00`

### 5.3. `run_demo_cycle`

- inject episode sau 12h và sync theo `ts` range

## 6. Ví dụ kết quả

```json
{
  "status": "completed",
  "injected_template_name": "water_deficit",
  "export_status": "new_data",
  "layer1_status": "ok",
  "result_status": "published",
  "result_label": "abnormal"
}
```

## 7. Cách tái lập

### 7.1. Chạy cycle latest-only

```powershell
python Backend\main.py --server-cycle-once --server-cycle-skip-super-table
```

### 7.2. Bootstrap baseline

```powershell
python Backend\main.py --demo-bootstrap-day --server-cycle-skip-super-table
```

### 7.3. Chạy episode demo

```powershell
python Backend\main.py --server-cycle-demo --inject-telemetry-template 2 --server-cycle-skip-super-table
```

## 8. Thư viện cần cài

- toàn bộ môi trường `Backend/requirements.txt`

## 9. Giả định xử lý

- Baseline nên được chạy trước khi inject episode sau 12h.
- `SuperTable` là tùy chọn trong demo cycle, không bắt buộc để publish lên web.

## 10. Rủi ro và giới hạn

- Đây là orchestrator one-shot, không phải daemon theo dõi liên tục.
- Episode demo hiện tối ưu cho flow một ngày demo, chưa phải replay engine tổng quát nhiều ngày.
