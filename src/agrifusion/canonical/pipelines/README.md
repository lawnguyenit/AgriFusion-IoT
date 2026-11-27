# Layer1 Pipeline

`preprocessing.py` la entrypoint orchestration cho canonical Layer1 pipeline.

## Luong xu ly

```text
Layer0 history/latest
    -> SourceRecord loading
    -> canonical row assembly
    -> demo exclusion
    -> segment detection + temporal features
    -> canonical validation
    -> canonical history/latest persistence
    -> segment outputs + debug/audit views + reports
    -> legacy compatibility outputs
```

## Ranh gioi trach nhiem

- pipeline chi duoc phep dieu phoi component va gom ket qua;
- processor khong doc/ghi filesystem;
- writer khong tinh domain feature;
- reporter khong duoc sua canonical rows;
- legacy adapter chi nhan canonical rows.

## Ghi chu quan trong

- mot telemetry event tu Firebase phai sinh ra toi da mot canonical row;
- packet sensor thieu khong duoc lam mat row;
- `quality` khong duoc dua vao active canonical schema;
- segment continuity la dien giai cua Layer1 dua tren `record.ts_sample`,
  khong duoc day nguoc ve Layer0;
- `delivery.buffer_reason` canonical phai la ma chuan hoa, khong duoc
  echo raw modem/Firebase log;
- `sht30/*` va `npk/*` chi la generated compatibility views.
