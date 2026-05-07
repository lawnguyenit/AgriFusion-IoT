# Layer 1 - FLB Input Alignment

Layer này chịu trách nhiệm biến dữ liệu trong `Backend/Output_data/Layer1` thành CSV input sạch cho fuzzy pipeline.

## Mục đích

- Chọn `timestamp` master.
- Gộp sensor data về một dòng aligned.
- Tính `ec_npk_consistency_score`.
- Chuyển `ec_npk_consistency_flag` sang nhị phân.
- Không sinh fuzzy membership, pressure, risk hoặc pathway.

## Input

- Thư mục mặc định: `D:\AgriFusion-IoT\Backend\Output_data\Layer1`
- Các file JSON/JSONL trong `history/` và `latest/` của Layer 1.

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\manifest.json`

## Schema CSV

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

## Quy ước consistency

- `ec_npk_consistency_flag = 1` nếu score >= 0.9
- `ec_npk_consistency_flag = 0` nếu score < 0.9

## Command debug

Chạy mặc định qua entrypoint gốc:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py
```

Nếu cần debug riêng Layer 1:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer1\main.py
```

## Điểm cần xem lại khi lỗi

- File input có bị thay đổi schema không.
- Có duplicate record do `latest.json` và `history.jsonl` không.
- Có thiếu cột `timestamp`, `EC`, `N`, `P`, `K`, `soil_temp`, `soil_humidity`, `air_temp`, `air_humidity`, `pH` không.
- Nếu row count lệch bất thường, xem lại bước normalize theo `timestamp`.
