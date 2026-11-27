#ifndef SOIL_MOISTURE_SERVICE_H
#define SOIL_MOISTURE_SERVICE_H

#include <Arduino.h>
#include <ArduinoJson.h>

#include "Soilv2.h"

struct SoilMoistureReading {
    bool readOk = false;
    bool sampleValid = false;
    bool calibrationValid = false;
    bool calibrationIsDefault = false;
    int raw = -1;
    int rawMin = -1;
    int rawMax = -1;
    uint32_t voltageMv = 0;
    int percent = -1;
    uint8_t sampleCount = 0;
    uint16_t sampleGapMs = 0;
    String state = "NOT_READ";
    String error = "not_attempted";
    String calibrationProfile = "unset";
    String calibrationSource = "unknown";
};

class SoilMoistureService {
public:
    SoilMoistureService(uint8_t adcPin,
                        int dryValue,
                        int wetValue,
                        uint8_t sampleCount,
                        uint16_t sampleGapMs);

    void begin();
    bool read(SoilMoistureReading &reading);

    String buildJsonPayload(const char *sensorType,
                            const char *sensorId,
                            const char *edgeSystem,
                            const char *edgeSystemId,
                            const char *edgeStream) const;

private:
    SoilV2 _sensor;
    uint8_t _adcPin;
    int _dryValue;
    int _wetValue;
    uint8_t _sampleCount;
    uint16_t _sampleGapMs;
    bool _begun = false;
    SoilMoistureReading _lastReading;
};

#endif
