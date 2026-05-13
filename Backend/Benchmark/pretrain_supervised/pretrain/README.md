# Pretrain

## Mục đích

- Tạo embedding self-supervised từ CSV benchmark của từng fuzzy layer.
- Dùng masked feature reconstruction để học representation trước khi sang downstream supervised versions.

## Input

- `v1 / layer1`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `v2 / layer2`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp2.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp3.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp4.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp5.csv`
- `v3 / v4`
  - reserved cho output của Layer3 và Layer4

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs\<run_id>\`

Artifact chính:
- `cleaned_input.csv`
- `feature_schema.json`
- `scaler.pkl`
- `scaler_stats.json`
- `pretrain_config.yaml`
- `pretrain_report.json`
- `pretrain_checkpoint.pt`
- `validation_reconstruction_loss.json`
- `training_metrics.csv`
- `monitoring_summary.json`
- `run_status.json`

## Command

Train baseline Layer1:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v1
```

Train Layer2 ablation full set:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v2 --source-kind layer2_exp5
```

Train đúng ablation cụ thể:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\main.py --benchmark-version v2 --source-kind layer2_exp3
```

Export embedding:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\infer.py --checkpoint D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs\<run_id>\pretrain_checkpoint.pt --output-csv D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain\outputs\<run_id>\embeddings.csv --mode embedding
```

## Giả định xử lý

- `timestamp` chỉ dùng để sort, tách thời gian và tạo feature thời gian, không đưa raw timestamp trực tiếp vào model.
- Mỗi source schema khai báo rõ required columns và feature columns riêng.
- Nếu source schema vẫn có `pH/N/P/K`, pretrain sẽ xử lý theo policy của version đó.
- Nếu source schema đã bỏ `pH/N/P/K`, pretrain vẫn chạy được miễn là feature contract hợp lệ.

## Rủi ro hoặc giới hạn hiện tại

- `v3` và `v4` mới chỉ được chừa contract, chưa có relational/extended feature pipeline cuối cùng.
- Compatibility alias `Backend/Benchmark/tabnet` vẫn còn để không phá command cũ, nhưng không còn là canonical path.
