#ifndef SHT30_H
#define SHT30_H

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>

// 1. Cấu hình chân 
#define SHT_SDA     1
#define SHT_SCL     2
#define SHT_ADDR    0x44 // Địa chỉ mặc định
// 2. Cấu trúc dữ liệu lưu trữ kết quả đọc
struct SHT_Data {
    float temp; // Nhiệt độ
    float hum;  // Độ ẩm
    bool error; // Cờ lỗi
};
// 3. Tạo đối tượng cảm biến
extern Adafruit_SHT31 sht;

bool setupSHT();                  // Khởi động
SHT_Data readSHT();               // Đọc dữ liệu
void checkSHTConnection();        // Kiểm tra và tự kết nối lại
void controlHeater(bool on);      // Bật/Tắt sấy

#endif