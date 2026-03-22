#include <Arduino.h>
#include <Wire.h>
#include "Adafruit_SHT31.h"

// CẤU HÌNH CHÂN I2C CHO ESP32-S3
// (Ông cắm chân nào thì sửa số chân ở đây)
#define SDA_PIN 8 
#define SCL_PIN 9

Adafruit_SHT31 sht31 = Adafruit_SHT31();

void setup() {
  Serial.begin(115200);
  
  // Khởi tạo I2C thủ công để chắc chắn đúng chân
  Wire.begin(SDA_PIN, SCL_PIN);

  Serial.println("SHT31 Test Bat Dau...");
  
  // Thử kết nối lần đầu
  if (!sht31.begin(0x44)) {   // 0x44 là địa chỉ mặc định
    Serial.println("LOI: Khong tim thay SHT31! Kiem tra day noi.");
  } else {
    Serial.println("OK: Da ket noi SHT31.");
  }
}

void loop() {
  // 1. Đọc dữ liệu
  float t = sht31.readTemperature();
  float h = sht31.readHumidity();

  // 2. KIỂM TRA LỖI (QUAN TRỌNG NHẤT)
  if (isnan(t) || isnan(h)) { 
    Serial.println("--- MAT KET NOI! DANG THU KET NOI LAI... ---");
    
    // --> CƠ CHẾ TỰ HỒI SINH <--
    // Thử kết nối lại ngay lập tức
    if (sht31.begin(0x44)) {
      Serial.println(">>> DA KET NOI LAI THANH CONG! <<<");
    } else {
      Serial.println(">>> VAN LOI. KIEM TRA DAY NGAY! <<<");
    }
  } 
  else {
    // 3. Nếu ngon lành thì in ra
    Serial.print("Nhiet do: "); Serial.print(t); Serial.println(" *C");
    Serial.print("Do am:    "); Serial.print(h); Serial.println(" %");
    Serial.println("-----------------------");
  }

  delay(2000);
}