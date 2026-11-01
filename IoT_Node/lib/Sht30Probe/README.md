# Sht30Probe

Che do probe rieng cho SHT30, khong di qua `Sht30Service`, AppRuntime, SIM,
hay Firebase.

Wiring cho bai test 3.3 V:

- `VCC -> 3V3`
- `GND -> GND` chung voi ESP32-S3
- `SDA -> GPIO6`
- `SCL -> GPIO7`
- Serial Monitor: `115200` baud

Neu breakout co pull-up I2C tich hop, dam bao SDA/SCL duoc keo len 3.3 V.

Probe quet I2C mot lan luc boot. Sau do, moi lan do ping dia chi chinh `0x44`, thu dia chi thay the `0x45` neu dia chi chinh khong ACK, doc mot frame raw 6 byte va kiem tra CRC. Sau khi in dong ket qua, probe doi it nhat 1000 ms moi bat dau lan do tiep theo. Moi lan do chi in mot dong `[SHT30][MEASURE]`, khong lap lai init burst hay JSON payload.

SDA/SCL lay tu `Config.h` (hien tai GPIO6/GPIO7); `0x45` chi la dia chi thay the de chan doan. Doc ket qua nhu sau:

- `ACK=0`: ca hai dia chi khong phan hoi; xem dong `primary_error` va `alternate_error`.
- `ACK=1`, `frame=1`, `crc=1`, `state=ok`: doc du 6 byte, ca hai CRC dung, va co gia tri decode.
- `ACK=1`, `crc=0` hoac `frame=0`: co phan hoi nhung frame/CRC loi.
- `state=zero_raw_measurement`: frame va CRC co the hop le nhung raw temp/humidity deu bang 0; khong xem day la mau moi truong hop le.
- `raw_temp`/`raw_hum`: gia tri tho 16-bit; `temp`/`hum`: gia tri decode tu frame.

De chay bai test nay, dat `APP_SHT30_TEST_MODE=1` va cac diagnostic selector
khac ve `0` trong `Config.h`. Dung environment mac dinh `esp32-s3-n16r8`
trong PlatformIO UI de Build/Upload; `DEBUG_MODE=1` bat serial logs. Khi test
xong, tat selector SHT30 va de tat ca diagnostic selector bang `0` de quay lai
production `AppRuntime`.
