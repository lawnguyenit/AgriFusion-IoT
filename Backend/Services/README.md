# Backend Services

## 1. Muc dich

`Backend/Services` chua toan bo lop giao tiep voi he thong ben ngoai va cac pipeline runtime online. Nhom nay khong phu trach feature engineering hay huan luyen; no tap trung vao:

- doc/ghi/xoa du lieu tren Firebase RTDB
- keo raw telemetry ve local Layer0
- inject du lieu demo
- dieu phoi server cycle online
- publish payload `result/*` cho web
- cleanup va cat output local theo moc bao cao

## 2. Kien truc xu ly

```text
Services/
|-- clients/
|   `-- firebase_rtdb.py
|-- layer0_ingestion/
|-- telemetry_runtime_simulator/
|-- telemetry_orchestrator/
|-- result_publisher/
`-- output_cutoff_maintenance/
```

## 3. Vai tro tung module

- `clients/`: client chuan cho Firebase RTDB, ho tro `pull_data`, `set_data`, `update_data`, `delete_data`.
- `layer0_ingestion/`: keo du lieu tu Firebase hoac nguon export ve `Backend/Output_data/Layer0`.
- `telemetry_runtime_simulator/`: tao goi tin demo theo template de test web va runtime model.
- `telemetry_orchestrator/`: noi chuoi inject demo -> sync Layer0 -> Layer1 -> publish result.
- `result_publisher/`: doc artifact local, dung payload `result/*`, day len Firebase cho frontend.
- `output_cutoff_maintenance/`: cat local output sau mot moc ngay de giu workspace dung pham vi bao cao.

## 4. Input

- `Backend/Services/.env`
- `Backend/Services/.env.example`
- khoa Firebase service account
- Firebase RTDB
- artifact local trong `Backend/Output_data`
- artifact benchmark/model trong `Backend/Benchmark`

## 5. Output

- `Backend/Output_data/Layer0/**`
- `Backend/Output_data/Result_publish/**`
- nhanh `result/*` tren Firebase
- du lieu demo trong `Node1/telemetry/*`
- cac thao tac cleanup tren Firebase khi can reset buoi demo

## 6. Vi du ket qua

### 6.1. Raw local

```text
Backend/Output_data/Layer0/Firebase_data/new_raw/latest.json
Backend/Output_data/Layer0/Firebase_data/history/2026/05/10/node1_1778386998.json
```

### 6.2. Payload web

```text
result/meta
result/latest
result/history/air
result/analysis
```

### 6.3. Cleanup demo

Cleanup utility co the:

- xoa `result`
- xoa `Node1/telemetry/<demo-date>`
- xoa `Node1/status_events/*_demo`
- phuc hoi `Node1/latest/current`, `Node1/latest/meta`, `Node1/live` ve ngay that duoc chi dinh

## 7. Cach tai lap

```powershell
copy Backend\Services\.env.example Backend\Services\.env
python Backend\main.py --help
python Backend\main.py --only-layer0 --source firebase --node-id Node1
python Backend\main.py --inject-telemetry-template 2
python Backend\main.py --server-cycle-demo --inject-telemetry-template 2 --server-cycle-skip-super-table
python Backend\main.py --only-result --publish-result --result-mode snapshot
python Backend\cleanup_demo_state.py --demo-date-key 2026-05-20 --restore-latest-date-key 2026-05-19
```

## 8. Thu vien can cai

- `firebase-admin`
- `python-dotenv`
- `openmeteo-requests`
- `requests-cache`
- `retry-requests`
- `numpy`
- `pandas`
- `scikit-learn`
- `joblib`
- `matplotlib`
- `xgboost`

## 9. Gia dinh xu ly

- `FirebaseRTDBClient` la client chuan cho RTDB.
- `Layer0IngestionPipeline` la entrypoint chuan cho ingestion.
- `ResultPublisherPipeline` la entrypoint chuan cho publish len web.
- cleanup demo yeu cau `restore-latest-date-key` van con telemetry that tren Firebase de phuc hoi cac node `latest/*` va `live`.

## 10. Rui ro va gioi han

- cac service command nay ghi len Firebase that neu khong chay `dry-run`
- cleanup demo xoa truc tiep node RTDB, vi vay can dung dung `demo-date-key`
- runtime web hien van phu thuoc vao schema `Layer1` va payload `result/*` hien tai
- file `.env` that phai giu local; chi commit `.env.example`
