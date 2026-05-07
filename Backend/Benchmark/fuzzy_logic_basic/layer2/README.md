# Layer 2 - Fuzzy Membership

Layer này chuyển input đã align ở Layer 1 thành fuzzy membership `[0, 1]`.

## Mục đích

- Biến raw/context feature thành membership có ý nghĩa fuzzy.
- Đây là layer membership, chưa phải risk cuối.
- `pH` chỉ dùng như context risk chậm, không xem như fast temporal signal.

## Input

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_input_aligned.csv`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\dataset\flb_membership.csv`

## Membership output chính

- `soil_humidity_low`
- `soil_humidity_high`
- `soil_humidity_dropping`
- `soil_humidity_rising`
- `soil_temperature_low`
- `soil_temperature_high`
- `soil_temperature_rising`
- `air_temperature_low`
- `air_temperature_high`
- `air_temperature_rising`
- `air_humidity_low`
- `air_humidity_high`
- `air_humidity_dropping`
- `EC_low_context`
- `EC_high`
- `EC_rising`
- `EC_shift_24h`
- `EC_risk`
- `pH_context_risk`

## Cột phụ trợ trong CSV

- `warmup_ready_24h`
- `gap_hours_since_prev`
- `soil_humidity_slope_3h`
- `soil_temp_slope_3h`
- `air_temp_slope_3h`
- `air_humidity_slope_3h`
- `EC_slope_3h`
- `ec_delta_24h_strict`
- `ec_npk_consistency_score`
- `ec_npk_consistency_flag`

Lưu ý:
- `N`, `P`, `K` không còn xuất ra Layer 2 CSV.
- `ec_delta_24h_strict` chỉ có giá trị khi đã có lịch sử ít nhất 24 giờ.
- Layer 2 mặc định bỏ warm-up 24 giờ đầu, nên CSV đầu ra thường bắt đầu từ khoảng ngày 2/4 nếu input bắt đầu từ 1/4.
- `timestamp` trong CSV là Unix epoch theo UTC; nếu đối chiếu theo giờ địa phương thì mốc warm-up 24 giờ có thể rơi sang ngày 2/4 dù nhìn UTC vẫn thấy cuối ngày 1/4.

## Config liên quan

- `D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\configs\flb_membership_thresholds.json`

## Debug nhanh

- Kiểm tra `timestamp` có tăng dần và không bị trùng.
- Kiểm tra output membership có nằm trong `[0, 1]`.
- Kiểm tra cột nào bị NaN thì phải truy về Layer 1 input.

## Command

Chạy riêng:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\layer2\main.py
```

Khi chạy trực tiếp, mặc định script sẽ:
- đọc `flb_input_aligned.csv`
- ghi `flb_membership.csv`
- in số dòng và đường dẫn input/output ra console

Chạy cả pipeline:

```powershell
python D:\AgriFusion-IoT\Backend\Benchmark\fuzzy_logic_basic\prepare_layer2_fuzzy.py
```
