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
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer1\ec_npk_consistency.py`

## Output

Moi lan chay sinh mot thu muc moi:

- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_input.csv`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_input_labeled.csv`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\synthetic_flb_gap_aware.csv`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\label_summary.json`
- `D:\AgriFusion-IoT\Backend\Simulator\outputs\<run_id>\generation_manifest.json`

Trong do:
- `synthetic_flb_input.csv`: giu schema giong `flb_input_aligned.csv`
- `synthetic_flb_input_labeled.csv`: them nhan scenario va metadata synthetic
- `synthetic_flb_gap_aware.csv`: giu du ca timestamp du kien, ke ca cac moc outage cua `packet_loss`
- `label_summary.json`: thong ke so record moi nhan
- `generation_manifest.json`: mo ta run, seed, EC model va output files

## Schema CSV

File `synthetic_flb_input.csv` giu dung 12 cot:

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
- `ec_npk_consistency_score`
- `ec_npk_consistency_flag`

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
- `rain_humid_context`
- `fertigation_spike`
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
- `rain_humid_context`:
  - uu tien khung gio toi den sang
  - nhiet do khong khi giam
  - do am khong khi tang cao
- `fertigation_spike`:
  - uu tien khung 05:00 -> 08:00
  - do am khong khi va do am dat tang
  - NPK va EC tang
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

Mac dinh sinh 4 scenario, moi scenario 300 record, va them `600` dong `normal_context`.
So dong event van duoc giu theo tung scenario, nhung se duoc rai thanh nhieu episode ngan co normal gap xen giua.

Chi dinh scenario rieng:

```powershell
python -m Backend.Simulator.main --scenario packet_loss:300:0.8 --scenario fertigation_spike:300:0.9
```

Su dung mot phan seed Layer1 gan nhat:

```powershell
python -m Backend.Simulator.main --seed-limit 1200
```

Khong che tong so dong normal:

```powershell
python -m Backend.Simulator.main --normal-count 600
```

## Rui ro hoac gioi han hien tai

- `packet_loss` trong CSV chi la bieu dien gian tiep, khong phai mat goi that o tang truyen.
- `packet_loss` duoc mo ta dung hon o file gap-aware; benchmark CSV se tu nhien bi thieu timestamp trong outage.
- Chua sinh weather/meteo.
- Cac scenario hien la rule-based, chua dung mo hinh tao sinh hoc sau.
- File benchmark CSV va file labeled duoc tach rieng de tranh lam ban dataset that, nhung khi train can chon dung file dau vao.
- Ban dau chua cho overlap nhieu event; moi timestamp chi co toi da 1 primary context.
- Tong so normal hien duoc khong che bang `--normal-count`, khong de no tang vo han theo chieu dai timeline nua.
