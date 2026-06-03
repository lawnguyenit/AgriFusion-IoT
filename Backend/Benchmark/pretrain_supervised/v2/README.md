# V2

## Muc dich

- Train downstream models tren embedding sinh tu `Layer2` pretrain.
- Giu ket qua tach bach theo tung ablation `exp1..exp5` va theo tung model de so sanh truc quan.

## Input

- Event CSV:
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- Pretrain checkpoint tuong ung voi tung exp:
  - `layer2_exp1`
  - `layer2_exp2`
  - `layer2_exp3`
  - `layer2_exp4`
  - `layer2_exp5`

`v2` tu tim checkpoint moi nhat phu hop voi tung exp trong:
- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs`

## Output

Moi run ghi vao:

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\outputs\<DD-MM-YYYY>\<run_name>\`

The reports still store the full timestamped `run_id`; the folder leaf is shortened to keep the tree easier to scan.

Trong do:

- `aggregate_model_metrics.csv`
  - bang tong hop toan bo model x toan bo exp
- `training_report.json`
  - tom tat toan run
- `experiments\exp1\...`
- `experiments\exp2\...`
- `experiments\exp3\...`
- `experiments\exp4\...`
- `experiments\exp5\...`

Moi folder `experiments\expN\` co:
- `embedding_dataset.csv`
- `embedding_scaler.pkl`
- `label_policy.json`
- `model_metrics.csv`
- `training_report.json`
- `run_status.json`
- `best_model.txt`
- `models\`

## Model suite

`v2` hien tai co `torch_probe` la DL head co dinh, va sklearn suite mac dinh duoc rut gon:

- `linear_probe`
- `xgboost`

Neu can doi chieu rong hon, co the mo lai cac sklearn head khac bang `--model-names`.

## Command

Chay toan bo `exp1..exp5`:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\main.py
```

Chay mot phan:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\main.py --experiments exp4 exp5
```

Smoke run:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\main.py --experiments exp5 --smoke-test
```

Backfill chi `xgboost` va `lightgbm` tren mot run da co san:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\backfill_optional_models.py --run-dir D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\outputs\<DD-MM-YYYY>\<run_name>
```

Chi backfill mot phan experiment:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\backfill_optional_models.py --run-dir D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\outputs\<DD-MM-YYYY>\<run_name> --experiments exp4 exp5
```

## Gia dinh xu ly

- Timestamp cua event CSV khop voi timestamp cua dataset da di qua `Layer2`.
- `v2` merge nhan tu event CSV vao dataset feature/pretrain theo `timestamp`.
- Label policy hien tai van tai dung chien luoc `binary/ternary` cua `v1`.
- `v2` hien la embedding-first downstream pipeline, chua fine-tune nguoc vao pretrain backbone.
- `exp6` full-set benchmark da duoc chuyen sang `v4`; `v2` chi giu single-window ablation.
- `v3` la nhom combo multi-window rieng, khong con la placeholder.

## Rui ro hoac gioi han hien tai

- Neu event CSV va dataset `Layer2` lech timestamp, so dong co nhan se giam.
- `v2` dang dung cung bo model head cua `v1`; chua co head chuyen biet chi danh rieng cho `Layer2`.
- `torch_probe` la head DL co dinh va khong nam trong `--model-names`.
- Utility `backfill_optional_models.py` chi thay the row metric cua cac model duoc chon trong run hien co; no khong rebuild embedding va khong train lai cac model con lai.
- `v3` la downstream pipeline cho Layer3 combo benchmark, khac voi `v2` va `v4`.
