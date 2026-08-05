# B2 selection profiles

B2 dùng hai profile đồng bộ để đo cùng một ma trận Q×K dưới hai fold policy:

- `config/qk_synchronized_7d.yaml`: toàn bộ Q×K dùng `E1_PRIMARY_7D_V1`.
- `config/qk_synchronized_5d.yaml`: toàn bộ Q×K dùng `E1_DIAGNOSTIC_5D_V1`.

Ma trận gồm `Q05/Q10/Q15/Q20-K3` và `Q10-K2/K4/K6`. `K6` là giá trị cụ thể,
không dùng alias `K_collapse`.

So sánh hai profile trước khi review B2:

```powershell
python Backend\Benchmark\weak_labels\lifecycle\phase_b_contract\main.py compare-folds `
  --phase-b1-run-dir <phase_b1_run_dir> `
  --seven-day-profile Backend\Benchmark\weak_labels\lifecycle\phase_b_contract\config\qk_synchronized_7d.yaml `
  --five-day-profile Backend\Benchmark\weak_labels\lifecycle\phase_b_contract\config\qk_synchronized_5d.yaml `
  --output <comparison_output_dir>
```

Báo cáo chỉ đo safety/support và đưa ra provisional recommendation. B2 vẫn
cần review quyết định fold chính thức; không tự điều chỉnh boundary.

Template review:

```powershell
python Backend\Benchmark\weak_labels\lifecycle\phase_b_contract\main.py template `
  --phase-b1-run-dir <phase_b1_run_dir> `
  --selection-config <selected_profile.yaml> `
  --output <review_decision.yaml>
```

Template chỉ là hồ sơ chờ review; nó không thể freeze contract cho đến khi
được điền `APPROVED`, semantic contract IDs và support thresholds theo task.
