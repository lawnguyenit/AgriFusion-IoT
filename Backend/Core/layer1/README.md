# Core Layer 1 Processing

Thu muc nay gom tat ca logic bien raw artifact trong `Output_data/Layer1`
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

## Vi sao meteo van co processor?

`external_weather` khong thay the `processors/meteo`.

Luong dung la:

```text
raw Open-Meteo Layer1
-> processors/meteo tao perception + memory
-> signals/fuzzy_signals tao rule features chung
-> signals/external_weather tao wetness/rain/drying/heat-cold/macro-micro
```

Processor meteo giu vai tro adapter tu raw Open-Meteo sang snapshot chuan. External
weather chi doc snapshot chuan do de tao feature domain bo sung.
