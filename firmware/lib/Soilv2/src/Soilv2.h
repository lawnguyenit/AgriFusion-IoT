#ifndef Soilv2
#define Soilv2

#include <Arduino.h>

// Struct chứa dữ liệu trả về
struct SoilData {
    int percent = -1;          // Độ ẩm dạng % (0-100), -1 nếu chưa hiệu chuẩn
    int raw = 0;               // Giá trị ADC trung bình
    int rawMin = 0;            // ADC nhỏ nhất trong cửa sổ mẫu
    int rawMax = 0;            // ADC lớn nhất trong cửa sổ mẫu
    uint32_t voltageMv = 0;    // Điện áp ADC đã hiệu chuẩn bởi Arduino core
    bool calibrationValid = false;
    String state;              // Trạng thái đọc được (Kho/Am/Uot/Chua hieu chuan)
};

class SoilV2 {
private:
    uint8_t _pin;
    int _airValue;   // Giá trị khi để khô ngoài không khí
    int _waterValue; // Giá trị khi nhúng nước
    
    uint8_t _sampleCount;
    uint16_t _sampleGapMs;

public:
    // Constructor: Cần truyền Chân PIN, Giá trị KHÔ, Giá trị ƯỚT
    SoilV2(uint8_t pin,
           int airVal,
           int waterVal,
           uint8_t sampleCount = 20U,
           uint16_t sampleGapMs = 2U);

    // Khởi động
    void begin();

    // Đọc dữ liệu đã xử lý
    SoilData read();
};

#endif
