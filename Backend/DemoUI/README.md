# DemoUI

## Muc dich

`D:\AgriFusion-IoT\Backend\DemoUI` hien la mot giao dien thao tac nhanh theo giai doan.

Muc tieu cua UI:

- chon giai doan bang so
- chi hien cac nut chuc nang lien quan den giai doan dang chon
- neu action can tham so thi hien form nho ben trai
- command/log chi hien ben phai nhu terminal output
- stream log realtime, co dry run, stop command, return code va duration

UI nay khong thay doi pipeline xu ly du lieu. No chi dieu phoi va giam sat cac command da ton tai.

## Kien truc xu ly

```text
browser local
-> DemoUI server.py
-> doc command_registry.json
-> render quick stage selector + action grid
-> /api/run goi subprocess
-> /api/state cap nhat terminal/progress
-> /api/overview van san co cho audit/helper backend
```

Thanh phan chinh:

- `server.py`: web server local, command runner, dry run, stop, last run metadata.
- `command_registry.json`: registry stage + action + `quick_ui` de render giao dien thao tac nhanh.
- `pipeline_audits.py`: helper audit/check/preview/summary cho tung stage.
- `last_runs.json`: duoc sinh sau moi lan run de luu metadata gan nhat theo stage.

## Input

Dashboard goi cac script co san trong repo:

- `D:\AgriFusion-IoT\Backend\main.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\main.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\real_labeling\main.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\benchmark_dataset\single_window_features\main.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\prepare.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\train.py`
- `D:\AgriFusion-IoT\Backend\Benchmark\tabular_benchmark\report.py`

Form tham so nhanh hien tai:

- `single_date`
- `from_date`
- `to_date`
- `feature_version`
- `date_key`
- `template_id`
- `packet_gap_minutes`
- `label_mode`
- `model_target`
- `result_runtime_experiment`
- `experiments`
- `dry_run`
- `smoke_test`
- `skip_super_table`

## Output

- local web page tai `http://127.0.0.1:8787`
- layout 2 cot: control trai, terminal phai
- stage selector `[1] [2] [3] [4] [5] [6]`
- action grid 2 cot cho stage dang chon
- terminal/log realtime
- progress/status
- command dang chay
- last run metadata theo stage

## Bo cuc UI

- cot trai: stage selector, form tham so, action buttons
- cot phai: command/terminal output
- khong hien toan bo pipeline cung luc
- khong dung card lon kieu landing page

## Quick stages

Mat chinh hien 6 giai doan thao tac:

1. `Keo du lieu`
2. `Tao Layer`
3. `Tao du lieu train`
4. `Train mo hinh`
5. `Dua len web`
6. `Demo nhanh`

Registry backend 9 stage van duoc giu lai cho audit/reporting, nhung UI chinh chi render 6 quick stage.

## Command registry

`command_registry.json` la contract render action va quick stage.

Moi action co metadata:

- `id`
- `stage_id`
- `title`
- `description`
- `command_preview`
- `danger_level`
- `allow_dry_run`
- `allow_overwrite`
- `expected_outputs`

Moi backend stage co metadata:

- `id`
- `title`
- `role`
- `inputs`
- `outputs`
- `warning`
- `status_note`

Phan `quick_ui` bo sung:

- `stages`: 6 stage giao dien
- `fields`: schema field can render o panel tham so
- `action_ids`: danh sach nut can hien cho moi quick stage

## Audit helpers

`pipeline_audits.py` hien ho tro:

- `overview`
- `raw-count`
- `validate-layer1`
- `sensor-quality`
- `telemetry-gaps`
- `preview-aligned`
- `alignment-summary`
- `label-distribution`
- `label-mapping`
- `label-audit-report`
- `preview-labeled`
- `feature-summary`
- `feature-compare`
- `feature-nan-check`
- `split-summary`
- `rare-class-coverage`
- `purge-gap`
- `training-feature-columns`
- `excluded-label-columns`
- `leakage-checklist`
- `limitations-summary`
- `export-defense-audit`

## Muc do map voi flow active

- `v0` map voi raw tabular source `benchmark_input_aligned.csv` full sensor + chemistry.
- `v1` map voi raw tabular source `benchmark_input_aligned.csv` subset moi truong + EC.
- `v2` map voi raw tabular source `single_window_exp2.csv`.
- UI train se dua `feature_version` ve `--experiments` neu user khong override tay.

## Command chay

```powershell
python -m Backend.DemoUI.server
python -m Backend.DemoUI.server --open-browser
python -m Backend.DemoUI.server --port 8899
```

Chay audit helper truc tiep:

```powershell
python -m Backend.DemoUI.pipeline_audits overview
python -m Backend.DemoUI.pipeline_audits label-distribution
python -m Backend.DemoUI.pipeline_audits split-summary --label-mode binary
```

## Thu vien can cai

- khong them dependency rieng cho web server
- `pipeline_audits.py` dung `pandas`, vi vay can moi truong trong `D:\AgriFusion-IoT\Backend\requirements.txt`

## Gia dinh xu ly

- moi lan chi chay 1 command active de tranh ghi chong output
- dry run chi in command va check expected outputs, khong thuc thi
- command dangerous level `high` can confirm tren UI neu khong o dry run
- overview metric duoc doc tu local artifact hien co, khong truy cap mang
- quick stage co the group action tu nhieu backend stage khac nhau, nhung command run van dung registry action goc

## Rui ro va gioi han hien tai

- progress bar van la heuristic, khong phai phan tram chinh xac tuyet doi cua moi pipeline
- mot so nut audit/preview la helper noi bo duoc xay de doc artifact local, khong phai pipeline khoa luan moi
- repo hien tai report active la markdown + PNG; dashboard khong tuyen bo co HTML/PDF neu artifact do chua ton tai
- `Stop current command` gui terminate; kha nang dung ngay con phu thuoc vao process con
- `Copy log` phu thuoc vao clipboard API cua trinh duyet local
