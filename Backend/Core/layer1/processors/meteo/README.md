# Meteo processor

Package nay chua logic Layer 2 cho snapshot thoi tiet.

Nguon Open-Meteo/API fetch khong nam o day nua. Phan lay du lieu Layer 1 thuoc
`Backend/Services/layer0_ingestion/sources/open_meteo.py`.

## Cau truc

| File | Vai tro |
| --- | --- |
| `processor.py` | Chuan hoa payload meteo Layer 1 thanh snapshot Layer 2. |
| `__init__.py` | Export `MeteoProcessor`. |

## Output chinh

- `perception`: nhiet do, do am, mua, diem suong, may, nhiet do dat nong, ET0 va ma thoi tiet.
- `memory.windows`: thong ke rolling theo `1h`, `3h`, `6h`, `24h`, `72h`.
- `fuzzy_signals` va `external_weather`: feature phan tich bo sung cho meteo.
- `sensor_id` cua meteo duoc chuan hoa thanh mot target chung, nen ERA5 va IFS cung mot stream logic.

## Nguyen tac

Layer 2 khong sinh `health`, `confidence`, `handoff`, `ready` hoac canh bao nong hoc cuoi cung.
Nhung ket luan do phai thuoc tang phan tich co nguong va co so hieu chuan rieng.
