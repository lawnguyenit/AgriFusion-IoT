# Fuzzy Logic Basic

## Mục đích

`fuzzy_logic_basic/` là family active cho phần chuẩn bị dữ liệu benchmark.

Module này chịu trách nhiệm:

- align Layer1 lịch sử cảm biến
- gắn `big_label` cho dữ liệu real
- sinh export feature Layer2 và Layer3

Nó không còn là nơi train mô hình downstream.

## Input

- `D:\AgriFusion-IoT\Backend\Output_data\Layer1`
- metadata Firebase phục vụ `real_event_labeling`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_with_events.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv` tới `flb_l2_exp6.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l3_combo1.csv` tới `flb_l3_combo4.csv`
- các build report JSON trong cùng folder `dataset/`

## Command

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\main.py
```

Chạy riêng bước gắn nhãn real:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\real_event_labeling\main.py
```

## Giả định

- `flb_input_with_events.csv` là labeled artifact upstream chuẩn cho `direct_benchmark` và `context_classifier`
- `big_label` hiện đủ tín hiệu để build các ladder `binary`, `tri_class`, và `four_class`

## Rủi ro / giới hạn

- label real vẫn là heuristic, chưa phải ground truth tuyệt đối
- nếu taxonomy nhãn thay đổi sâu, cần cập nhật lại mapping từ `big_label` trong shared label registry
