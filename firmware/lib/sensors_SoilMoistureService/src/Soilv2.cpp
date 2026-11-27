#include "Soilv2.h"

SoilV2::SoilV2(uint8_t pin,
               int airVal,
               int waterVal,
               uint8_t sampleCount,
               uint16_t sampleGapMs) {
    _pin = pin;
    _airValue = airVal;
    _waterValue = waterVal;
    _sampleCount = sampleCount > 0U ? sampleCount : 20U;
    _sampleGapMs = sampleGapMs;
}

void SoilV2::begin() {
    pinMode(_pin, INPUT);
    // Cấu hình ADC của ESP32 để đọc chính xác dải 0-3.3V
    analogReadResolution(12);       // Đọc 12 bit (0-4095)
    analogSetAttenuation(ADC_11db); // Cho phép đọc full dải áp 3.3V
}

SoilData SoilV2::read() {
    SoilData result;
    long rawSum = 0;
    long voltageSum = 0;
    result.rawMin = 4095;
    result.rawMax = 0;

    for (uint8_t index = 0U; index < _sampleCount; ++index) {
        const int raw = analogRead(_pin);
        const uint32_t voltageMv = analogReadMilliVolts(_pin);
        rawSum += raw;
        voltageSum += static_cast<long>(voltageMv);
        if (raw < result.rawMin) {
            result.rawMin = raw;
        }
        if (raw > result.rawMax) {
            result.rawMax = raw;
        }
        delay(_sampleGapMs);
    }

    result.raw = static_cast<int>(rawSum / _sampleCount);
    result.voltageMv = static_cast<uint32_t>(voltageSum / _sampleCount);
    result.calibrationValid = _airValue != _waterValue;

    if (!result.calibrationValid) {
        result.percent = -1;
        result.state = "CHUA HIEU CHUAN";
        return result;
    }

    const long scaled = (static_cast<long>(result.raw) - _airValue) * 100L;
    int per = static_cast<int>(scaled / (_waterValue - _airValue));
    if (per > 100) {
        per = 100;
    }
    if (per < 0) {
        per = 0;
    }

    result.percent = per;
    if (per < 30) {
        result.state = "KHO (Can tuoi)";
    } else if (per < 70) {
        result.state = "AM (Tot)";
    } else {
        result.state = "UOT (Ngap)";
    }

    return result;
}
