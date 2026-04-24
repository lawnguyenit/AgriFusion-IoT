# AgriFusion IoT

## Giới thiệu về đề tài

Đây là repository phục vụ luận văn tốt nghiệp của sinh viên ngành Công nghệ thông tin tại Trường Đại học Sư phạm Kỹ thuật Vĩnh Long (VLUTE).

Hướng nghiên cứu ban đầu là phát triển một hệ thống AI đa tác nhân hỗ trợ chẩn đoán bệnh và nhu cầu dinh dưỡng của cây trồng. Dữ liệu được thu thập từ thiết bị IoT, dữ liệu thời tiết và định hướng mở rộng thêm ảnh từ flycam. Đối tượng nghiên cứu chính hiện tại là cây sầu riêng.

Phần nghiên cứu chính trong repository này tập trung vào:

- Hệ thống nhúng IoT: logic hoạt động của node cảm biến, truyền dữ liệu, kiểm tra trạng thái thiết bị và đồng bộ dữ liệu lên Firebase RTDB.
- Backend xử lý dữ liệu: kéo dữ liệu thô, chuẩn hóa thành các layer xử lý, tạo bộ dữ liệu phục vụ phân tích và huấn luyện mô hình.
- Luật và mô hình AI: xây dựng rule-based signal, fuzzy logic, feature table và benchmark thử nghiệm cho các mô hình như TabNet.

## Mục tiêu hệ thống

Hệ thống được thiết kế theo hướng nhiều lớp dữ liệu để tách rõ dữ liệu thô, dữ liệu đã xử lý và dữ liệu dùng cho suy luận:

1. Thu thập dữ liệu từ node IoT và nguồn thời tiết.
2. Lưu dữ liệu thô layer 1.
3. Tiền xử lý từng nhóm cảm biến thành snapshot ở Layer 2.
4. Hợp nhất các nguồn ở Layer 2.5 để tạo bảng dữ liệu dùng cho mô hình.
5. Xây dựng rule và benchmark để đánh giá tín hiệu sinh học, môi trường và dinh dưỡng.

## Luồng dữ liệu chính

```text
IoT Node / Open-Meteo / Firebase RTDB
        |
        v
Backend/Services/exporters
        |
        v
Backend/Output_data/Layer1
        |
        v
Backend/Core/Preprocessors
        |
        v
Backend/Output_data/Layer2
        |
        v
Backend/Core/Preprocessors/Layer25
        |
        v
Benchmark / TabNet / rule-based signals
```

## Cấu trúc thư mục

```text
AgriFusion-IoT/
├── Backend/
│   ├── main.py
│   ├── Services/
│   │   ├── app_config.py
│   │   ├── firebase_service.py
│   │   └── exporters/
│   ├── Core/
│   │   └── Preprocessors/
│   │       ├── NPK/
│   │       ├── SHT30/
│   │       ├── environmental_intelligence/
│   │       ├── Layer25/
│   │       ├── Cannon_data/
│   │       └── Untils/
│   ├── Benchmark/
│   │   ├── Tabnet_vanilla/
│   │   └── rules/
│   │       └── layer1/
│   ├── Config/
│   ├── Output_data/
│   │   ├── Layer1/
│   │   └── Layer2/
│   └── Test/
├── IoT_Node/
│   ├── src/
│   ├── lib/
│   └── platformio.ini
├── Frontend/
│   ├── public/
│   ├── firebase.json
│   └── database.rules.json
├── Docs/
│   ├── Architecture/
│   ├── Figures/
│   ├── Dataset_Durian/
│   └── web/
├── Secrets/
├── pyproject.toml
└── README.md
```

## Vai trò từng phần

### `IoT_Node`

Chứa firmware cho node ESP32-S3. Phần này xử lý đọc cảm biến NPK, SHT30, trạng thái thiết bị, kết nối mạng qua SIM/WiFi, đóng gói telemetry và gửi dữ liệu lên Firebase RTDB.

### `Backend`

Là phần xử lý dữ liệu chính của hệ thống. Backend hiện có pipeline kéo dữ liệu từ Firebase hoặc file JSON export, ghi dữ liệu thô vào `Output_data/Layer1`, sau đó tiền xử lý thành Layer 2 và hợp nhất thành Layer 2.5.

Các nhóm xử lý quan trọng:

- `Services/exporters`: đồng bộ dữ liệu nguồn về local artifact.
- `Core/Preprocessors/NPK`: xử lý dữ liệu đất, NPK, pH, EC và độ ẩm đất.
- `Core/Preprocessors/SHT30`: xử lý nhiệt độ và độ ẩm không khí từ cảm biến SHT30.
- `Core/Preprocessors/environmental_intelligence`: xử lý dữ liệu thời tiết từ Open-Meteo.
- `Core/Preprocessors/Layer25`: hợp nhất các nguồn dữ liệu thành bảng chung.
- `Benchmark`: thử nghiệm rule, feature engineering và mô hình benchmark.

### `Backend/Benchmark/rules/layer1`

Chứa rule object cho ba nhóm nguồn đầu vào:

- `npk.py`: tín hiệu dinh dưỡng, độ ẩm đất, pH và EC.
- `sht30.py`: tín hiệu nhiệt độ, độ ẩm không khí và áp lực ngưng tụ.
- `meteo.py`: tín hiệu thời tiết, mưa, độ ẩm, nhiệt độ, mây và bốc thoát hơi.

Các rule này dùng các tham số như `normal_low`, `normal_high`, `threshold_low`, `threshold_high`, `direction`, `alpha`, `confidence` để đánh giá fuzzy state, xu hướng và tích lũy áp lực theo các lát thời gian `3h`, `8h`, `12h`, `24h`.

### `Frontend`

Chứa phần cấu hình Firebase Hosting và public assets. Hiện phần frontend chưa phải trọng tâm chính của pipeline dữ liệu, nhưng có thể dùng để trình bày dashboard hoặc tài liệu web.

### `Docs`

Chứa tài liệu kiến trúc, hình ảnh thiết bị, sơ đồ hệ thống và các ghi chú nghiên cứu. Đây là nơi nên đặt hình minh họa, sơ đồ layer và tài liệu giải thích cho luận văn.

### `Secrets`

Chứa dữ liệu nhạy cảm hoặc file cấu hình cục bộ. Thư mục này không nên được dùng làm nơi tham chiếu cứng trong code và không nên commit thông tin bí mật lên remote repository.

## Chạy backend nhanh

Từ thư mục `Backend`:

```powershell
python -m pip install -r requirements.txt
python main.py --source firebase --node-id Node1 --full-history --skip-layer25
```

Chạy Layer 2 từ dữ liệu local đã có:

```powershell
python main.py --layer2-only --skip-layer25
```

Chạy test:

```powershell
python -m unittest discover -s Test -p "test_*.py"
```

## Nhận xét về cấu trúc hiện tại

Cấu trúc hiện tại đi theo hướng đúng vì đã tách được ba phần lớn: firmware IoT, backend xử lý dữ liệu và tài liệu nghiên cứu. Phần backend cũng đã chia layer khá rõ, phù hợp với hướng làm luận văn vì có thể giải thích luồng dữ liệu từ raw telemetry đến feature table.

Điểm mạnh:

- Có pipeline dữ liệu theo layer, dễ kiểm soát và tái lập.
- Tách riêng từng nguồn cảm biến như NPK, SHT30 và Open-Meteo.
- Có thư mục benchmark riêng để thử nghiệm mô hình mà không trộn vào pipeline production.
- Có tài liệu và hình ảnh trong `Docs`, phù hợp cho việc viết báo cáo.

Điểm nên cải thiện tiếp:

- Nên thống nhất cách đặt tên thư mục và file. Ví dụ `Untils` có thể đổi thành `Utils`, `Cannon_data` có thể đổi thành `Canonical_data` nếu chưa bị phụ thuộc nhiều.
- Không nên để dữ liệu sinh ra quá lớn hoặc dữ liệu nhạy cảm trong repo chính. `Output_data`, `.cache`, `Secrets` nên được kiểm soát kỹ bằng `.gitignore`.
- Nên thêm README nhỏ trong từng module quan trọng như `Benchmark/rules`, `Layer25`, `IoT_Node/lib`.
- Nên chuẩn hóa encoding UTF-8 cho toàn bộ tài liệu tiếng Việt để tránh lỗi hiển thị ký tự.

## Trạng thái hiện tại

Repository đang ở giai đoạn xây dựng nền tảng dữ liệu và benchmark. Trọng tâm hợp lý tiếp theo là ổn định schema dữ liệu, hoàn thiện rule signal cho từng nguồn, sau đó dùng Layer 2.5 làm đầu vào nhất quán cho mô hình học máy và các tác nhân suy luận.
