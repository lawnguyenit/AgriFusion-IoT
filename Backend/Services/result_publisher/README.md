# Result Publisher

## Muc dich

`result_publisher` la module noi `Layer1` voi nhanh `result/*` tren Firebase RTDB de frontend co the doc duoc:

- du lieu latest theo tung nhom cam bien
- lich su de ve chart
- ket qua runtime classification
- forecast / anomaly / recommendation phuc vu dashboard

Day la buoc cuoi cua backend truoc khi web hien thi ket qua.

## Kien truc xu ly

```text
Layer1 local artifact
-> load latest.json + history.jsonl theo tung group
-> dung feature runtime tu lich su chung timestamp
-> tim runtime model phu hop
-> predict diagnosis
-> build forecast / rule signals / anomalies / recommendations
-> ghi local debug artifact
-> publish len Firebase result/*
```

## Input

- `Backend/Output_data/Layer1/sht30/history.jsonl`
- `Backend/Output_data/Layer1/sht30/latest.json`
- `Backend/Output_data/Layer1/npk/history.jsonl`
- `Backend/Output_data/Layer1/npk/latest.json`
- `Backend/Output_data/Layer1/meteo/history.jsonl` neu co
- `Backend/Output_data/Layer1/meteo/latest.json` neu co
- artifact model trong `Backend/Benchmark/tabular_benchmark/artifacts/four_class/training/**`
- fallback artifact trong `Backend/Benchmark/tabular_benchmark/artifacts/binary/training/**`
- `Backend/Services/.env`

## Output

### Firebase RTDB

- `result/meta`
- `result/pipeline`
- `result/latest`
- `result/history/{air,soil,npk,weather}`
- `result/analysis`

### Local debug artifact

- `Backend/Output_data/Result_publish/latest_result_payload.json`
- `Backend/Output_data/Result_publish/latest_publish_manifest.json`
- `Backend/Output_data/Result_publish/result_sync_state.json`
- `Backend/Output_data/Result_publish/report_charts/chart_manifest.json`
- `Backend/Output_data/Result_publish/report_charts/*.svg`
- `Backend/Output_data/Result_publish/report_charts/*.png`

## Command chay

### Snapshot full

```powershell
python -m Backend.main --only-result --publish-result --result-mode snapshot --result-payload-scope full
```

### Append an toan

```powershell
python -m Backend.main --only-result --publish-result --result-mode append --result-payload-scope full
```

### Chi publish latest + analysis

```powershell
python -m Backend.main --only-result --publish-result --result-mode append --result-payload-scope diagnosis-only
```

### Chon runtime experiment

```powershell
python -m Backend.main --only-result --publish-result --result-mode append --result-runtime-experiment auto
python -m Backend.main --only-result --publish-result --result-mode append --result-runtime-experiment v0
python -m Backend.main --only-result --publish-result --result-mode append --result-runtime-experiment v1
python -m Backend.main --only-result --publish-result --result-mode append --result-runtime-experiment v2
```

### Dry-run

```powershell
python -m Backend.main --only-result --publish-result --result-mode append --result-dry-run
```

## Vi du ket qua

### `result/meta`

```json
{
  "source": "server",
  "payloadScope": "full",
  "lastPublishedTs": 1778387046
}
```

### `result/latest`

```json
{
  "air": {
    "ts": 1778387046,
    "temperature_c": 35.09,
    "humidity_pct": 69.09
  },
  "soil": {
    "ts": 1778387046,
    "humidity_pct": 55.8
  }
}
```

## Gia dinh xu ly

- `Layer1` artifact local da ton tai va con su dung duoc.
- Frontend doc truc tiep contract `result/*`.
- Runtime model hien tai uu tien lane `four_class` de tra truc tiep:
  - `normal_context`
  - `packet_loss_outage`
  - `water_deficit`
  - `rain_or_fertigation_context`
- Neu local artifact `four_class` khong san sang, publisher moi fallback ve lane `binary`.
- `weather` la nhanh opportunistic; neu khong co `Layer1/meteo`, cac nhanh con lai van publish duoc.

## Thu vien can cai

- `numpy`
- `pandas`
- `scikit-learn`
- `joblib`
- `matplotlib`
- `xgboost`
- `firebase-admin`

## Rui ro va gioi han

- Runtime hien tai uu tien `four_class`, nhung moi runtime loader `xgboost` duoc dung trong pha publish online.
- Forecast hien tai la heuristic tu slope/range, khong phai mo hinh du bao rieng.
- Neu artifact model cu tham chieu duong dan legacy, publisher phai remap path truoc khi load.
- Tu ban sua nay, `result-mode append` khong con tu dong roi xuong `snapshot` khi mat `result_sync_state.json`.
  Khi state local bi mat, publisher se append theo tung node con de tranh xoa `result/history` dang ton tai tren Firebase.
