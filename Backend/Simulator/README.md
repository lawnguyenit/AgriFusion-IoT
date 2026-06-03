# Simulator

## Muc dich cua module

`Backend/Simulator` sinh ra du lieu mo phong de train va benchmark.

Module nay:
- doc seed tu `Backend/Output_data/Layer1`
- align seed theo cung logic voi benchmark fuzzy layer1
- sinh record moi theo timeline co `normal_context` xen ke giua cac `event episode`
- xuat ra CSV rieng co schema giong `flb_input_aligned.csv`

Module nay khong append vao dataset that dang co.

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`

Seed duoc lay tu `history.jsonl` va `latest.json` cua:
- `sht30`
- `npk`

Sau do module tai su dung logic benchmark trong:
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer1\alignment.py`

## Output

Moi lan chay sinh mot thu muc moi:

- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_input.csv`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_input_labeled.csv`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_gap_aware.csv`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\label_summary.json`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\augmentation_taxonomy.json`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\generation_manifest.json`

Trong do:
- `synthetic_flb_input.csv`: giu schema giong `flb_input_aligned.csv`
- `synthetic_flb_input_labeled.csv`: them nhan scenario va metadata synthetic
- `synthetic_flb_gap_aware.csv`: giu du ca timestamp du kien, ke ca cac moc outage cua `packet_loss`
- `label_summary.json`: thong ke so record moi nhan
- `augmentation_taxonomy.json`: thong ke du lieu synthetic dang duoc sinh theo nhom `rule_based_simulation`, `missing_value_simulation`, `gaussian_noise_augmentation` hay `seed_replay_baseline`
- `generation_manifest.json`: mo ta run, seed va output files

## Schema CSV

File `synthetic_flb_input.csv` giu dung 10 cot:

- `timestamp`
- `soil_temp`
- `soil_humidity`
- `air_temp`
- `air_humidity`
- `EC`
- `pH`
- `N`
- `P`
- `K`

File labeled them:
- `scenario_label`
- `timeline_state`
- `episode_id`
- `phase_name`
- `is_synthetic`
- `scenario_intensity`
- `scenario_progress`
- `effect_strength`
- `source_seed_timestamp`

File gap-aware them nua:
- `record_present`
- `system_context`
- `recovery_hint`

## Scenario hien co

- `packet_loss`
- `rain_or_fertigation_context`
- `water_deficit`

## Gia dinh xu ly theo scenario

Tat ca scenario deu duoc sinh theo co che:
- `normal gap`
- `onset`
- `peak`
- `stabilizing`
- `recovery`

Khong con sinh 300 dong lien tiep cung mot nhan.

- `packet_loss`:
  - mo phong mat nguon do thieu nang luong mat troi
  - khong co record duoc gui len trong suot outage
  - neu outage roi vao dem thi co the sang moi moi co kha nang phuc hoi
- `rain_or_fertigation_context`:
  - la nhan canonical gop cho 2 bieu hien `rain_humid_context` va `fertigation_spike`
  - neu episode roi vao khung 05:00 -> 08:00 thi mutation nghieng ve tuoi-bon
  - neu episode roi vao khung gio am/mua con lai thi mutation nghieng ve mua-am
  - output `scenario_label` cuoi cung van chi la `rain_or_fertigation_context`
  - neu user van truyen `rain_humid_context` hoac `fertigation_spike` qua `--scenario`, CLI se tu dong merge count ve nhan canonical nay
- `water_deficit`:
  - uu tien khung 09:00 -> 17:00
  - do am dat giam dan
  - EC tang nhe

Ngoai cac event row, timeline con sinh them `normal_context` de du lieu giong telemetry tu nhien hon.

## Command chay

Tu root repo:

```powershell
python -m Backend.Simulator.main
```

Mac dinh simulator se:
- giu count tuyet doi nhu truoc day
- sinh 3 nhan abnormal canonical:
  - `packet_loss = 300`
  - `rain_or_fertigation_context = 600`
  - `water_deficit = 300`
- them `600` dong `normal_context`
- rai event thanh nhieu episode ngan co normal gap xen giua de timeline tu nhien hon

Chi dinh scenario rieng:

```powershell
python -m Backend.Simulator.main --scenario packet_loss:300:0.8 --scenario rain_or_fertigation_context:600:0.85
```

Su dung mot phan seed Layer1 gan nhat:

```powershell
python -m Backend.Simulator.main --seed-limit 1200
```

Khong che tong so dong normal:

```powershell
python -m Backend.Simulator.main --normal-count 600
```

Nhan toan bo count len 3 lan, nhung van giu co che setup so record cho tung event:

```powershell
python -m Backend.Simulator.main --count-multiplier 3
```

Vi du neu truoc day ban dang dung `300` moi event thi lenh tren se thanh `900` moi event va `1800` dong `normal_context`.

Neu muon set tay count lon hon theo tung event:

```powershell
python -m Backend.Simulator.main --normal-count 1800 --scenario packet_loss:900:0.8 --scenario rain_or_fertigation_context:1800:0.85 --scenario water_deficit:900:0.85
```

Bat che do auto-target theo kich thuoc `train real` khi can:

```powershell
python -m Backend.Simulator.main --use-real-train-target --target-real-train-multiplier 3
```

Chi dinh truc tiep so dong `real train` de tranh phai estimate lai:

```powershell
python -m Backend.Simulator.main --use-real-train-target --real-train-row-count 4200 --target-real-train-multiplier 3
```

Canh chinh tham so split neu muon auto-target bam sat cau hinh benchmark hien tai:

```powershell
python -m Backend.Simulator.main --use-real-train-target --label-scheme option2_4class --train-ratio 0.70 --validation-ratio 0.15 --test-ratio 0.15 --purge-gap-minutes 1440 --split-strategy coverage_aware_temporal
```

## Gia dinh sizing va taxonomy

- Manual mode la mac dinh; `--normal-count` va `--scenario name:count:intensity` van la count tuyet doi.
- `--count-multiplier` nhan dong loat toan bo count de khong phai viet lai tung scenario.
- Auto-target chi tac dong tong so dong synthetic; no khong doi schema CSV.
- Khi auto-target dang bat, `--normal-count` va phan `count` trong `--scenario name:count:intensity` duoc xem la weight phan bo.
- `packet_loss` duoc xep primary vao `missing_value_simulation`, nhung manifest van ghi ro no co phu thuoc secondary vao `rule_based_simulation` vi khung gio va duration outage duoc sap lich theo rule.
- `rain_or_fertigation_context` va `water_deficit` duoc xep vao `rule_based_simulation`.
- `normal_context` duoc giu thanh `seed_replay_baseline` de tach ro khoi augmentation event.
- `gaussian_noise_augmentation` hien khong duoc su dung; `augmentation_taxonomy.json` se thong ke ro `used=false`.

## Rui ro hoac gioi han hien tai

- `packet_loss` trong CSV chi la bieu dien gian tiep, khong phai mat goi that o tang truyen.
- `packet_loss` duoc mo ta dung hon o file gap-aware; benchmark CSV se tu nhien bi thieu timestamp trong outage.
- Chua sinh weather/meteo.
- Cac scenario hien la rule-based, chua dung mo hinh tao sinh hoc sau.
- Neu bat auto-target, kich thuoc `real train` se duoc suy ra tu `flb_input_with_events.csv` va split config; neu benchmark doi ratio hoac label scheme thi nen truyen lai tham so tuong ung.
- File benchmark CSV va file labeled duoc tach rieng de tranh lam ban dataset that, nhung khi train can chon dung file dau vao.
- Ban dau chua cho overlap nhieu event; moi timestamp chi co toi da 1 primary context.
- Tong so normal hien duoc khong che bang `--normal-count` trong manual mode, va duoc suy ra theo weight trong auto-target mode.
