# Layer2

## Mục đích

- Biến output `L1` đã align thành các CSV `L2` phục vụ ablation cho pretrain.
- Tách riêng từng nhóm feature để sau đó benchmark:
  - `Exp1`: `L1 + delta`
  - `Exp2`: `L1 + delta + 3h/8h window`
  - `Exp3`: `L1 + delta + 3h/8h window + 24h window`
  - `Exp4`: `L1 + delta + 3h/8h window + saturation`
  - `Exp5`: full `L2` set

## Input

- Mặc định đọc:
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`

## Output

- Ghi ra cùng dataset root:
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp1.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp2.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp3.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp4.csv`
  - `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_l2_exp5.csv`

## Feature groups

- `L2_DELTA`
  - `air_temp_delta_1step`
  - `soil_temp_delta_1step`
  - `soil_humidity_delta_1step`
  - `EC_delta_1step`

- `L2_WINDOW_SHORT`
  - `air_temp_slope_3h`
  - `air_temp_range_3h`
  - `air_temp_mean_3h`
  - `soil_temp_slope_3h`
  - `soil_humidity_slope_3h`
  - `soil_humidity_range_3h`
  - `EC_slope_3h`
  - `EC_range_3h`

- `L2_WINDOW_MEDIUM`
  - `air_temp_slope_8h`
  - `air_temp_range_8h`
  - `soil_temp_slope_8h`
  - `soil_temp_mean_8h`
  - `soil_humidity_slope_8h`
  - `soil_humidity_range_8h`
  - `EC_slope_8h`
  - `EC_range_8h`

- `L2_WINDOW_LONG`
  - `soil_temp_range_24h`
  - `soil_humidity_mean_24h`
  - `soil_humidity_min_24h`
  - `EC_mean_24h`
  - `EC_range_24h`
  - `EC_exposure_24h`

- `L2_SATURATION`
  - `air_humidity_saturation_flag`
  - `air_humidity_saturation_duration_3h`
  - `air_humidity_saturation_duration_8h`
  - `air_humidity_saturation_ratio_3h`
  - `air_humidity_saturation_ratio_8h`

## Command

Chạy toàn bộ ablation:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py
```

Chạy riêng một thí nghiệm:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py --experiment exp3
```

## Giả định xử lý

- `L2` cắt bỏ `pH`, `N`, `P`, `K`, `ec_npk_consistency_score`, `ec_npk_consistency_flag` khỏi main dataset.
- Mọi window đều strict backward-looking.
- `air_humidity_saturation_flag` dùng ngưỡng bão hòa hiện tại là `95.0`.
- `EC_exposure_24h` được định nghĩa là tỷ lệ thời gian trong 24h gần nhất mà `EC` nằm trên mean 24h cục bộ.

## Rủi ro hoặc giới hạn hiện tại

- `L3` relational features chưa được thêm ở bước này.
- Một số cột window dài sẽ tạo `NaN` ở đầu chuỗi; việc drop hay giữ sẽ do pretrain version tương ứng quyết định.
- Ngưỡng saturation và định nghĩa exposure hiện đang là kỹ thuật baseline để phục vụ ablation, chưa phải công thức cuối cùng của nghiên cứu.
