# Backend Core

`Backend/Core` la phan xu ly du lieu sau khi raw data da duoc keo ve
`Backend/Output_data/Layer1`.

## Cau truc

```text
Core/
|-- layer1/
|   |-- pipelines/      Dieu phoi raw Layer1 -> snapshot xu ly
|   |-- processors/     Xu ly rieng cho npk, sht30, meteo
|   `-- signals/        Feature phu tro: fuzzy_signals, external_weather
|-- fusion/             Ghep snapshot thanh bang Layer 2.5
|-- canonical/          Chuyen Layer 2.5 thanh matrix cho ML
|-- contracts/          Schema/version contract
`-- utils/              Helper dung chung, khong chua logic domain
```

## Nguyen tac

- `layer1/processors` tao khung chung: `timestamps`, `perception`, `memory`.
- `layer1/signals` tao tin hieu bo sung dua tren snapshot da chuan hoa.
- `fusion` moi flatten du lieu cho bang ML; Layer 1/Layer 2 snapshot giu cau truc de debug.
- Khong dung bucket theo gio lam truc thoi gian chinh. Truc chinh la `ts_server`.

## Ghi chu ve ten Layer

`Backend/Output_data/Layer1` hien la ten legacy cua artifact raw-ingestion sau khi
keo tu Firebase/Open-Meteo ve local. Ve mat khai niem, day gan voi `Layer0/raw`.

Chua rename thu muc nay ngay vi no anh huong den exporter, settings, pipeline, output
cu va cac script benchmark. Trong code Core, `layer1/` duoc hieu la buoc xu ly raw
artifact do thanh snapshot co cau truc. Khi repo on dinh hon co the lam migration rieng:

```text
Output_data/Layer1 -> Output_data/Layer0_raw
Core/layer1        -> Core/layer1_processing
```

## Output Layer 2 hien tai

Moi processor nen tra ve cac nhom chinh:

- `timestamps`: thoi gian server va local ISO.
- `perception`: gia tri do hien tai da chuan hoa.
- `memory`: window stats, continuity va trend theo tung metric.
- `fuzzy_signals`: toan bo fuzzy rule da evaluate, phuc vu ML.
- `external_weather`: chi co o meteo, mo ta nen am/mua/kha nang lam kho/nong lanh/tuong quan macro-micro.
