#include "Soilv2.h"

SoilV2::SoilV2(uint8_t pin, int airVal, int waterVal) {
    _pin = pin;
    _airValue = airVal;
    _waterValue = waterVal;
}

void SoilV2::begin() {
    pinMode(_pin, INPUT);
    // Cấu hình ADC của ESP32 để đọc chính xác dải 0-3.3V
    analogReadResolution(12);       // Đọc 12 bit (0-4095)
    analogSetAttenuation(ADC_11db); // Cho phép đọc full dải áp 3.3V
}

// Hàm này quản lý rủi ro "Nhiễu tín hiệu"
int SoilV2::readRawSmoothed() {
    long sum = 0;
    const int SAMPLES = 20; // Đọc 20 lần liên tiếp
    
    for(int i=0; i<SAMPLES; i++) {
        sum += analogRead(_pin);
        delay(2); // Nghỉ cực ngắn giữa các lần đọc
    }
    
    return (int)(sum / SAMPLES); // Trả về trung bình cộng
}

SoilData SoilV2::read() {
    SoilData result;
    
    // 1. Lấy giá trị thô đã lọc nhiễu
    result.raw = readRawSmoothed();

    int per = map(result.raw, _airValue, _waterValue, 0, 100);
    // 2. Giới hạn trong khoảng 0-100%
    if (per > 100) per = 100;
    if (per < 0) per = 0;
    
    result.percent = per;

    // 4. Đánh giá trạng thái (Cho main dễ dùng)
    if (per < 30) result.state = "KHO (Can tuoi)";
    else if (per < 70) result.state = "AM (Tot)";
    else result.state = "UOT (Ngap)";

    return result;
}