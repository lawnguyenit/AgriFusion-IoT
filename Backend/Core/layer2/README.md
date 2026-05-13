# Core Layer2

## Mục đích

- Chứa các helper dùng chung để sinh feature theo time window cho L2.
- Tách phần toán feature ra khỏi benchmark orchestration để `fuzzy_logic_basic/layer2` chỉ còn lo input/output và ablation.

## Input

- DataFrame đã có:
  - `timestamp`
  - `soil_temp`
  - `soil_humidity`
  - `air_temp`
  - `air_humidity`
  - `EC`

## Output

- DataFrame feature bundle với:
  - các cột base giữ nguyên
  - các cột delta / window / saturation dùng lại cho các thí nghiệm `exp1..exp5`

## Command

- Không có command riêng. Module này được gọi từ `Backend/Benchmark/fuzzy_logic_basic/layer2`.

## Giả định xử lý

- `timestamp` là Unix epoch theo UTC.
- Cửa sổ đều là strict backward-looking, không dùng dữ liệu tương lai.
- Các hàm duration/ratio theo saturation và exposure được tính theo khoảng thời gian giữa các bản ghi.

## Rủi ro / giới hạn hiện tại

- Các ngưỡng như saturation hiện đang cấu hình cục bộ trong code, chưa đưa ra JSON config riêng.
- Exposure cho `EC` hiện được định nghĩa là tỷ lệ thời gian trong 24h mà `EC` nằm trên mean 24h cục bộ; đây là định nghĩa kỹ thuật để phục vụ ablation, không phải ground truth vật lý cuối cùng.
