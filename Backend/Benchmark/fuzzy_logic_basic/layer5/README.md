# Layer 5 - Risk Pathway Interpretation

Layer này không đoán bệnh. Nó chỉ giải thích drift đang trôi về pathway nào.

## Mục đích

- Lấy output Layer 4 và gán pathway giải thích.
- Phục vụ debug và đọc cho người sau.
- Cho biết hệ thống đang drift về lỗi nào nhiều hơn.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_output_prediction.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pressure.csv`
- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_temporal_dynamics.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_pathway_interpretation.csv`

## Pathway chính

- `water_stress_pathway`
- `heat_stress_pathway`
- `dry_air_pathway`
- `electrochemical_nutrient_context_pathway`
- `sensor_fault_pathway`
- `post_intervention_pathway`
- `stable_no_dominant_pathway`

## Config liên quan

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_pathways.json`

## Debug nhanh

- Nếu pathway margin quá nhỏ, có thể hệ thống đang ở trạng thái cạnh tranh giữa nhiều lỗi.
- Nếu `sensor_fault_pathway` lên cao, xem lại Layer 1 và `sensor_uncertainty` ở Layer 3.
- Nếu `post_intervention_pathway` lên cao, đối chiếu với giai đoạn vừa tưới/bón phân.

## Command

Chạy riêng:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer5\main.py
```
