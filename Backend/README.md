# Backend Data Pipelines

`Backend` hien duoc chuan hoa theo 5 vai tro:

- `Config`: settings, path, helper IO/coercion dung chung.
- `Services`: giao tiep he ngoai va runtime online.
- `Core`: xu ly du lieu noi bo Layer0 -> Layer1 -> Layer2.5.
- `Benchmark`: build dataset, train va report nghien cuu.
- `DemoUI`: local web control panel de bam nut chay command trong buoi demo/bao cao.

## Muc dich

- Keo raw data tu Firebase RTDB, JSON export, va Open-Meteo vao Layer0.
- Tien xu ly Layer0 thanh snapshot Layer1 theo tung stream.
- Hop nhat Layer1 thanh bang Layer2.5 cho benchmark va runtime feature reuse.
- Cung cap local UI de thao tac nhanh cac command demo va benchmark dataset pipeline.

## Input

- `Backend/Services/.env`
- Firebase RTDB hoac file JSON export
- Open-Meteo API khi bat `--sync-meteo`
- raw/local artifacts duoi `Backend/Output_data`

## Output

- `Backend/Output_data/Layer0/**`
- `Backend/Output_data/Layer1/**`
- `Backend/Output_data/Layer2.5/**`
- `Backend/Output_data/Result_publish/**`
- local web page tai `http://127.0.0.1:8787` khi chay `DemoUI`

## Cau truc chuan

```text
Backend/
|-- Config/
|-- Core/
|-- DemoUI/
|-- Services/
|   |-- clients/
|   |-- layer0_ingestion/
|   |-- result_publisher/
|   |-- telemetry_runtime_simulator/
|   `-- telemetry_orchestrator/
|-- Benchmark/
|-- Output_data/
`-- main.py
```

## Command chay

```powershell
python main.py --help
python main.py --only-layer0 --source firebase --node-id Node1
python main.py --only-layer1
python main.py --only-layer2.5
python main.py --to-layer layer2.5 --source firebase --node-id Node1
python main.py --only-result --publish-result --result-mode append
python -m Backend.DemoUI.server --open-browser
```

## Gia dinh xu ly

- `Config/runtime.py` la nguon chuan cho settings runtime.
- `Services/layer0_ingestion` la package chuan cho Layer0.
- `Core` khong giu service client hay env loader.
- `DemoUI` khong chua logic xu ly du lieu; no chi boc command san co bang local web UI.
- Output data path duoc giu nguyen de khong lam gay benchmark/runtime hien tai.

## Rui ro / gioi han hien tai

- Mot phan benchmark tree lich su van con import tuyet doi kieu `Backend.*`; duong chay backend chinh da duoc kiem tra lai va van hoat dong.
- Ten folder output chua doi vat ly de tranh migration du lieu lon ngoai pham vi task.
- Cac command co pull/push Firebase van ghi du lieu that, nen chi chay khi chu y.
- `DemoUI` hien chi hien log sau khi command ket thuc, chua stream log theo thoi gian thuc.

## DemoUI

- `Backend/DemoUI` la local web control panel de bam nut chay command demo.
- Module nay khong chua logic xu ly moi; no chi goi lai command san co trong `Backend/main.py` va `Backend/Benchmark/fuzzy_logic_basic/main.py`.
- Xem them: `Backend/DemoUI/README.md`.

## Tests

Kiem tra nhe khong ghi du lieu:

```powershell
python -m py_compile Backend\main.py Backend\Config\runtime.py Backend\Services\layer0_ingestion\pipeline.py Backend\Core\layer1\pipelines\preprocessing.py Backend\DemoUI\server.py
python Backend\main.py --help
python -m Backend.DemoUI.server --help
```
