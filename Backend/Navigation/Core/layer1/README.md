# Core Layer1

`Backend/Core/layer1` theo huong canonical-first.

## Muc dich

Layer1:

- nap raw telemetry tu `Layer0/Firebase_data`;
- build mot canonical telemetry history, moi row ung voi mot Firebase event;
- danh dau continuity segment theo `record.ts_sample` de tach cac khoang van hanh bi ngat dai;
- sinh latest snapshot, debug views, feature catalog, quality reports;
- sinh compatibility outputs `sht30/*`, `npk/*`, `meteo/*` tu canonical history khi consumer cu van ton tai.

## Module map

- `contracts/`
  - field catalog, typed Layer1 contracts, build stats
- `loaders/`
  - source loading tu Layer0 history/latest
- `processors/`
  - SHT30 packet
  - NPK packet
  - sensor status/fault
  - record/delivery/network/device context
  - canonical row assembly
  - temporal + segment features
- `validation/`
  - invariant checks va unknown catalog field policy
- `writers/`
  - canonical persistence, segment outputs, debug views, audit artifacts
- `reports/`
  - feature catalog, missingness, variance, duplicate-field, processing report
- `publishers/`
  - legacy compatibility outputs chi doc canonical rows
- `pipelines/`
  - orchestration only

## Dependency direction

```text
contracts <- loaders
contracts <- processors
contracts <- validation
contracts <- writers
contracts <- reports
contracts <- publishers

loaders/processors -> pipelines -> validation/writers/reporters/publishers
```

## Output chinh

- `Output_data/Layer1/canonical/telemetry_history.parquet`
- hoac fallback `Output_data/Layer1/canonical/telemetry_history.csv`
- `Output_data/Layer1/canonical/telemetry_latest.json`
- `Output_data/Layer1/canonical/feature_catalog.csv`
- `Output_data/Layer1/views/*.csv`
- `Output_data/Layer1/segments/segments_manifest.json`
- `Output_data/Layer1/segments/<segment_id>/canonical/*`
- `Output_data/Layer1/quality_reports/*.csv|json`
- `Output_data/Layer1/excluded/excluded_records.csv`

## Compatibility

Neu consumer cu van doc:

- `Output_data/Layer1/sht30/history.jsonl`
- `Output_data/Layer1/sht30/latest.json`
- `Output_data/Layer1/npk/history.jsonl`
- `Output_data/Layer1/npk/latest.json`
- `Output_data/Layer1/meteo/history.jsonl`
- `Output_data/Layer1/meteo/latest.json`

thi cac file nay duoc sinh lai tu canonical source-of-truth, khong con la pipeline xu ly song song.

## Ghi chu schema moi

- canonical history van la source-of-truth hop nhat;
- `record.segment_id`, `record.segment_index`,
  `record.segment_boundary_before`,
  `record.segment_expected_interval_sec` chi dien giai continuity trong
  Layer1, khong sua raw Layer0;
- `record.delta_prev_sec`, `record.gap_flag`,
  `record.missing_slot_count` duoc tinh lai trong pham vi tung segment;
- `delivery.buffer_reason` chi giu taxonomy da chuan hoa;
- raw buffer/modem log duoc dua ra
  `quality_reports/buffer_reason_audit.csv`, khong nam trong active
  canonical schema;
- `feature_catalog.csv` co them governance fields:
  `feature_role`, `used_by_label_rule`, `rule_proxy_level`,
  `split_only`, `allowed_views`, `forbidden_views`;
- `eligible_for_model` duoc giu lai nhu cot compatibility suy ra tu
  governance moi.

## Khong con dung

- quality score legacy lam analytical evidence;
- filter bo row chi vi packet sensor bi thieu;
- stream meteo la source-of-truth ngang hang voi telemetry canonical.

## Detailed Flow

For implemented control flow, input/output behavior, and recommended
code reading order, see [FLOW.md](FLOW.md).
