# Layer0 Ingestion

## Mục đích

`Backend/Services/layer0_ingestion` là package chuẩn để materialize raw source vào `Output_data/Layer0`.

## Input

- Firebase RTDB snapshot hoặc latest/current path
- file RTDB JSON export
- Open-Meteo API
- `Backend/Services/.env`

## Output

- `Backend/Output_data/Layer0/Firebase_data/new_raw/*`
- `Backend/Output_data/Layer0/Firebase_data/history/**`
- `Backend/Output_data/Layer0/OpenMeteo_Data/**`

## Cấu trúc

```text
layer0_ingestion/
|-- pipeline.py
|-- sources/
|-- stores/
|-- sync/
|-- utils/
`-- docs/
```

## Command chạy

```powershell
python Backend\main.py --only-layer0 --source firebase --node-id Node1
python Backend\main.py --only-layer0 --source json-export --input-json C:\path\to\export.json --node-id Node1 --full-history
python Backend\main.py --only-layer0 --sync-meteo --meteo-mode all
```

## Giả định xử lý

- `Layer0IngestionPipeline` là entrypoint chuẩn.
- `FirebaseRTDBClient` là client chuẩn khi source là Firebase.
- `Backend/Config/runtime.py` và `Backend/Config/storage.py` là nguồn chuẩn cho settings và IO dùng chung.

## Rủi ro / giới hạn hiện tại

- `sources/firebase.py` vẫn hỗ trợ cả normalized snapshot root và legacy latest/current path để không làm gãy runtime data đang tồn tại trên RTDB.
