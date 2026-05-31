# Backend Services

## Mục đích

`Backend/Services` chứa phần giao tiếp hệ ngoài và runtime pipeline online:

- đọc/ghi Firebase RTDB
- ingest Layer0 từ source ngoài
- publish runtime result
- inject telemetry demo
- orchestration cho server/demo cycle

## Input

- `Backend/Services/.env`
- Firebase RTDB
- file JSON export nếu chạy offline
- local artifacts trong `Backend/Output_data`
- runtime model artifacts trong `Backend/Benchmark`

## Output

- Layer0 raw artifacts trong `Backend/Output_data/Layer0`
- payload `result/*` trên Firebase
- debug artifacts trong `Backend/Output_data/Result_publish`

## Cấu trúc chuẩn

```text
Services/
|-- clients/
|   `-- firebase_rtdb.py
|-- layer0_ingestion/
|-- result_publisher/
|-- telemetry_runtime_simulator/
`-- telemetry_orchestrator/
```

## Command chạy

```powershell
python Backend\main.py --help
python Backend\main.py --only-layer0 --source firebase --node-id Node1
python Backend\main.py --inject-telemetry-template 2
python Backend\main.py --server-cycle-once
python Backend\main.py --only-result --publish-result --result-mode append
```

## Giả định xử lý

- Package chuẩn cho Layer0 là `Services/layer0_ingestion`.
- Client chuẩn cho Firebase là `FirebaseRTDBClient`.
- Shared settings/path/helper được lấy trực tiếp từ `Backend/Config`.

## Rủi ro / giới hạn hiện tại

- Runtime service vẫn phụ thuộc vào schema output hiện có của Layer1/Layer2.5 để không làm gãy frontend và benchmark đang tồn tại.
