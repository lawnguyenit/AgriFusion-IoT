# Fuzzy Logic Basic

Module nay la mat bang dau tien cho Layer2/fuzzy.

## Cau truc

- `prepare_layer2_fuzzy.py`: CLI entrypoint.
- `materialize.py`: thin shim, chi giu API cap root.
- `core/runner.py`: orchestration layer.
- `core/loader.py`: doc Layer1 va build index theo family.
- `core/anchors.py`: anchor-time features, ERA window, EC fit.
- `core/qc.py`: staleness, coverage, residual checks.
- `core/rules.py`: pressure fusion va reason codes.
- `core/dynamics.py`: accumulated / velocity / acceleration.
- `core/rows.py`: build 1 row CSV theo anchor_time.
- `core/writer.py`: CSV + manifest writer.
- `core/model.py`: dataclass va constant dung chung.
- `membership/functions.py`: membership functions continuous `[0, 1]`.
- `Backend/Config/data_utils.py`: helper dung chung cho `safe_float`, `safe_int`, `iso_from_ts`.

## Muc tieu

- Doc du lieu da chuan hoa tu `Backend/Output_data/Layer1`.
- Tao CSV theo `anchor_time`, khong lay record moi nhat toan cuc.
- Tach ro IFS(t), ERA(t), membership, pressure, temporal dynamics, va explanation.

## Input

- `Backend/Output_data/Layer1/**/history.jsonl`
- `Backend/Output_data/Layer1/**/latest.json` neu co

## Output

- `Backend/Output_data/Layer2/fuzzy/layer2_fuzzy.csv`
- `Backend/Output_data/Layer2/fuzzy/manifest.json`

## Chay

```powershell
python Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py
```

Script nay co the chay truc tiep theo duong dan file; entrypoint se tu bo sung repo root vao `sys.path`.

Dry run theo so dong:

```powershell
python Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py --limit 50
```

## Gia dinh

- Anchor time la union timestamp cua cac stream Layer1.
- SHT30/NPK duoc su dung lam cot co so cho pressure canh tac.
- Meteo duoc tach thanh IFS current-state va ERA rolling history 5 ngay.
- EC duoc fit line tinh don gian tu NPK sum de lam kiem tra nguon/cam bien.
- Chi cac anchor co du SHT30, NPK va meteo current-state moi duoc ghi vao CSV.
- `Layer2/fuzzy` la dataset CSV; JSON chi dung cho manifest.
- Helper parse/coerce co dung chung nen de trong `Backend/Config/data_utils.py`.

## Gioi han

- Day la baseline fuzzy basic, chua phai engine rule final.
- Temporal dynamics phu thuoc vao thu tu anchor time hien co, khong thay the calibration theo vu/crop stage.
- Root folder chi nen giu entrypoint va shim; logic da nam trong `core/` va `membership/`.
