# Lõi xử lý Backend

`Backend/Core` là lớp xử lý dữ liệu nghiên cứu của backend. Nhiệm vụ của phần này là biến artifact Layer 1 thành snapshot Layer 2 theo từng nguồn, bảng hợp nhất Layer 2.5, và dữ liệu canonical cho benchmark hoặc mô hình học máy.

Mục tiêu thiết kế hiện tại là thận trọng: Layer 2 ưu tiên dữ liệu đo, kiểm tra chất lượng trực tiếp từ packet, và thống kê mô tả. Các kết luận nông học hoặc confidence heuristic không nằm ở đây nếu chưa có cơ sở hiệu chuẩn rõ ràng.

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

- `npk/`: dữ liệu đất gồm N, P, K, pH, EC, nhiệt độ đất và độ ẩm đất.
- `sht30/`: nhiệt độ và độ ẩm không khí.
- `meteo/`: dữ liệu thời tiết Open-Meteo.

Mỗi processor nên giữ ba nhóm chính:

- `perception`: giá trị đo đã chuẩn hóa.
- `quality`: cờ chất lượng trực tiếp từ packet/provider, không tự suy diễn confidence.
- `derived_signals`: thống kê mô tả như delta, trend, spread ratio.

### `pipelines/`

`preprocessing.py` điều phối Layer 2: đọc artifact Layer 1, chọn processor phù hợp, truyền history vào processor, sau đó ghi `history.jsonl`, `latest.json`, `state.json` và `manifest.json`.

### `fusion/`

`layer25.py` ghép nhiều snapshot Layer 2 thành hàng dữ liệu Layer 2.5 theo `ts_hour_bucket`. Fusion chỉ hợp nhất và flatten dữ liệu; không đánh giá sức khỏe cảm biến.

### `canonical/`

Chứa bộ dựng bảng dữ liệu chuẩn cho mô hình. Hiện tại `tabnet_super_table.py` chuyển Layer 2.5 thành matrix CSV và schema metadata cho TabNet.

### `contracts/`

Chứa marker/schema version cho các hợp đồng dữ liệu. Khi cấu trúc payload thay đổi, cần cập nhật phần này để phục vụ tái lập.

### `utils/`

Chứa helper kỹ thuật dùng chung như xử lý thời gian, ép kiểu số, thống kê cửa sổ và đọc/ghi JSON. Không đặt rule nông học hoặc logic sensor đặc thù trong package này.

## API chính

```python
from Core import PreprocessingPipeline, Layer25FusionPipeline
from Core.processors import NPKProcessor, SHT30Processor, MeteoProcessor
from Core.canonical import TabNetSuperTableBuilder
```

## Ranh giới khoa học

Layer 2 không nên nói:

- cây chắc chắn đang stress,
- đất chắc chắn thiếu dinh dưỡng,
- sensor có confidence bao nhiêu phần trăm nếu chưa có mô hình hiệu chuẩn,
- record đã sẵn sàng cho agent hay chưa.

Layer 2 nên nói:

- cảm biến đã đo gì,
- packet có vượt qua hard gate kỹ thuật không,
- xu hướng/delta trong các cửa sổ thời gian là gì,
- dữ liệu được ghi từ nguồn nào và ở bucket thời gian nào.
