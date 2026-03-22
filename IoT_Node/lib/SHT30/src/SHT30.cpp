#include "SHT30.h"

Adafruit_SHT31 sht; 

bool setupSHT() {
    Serial.println("[SHT30] --- BAT DAU KHOI DONG ---");
    
    // SỬA ĐOẠN NÀY:
    // Thêm tham số thứ 3 là tần số: 10000 (10kHz) thay vì mặc định
    // Cú pháp: Wire.begin(SDA, SCL, FREQUENCY);
    Wire.begin(SHT_SDA, SHT_SCL, 10000); 
    
    // Tăng thời gian chờ một chút cho dây dài
    delay(100);

    if (!sht.begin(SHT_ADDR)) {
        Serial.println("[SHT30] LOI: Khong tim thay SHT30!");
        Serial.println(" -> 1. Kiem tra lai MOI HAN chan header");
        Serial.println(" -> 2. Day 2m qua dai -> Da ha toc do xuong 10kHz");
        return false;
    }

    Serial.println("[SHT30] KHOI DONG THANH CONG (Low Speed Mode)!");
    return true;
}
// ... Các hàm bên dưới giữ nguyên ...
SHT_Data readSHT() {
    SHT_Data data;
    data.temp = sht.readTemperature();
    data.hum = sht.readHumidity();

    if (isnan(data.temp) || isnan(data.hum)) {
        data.error = true;
    } else {
        data.error = false;
    }
    return data;
}

void checkSHTConnection() {
    Wire.beginTransmission(SHT_ADDR);
    if (Wire.endTransmission() != 0) {
        Serial.println("[SHT30] Mat ket noi! Reconnecting...");
        setupSHT();
    }
}

void controlHeater(bool control) {
    sht.heater(control);
}