#ifndef Soilv2
#define Soilv2

#include <Arduino.h>

// Struct chứa dữ liệu trả về
struct SoilData {
    int percent;  // Độ ẩm dạng % (0-100)
    int raw;      // Giá trị thô (để debug/hiệu chuẩn)
    String state; // Trạng thái đọc được (Kho/Am/Uot)
};

class SoilV2 {
private:
    uint8_t _pin;
    int _airValue;   // Giá trị khi để khô ngoài không khí
    int _waterValue; // Giá trị khi nhúng nước
    
    // Hàm đọc trung bình để lọc nhiễu (Private)
    int readRawSmoothed();

public:
    // Constructor: Cần truyền Chân PIN, Giá trị KHÔ, Giá trị ƯỚT
    SoilV2(uint8_t pin, int airVal, int waterVal);

    // Khởi động
    void begin();

    // Đọc dữ liệu đã xử lý
    SoilData read();
};

#endif