# Layer1 Pipeline

## Muc dich

`preprocessing.py` la entrypoint chuan cua buoc `Layer1`. Module nay:

- nap du lieu raw da co o local sau khi Layer0 dong bo xong
- chon processor phu hop cho tung loai record
- build snapshot chuan hoa cho `sht30`, `npk`, `meteo`
- ghi `history.jsonl`, `latest.json`, `state.json`, `manifest.json`

## Kien truc xu ly

```text
Layer0 local artifacts
    -> PreprocessingPipeline._load_source_records()
    -> loop tung processor
    -> _process_source_record()
    -> _persist_targets()
    -> manifest Layer1
```

Thanh phan chinh:

- `SourceRecord`: record nguon da duoc chuan hoa tu history/latest.
- `SourceStore`: mo ta tung kho nguon local duoc phep doc.
- `Layer1Result`: tong hop ket qua cua ca lan chay.
- `Layer2Target`: mo ta dich ghi output cho tung stream.
- `Layer2RunState`: bo nho tam de giu history, state, pending rows va thong ke.

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data\history\**\*.json`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data\new_raw\latest.json`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer0\Firebase_data\new_raw\latest_meta.json`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer0\OpenMeteo_Data\**` neu co bat dong bo meteo

## Output

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1\sht30\history.jsonl`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer1\sht30\latest.json`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer1\sht30\state.json`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer1\npk\history.jsonl`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer1\meteo\history.jsonl`
- `D:\AgriFusion-IoT\Backend\Output_data\Layer1\manifest.json`

## Cac giai doan xu ly

### 1. Nap source record

- Quet tat ca file `history/*.json` cua moi `SourceStore`.
- Doc them `latest.json` va `latest_meta.json`.
- Chuan hoa du lieu thanh `SourceRecord`.
- Dedupe theo `source_name/date_key/event_key`.

### 2. Chay processor

- Moi processor tu xac dinh record co thuoc no hay khong.
- Record khong hop le se duoc dem vao `filtered_out_records`.
- Record hop le se duoc dua qua `build_snapshot()`.

### 3. Gioi han lich su tinh toan

- Pipeline khong dua toan bo lich su vao moi phep tinh nua.
- Lich su dua vao processor duoc cat theo `window_hours` lon nhat cua processor.
- Pipeline giu them 1 record ngay truoc cua so de khong mat thong tin `previous_value` va `previous_signals`.
- Muc tieu: giam do phuc tap cua lan rebuild dau tien, nhat la khi `Layer0/history` co hang nghin file.

### 4. Log tien do

Khi chay bang:

```powershell
python Backend\main.py --only-layer1
```

ban se thay log dang:

```text
--- Layer1 da nap 3811 source record tu local Layer0 ---
--- Layer1 dang chay sht30_preprocessor tren 3811 source record ---
  [sht30_preprocessor] bat dau quet source record...
  [sht30_preprocessor] da quet 500/3811 source record
  [sht30_preprocessor] da quet 1000/3811 source record
```

Log nay cho biet pipeline van dang chay, khong bi treo im lang nhu truoc.

### 5. Ghi output

- Append snapshot moi vao `history.jsonl`.
- Ghi snapshot cuoi vao `latest.json`.
- Cap nhat `state.json`.
- Ghi `manifest.json` cho toan lan chay.

## Vi du ket qua

Vi du `manifest.json`:

```json
{
  "pipeline": "layer1_preprocessing",
  "processed_source_records": 3811,
  "filtered_out_records": 0,
  "total_new_snapshots": 7622,
  "targets": {
    "npk": 3811,
    "sht30": 3811
  }
}
```

Luu y:

- So luong thuc te phu thuoc vao du lieu hop le cua tung sensor.
- `meteo` chi co output neu Layer0 da co nhanh Open-Meteo.

## Command chay

```powershell
python Backend\main.py --only-layer1
```

## Thu vien can cai

- Khong can package rieng cho module nay.
- Dung chung moi truong trong `D:\AgriFusion-IoT\Backend\requirements.txt`.

## Gia dinh xu ly

- Layer0 artifact da dung schema ma processor dang ky vong.
- Thu tu `ts_server` la co y nghia de xay dung history tang dan.
- `window_hours` cua processor phan anh dung cua so can thiet cho thong ke va fuzzy signal hien tai.

## Rui ro va gioi han hien tai

- Lan rebuild dau tien van co the ton nhieu phut neu so file Layer0 rat lon, nhung se co log tien do de theo doi.
- Ten `Layer2Target` va `Layer2RunState` la ten legacy; module nay van dang phuc vu Layer1.
- Neu `history.jsonl` cu bi sua tay, state dedupe co the khong con phan anh dung lich su thuc te.
