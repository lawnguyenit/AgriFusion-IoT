# Lõi xử lý Backend

`Backend/Core` là lớp xử lý dữ liệu nghiên cứu của backend. Nhiệm vụ của phần này là biến artifact có thể tái lập ở Layer 1 thành snapshot Layer 2 theo từng nguồn, hàng dữ liệu hợp nhất Layer 2.5, và bảng dữ liệu chuẩn để phục vụ benchmark hoặc huấn luyện mô hình.

Mục tiêu của cấu trúc này là làm rõ luồng xử lý, tăng khả năng tái lập, và giúp người đọc repo truy vết được dữ liệu từ telemetry thô đến dữ liệu sẵn sàng cho mô hình.

## Cấu trúc

```text
Core/
|-- contracts/
|   `-- schemas.py
|-- processors/
|   |-- npk/
|   |-- sht30/
|   `-- meteo/
|-- pipelines/
|   `-- preprocessing.py
|-- fusion/
|   `-- layer25.py
|-- canonical/
|   `-- tabnet_super_table.py
|-- utils/
|   |-- common.py
|   `-- storage.py
`-- __init__.py
```

## Vai trò từng phần

### `processors/`

Chứa logic xử lý riêng cho từng nguồn dữ liệu ở Layer 2.

- `npk/`: dữ liệu đất, NPK, pH, EC, độ ẩm đất.
- `sht30/`: nhiệt độ và độ ẩm không khí.
- `meteo/`: dữ liệu thời tiết Open-Meteo, đánh giá độ tin cậy và snapshot thời tiết.

Mỗi processor nên tách rõ:

- `processor.py`: tạo snapshot Layer 2.
- `health.py`: đánh giá độ tin cậy của dữ liệu.
- `README.md`: ghi chú giả định, ngưỡng và phạm vi của nguồn dữ liệu.

### `pipelines/`

Chứa pipeline điều phối. `preprocessing.py` đọc artifact Layer 1, gọi các processor theo nguồn, sau đó ghi lịch sử Layer 2, latest snapshot, state và manifest.

### `fusion/`

Chứa logic hợp nhất nhiều nguồn. `layer25.py` ghép các snapshot Layer 2 thành hàng dữ liệu Layer 2.5, kèm thông tin độ phủ nguồn và cờ sẵn sàng cho TabNet.

### `canonical/`

Chứa bộ dựng bảng dữ liệu chuẩn cho mô hình. Phần này chuyển dữ liệu đã fusion thành bảng sạch hơn để dùng cho benchmark hoặc huấn luyện.

### `contracts/`

Chứa marker/schema version cho các hợp đồng dữ liệu. Khi cấu trúc payload thay đổi, cần cập nhật và ghi chú tại đây để phục vụ tái lập.

### `utils/`

Chứa helper kỹ thuật dùng chung, ví dụ xử lý thời gian, ép kiểu số, thống kê cửa sổ và đọc/ghi JSON. Không đặt logic nông học hoặc logic sensor đặc thù trong package này.

## API chính

```python
from Core import PreprocessingPipeline, Layer25FusionPipeline
from Core.processors import NPKProcessor, SHT30Processor, MeteoProcessor
from Core.canonical import TabNetSuperTableBuilder
```

## Lý do thiết kế

Cấu trúc này giúp repo thể hiện rõ tư duy kỹ thuật nghiên cứu:

- boundary của từng nguồn dữ liệu được tách rõ,
- pipeline điều phối tách khỏi processor đơn lẻ,
- fusion tách khỏi preprocessing,
- bảng canonical tách khỏi pipeline vận hành,
- schema version hỗ trợ tái lập và kiểm chứng,
- helper kỹ thuật không che lấp logic miền.
