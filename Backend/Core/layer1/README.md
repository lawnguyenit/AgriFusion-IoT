# Core Layer 1 Processing

Thu muc nay gom tat ca logic bien raw artifact trong `Output_data/Layer0`
thanh snapshot xu ly co cau truc.

## Thanh phan

```text
layer1/
|-- pipelines/preprocessing.py
|-- processors/
|   |-- npk/
|   |-- sht30/
|   `-- meteo/
`-- signals/
    |-- fuzzy_signals/
    `-- external_weather/
```

## Ranh gioi

- `processors`: chuan hoa payload va tinh `memory.windows`.
- `fuzzy_signals`: rule/fuzzy cho tat ca sensor.
- `external_weather`: tin hieu thoi tiet bo sung rieng cho meteo va quan he macro-micro voi SHT30.
- `fusion/canonical`: nam ngoai `layer1` vi do la buoc hop bang va tao matrix cho ML.

## Meteo realtime va archive

Open-Meteo van co 2 luong o Layer0:

```text
Output_data/Layer0/OpenMeteo_Data/Meteo_archive_era5
Output_data/Layer0/OpenMeteo_Data/Meteo_forecast_ifs
```

Layer1 khong coi day la hai stream doc lap nua. Processor meteo gop IFS + ERA5
thanh mot stream logic duy nhat:

```text
Output_data/Layer0/OpenMeteo_Data/Meteo_archive_era5
Output_data/Layer0/OpenMeteo_Data/Meteo_forecast_ifs
-> Output_data/Layer1/meteo
```

- `meteo_archive_era5` dung lam bootstrap/backfill ban dau.
- `meteo_forecast_ifs` dung de mo rong latest va cap nhat cac ngay gan hien tai.
- Layer1 se tu dong gom archive khi history archive da ton tai; flag `--include-meteo-archive-layer1` chi la override cuong biet.

## Vi sao meteo van co processor?

`external_weather` khong thay the `processors/meteo`.

Luong dung la:

```text
raw Open-Meteo Layer0
-> processors/meteo tao perception + memory
-> signals/fuzzy_signals tao rule features chung
-> signals/external_weather tao wetness/rain/drying/heat-cold/macro-micro
```

Processor meteo giu vai tro adapter tu raw Open-Meteo sang snapshot chuan. External
weather chi doc snapshot chuan do de tao feature domain bo sung.
