# Hợp đồng `result/*` (Backend -> Dashboard)

Phiên bản hợp đồng: `schema_version = 1`. Bản máy đọc được: `Frontend/public/contract.js`.
`Frontend/test/contract.test.js` kiểm dữ liệu mẫu của UI, danh sách metric của UI và `database.rules.json` theo hợp đồng này.

Trạng thái: **backend publisher chưa tồn tại** (sẽ viết sau theo tài liệu này). Chỗ nào ghi "đề xuất" là quy tắc backend cần
tuân thủ nhưng chưa có mã nào thực thi; chưa kiểm chứng với dữ liệu thật.

## 1. Phạm vi

Trong hợp đồng: không khí (SHT30), đất (nhóm cảm biến NPK: nhiệt độ, độ ẩm, pH, EC), NPK dạng proxy.
Ngoài hợp đồng (không có nguồn dữ liệu, đã bỏ khỏi UI): thời tiết, dự báo, chẩn đoán, khuyến nghị, bất thường, `pipeline`.
Backend không được ghi các nhánh này; dashboard không đọc chúng.

## 2. Cây RTDB

```text
result/
  meta                         object
  latest/{air,soil,npk}        object  (bản sao bản ghi mới nhất của history cùng nhóm)
  history/
    air/{ts}                   object  key = String(ts)
    soil/{ts}
    npk/{ts}
```

- `ts`: số nguyên, epoch giây (UTC), lấy từ `record.ts_sample`. Key của history luôn bằng `String(ts)` (khử trùng lặp, thứ tự theo key).
- Không có kiểu `null` trong RTDB: **thiếu giá trị = bỏ hẳn key**. Không ghi `null`, `NaN`, chuỗi rỗng, cũng không ghi 0 làm giá trị thay thế.

## 3. `result/meta`

| Trường | Kiểu | Bắt buộc | Nguồn / ý nghĩa |
|---|---|---|---|
| `schema_version` | int | có | hằng `1` |
| `published_ts` | int (epoch giây) | có | đồng hồ backend lúc publish; UI dùng để báo "dữ liệu cũ" (quá 40 phút) |
| `latest_sample_ts` | int | không | max `ts` trên cả ba nhóm; bỏ khi chưa có dữ liệu |
| `node_id` | string | có | node nguồn (ví dụ `Node2`) |
| `source` | string | có | định danh publisher (ví dụ `agrifusion-backend`) |

## 4. Bản ghi history / latest

Mỗi bản ghi có `ts` (int, bắt buộc) và các trường giá trị bên dưới (kiểu number hữu hạn, đều tùy chọn).
Bản ghi không có trường giá trị nào thì **không publish**.
Khoảng hợp lệ là đề xuất sanity: giá trị ngoài khoảng thì backend bỏ key đó (UI cũng không sửa giá trị).

### `history/air/{ts}` (canonical nhóm `sht.*`)

| Trường | Đơn vị | Cột canonical | Khoảng |
|---|---|---|---|
| `temperature_c` | °C | `sht.temp_c` (`packet.sht30_data.sht_temp_c`) | -40..85 |
| `humidity_pct` | % | `sht.humidity_pct` (`packet.sht30_data.sht_hum_pct`) | 0..100 |

### `history/soil/{ts}` (canonical nhóm `npk.*`, phần đất)

| Trường | Đơn vị | Cột canonical | Khoảng |
|---|---|---|---|
| `temperature_c` | °C | `npk.soil_temp_c` | -40..85 |
| `moisture_pct` | % | `npk.soil_moisture_pct` | 0..100 |
| `ph` | pH | `npk.ph` | 0..14 |
| `ec` | **chưa kiểm chứng** | `npk.ec` | >= 0 |

`ec`: catalog canonical (`canonical_fields.py`) chỉ ghi "Soil EC measured in the NPK packet", không khẳng định đơn vị.
Tên trường cũ `ec_us_cm` bị bỏ vì ngầm khẳng định µS/cm. UI hiển thị "EC (chưa rõ đơn vị)".
Tên trường cũ `humidity_pct` của nhóm soil đổi thành `moisture_pct` cho khớp `npk.soil_moisture_pct`.

### `history/npk/{ts}`

| Trường | Đơn vị | Cột canonical | Khoảng |
|---|---|---|---|
| `n_proxy` | proxy (uncalibrated) | `npk.n_proxy` (`packet.npk_data.N`) | >= 0 |
| `p_proxy` | proxy (uncalibrated) | `npk.p_proxy` (`packet.npk_data.P`) | >= 0 |
| `k_proxy` | proxy (uncalibrated) | `npk.k_proxy` (`packet.npk_data.K`) | >= 0 |

Đây là chỉ số proxy chưa hiệu chuẩn, **không phải ppm** và không quy đổi sang mg/kg. Tên trường cũ `n_ppm/p_ppm/k_ppm` bị bỏ.

### `latest/{air,soil,npk}`

Cùng schema với bản ghi history của nhóm đó, và phải bằng bản ghi có `ts` lớn nhất hiện có trong `history/{nhóm}`.
Publisher cập nhật `latest` và `history` trong cùng một multi-path update.

## 5. Quy tắc null / loại bản ghi (đề xuất)

- Lấy từ canonical row đã qua Layer1. Bỏ qua hàng có `record.is_demo = true` hoặc `record.excluded_reason` khác rỗng.
- Với NPK: nếu cờ `npk.n_proxy_valid` / `p_proxy_valid` / `k_proxy_valid` là false thì bỏ key tương ứng. Tương tự `npk.soil_temp_valid`, `npk.soil_moisture_valid`, `npk.ec_valid` cho các trường đất (tên cờ lấy từ catalog; ánh xạ chính xác do publisher xác nhận).
- Ba nhóm có thể có `ts` giống nhau (cùng một lần lấy mẫu) nhưng mỗi nhóm được quyết định riêng: nhóm không có trường hợp lệ thì không có bản ghi tại `ts` đó.

## 6. Giữ lại và cắt tỉa (đề xuất)

- Retention: 7 ngày tính theo `ts` so với `ts` mới nhất của nhóm (`HISTORY_RETENTION_SECONDS = 604800`).
- Trần số điểm: 800 mỗi nhóm (`HISTORY_MAX_POINTS`). Chu kỳ lấy mẫu vận hành của firmware là 15 phút, tức 672 điểm/7 ngày; 800 chừa dư cho mẫu bù/replay. Nếu bật chế độ debug 2 phút thì trần 800 cắt còn ~27 giờ.
- Quy tắc cắt: sau mỗi lần ghi, publisher xóa (set `null` trong cùng multi-path update) mọi key có `ts < ts_mới_nhất - 7 ngày`, rồi nếu còn hơn 800 key thì xóa các key `ts` nhỏ nhất.
- Dashboard đọc bằng `limitToLast(800)` theo key. Do key là chuỗi số cùng độ dài (epoch giây 10 chữ số) nên thứ tự key = thứ tự thời gian. Phía đọc cũng chịu được khi publisher chưa kịp cắt.
- Dữ liệu cũ hơn 7 ngày vẫn nằm ở `Backend/Output_data/*`, không ở RTDB.

## 7. Ai ghi, ai đọc

| Đường dẫn | Ghi | Đọc |
|---|---|---|
| `result/**` | publisher backend, qua service account (Admin SDK; bỏ qua rules) | công khai (dashboard, không cần đăng nhập) |
| `Node2/*`, `debug/*`, `control/*`, `ops/*` | thiết bị / vận hành, yêu cầu auth không ẩn danh | yêu cầu auth không ẩn danh, **không công khai** |

Client công khai không có quyền ghi bất kỳ đâu. Rules nằm ở `Frontend/database.rules.json`; rules đang chạy trên Firebase chưa được repo này xác minh.
