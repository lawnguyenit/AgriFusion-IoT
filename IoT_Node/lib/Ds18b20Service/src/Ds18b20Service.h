#ifndef DS18B20_SERVICE_H
#define DS18B20_SERVICE_H

#include <Arduino.h>
#include <OneWire.h>

#include "Config.h"

struct Ds18b20BusStatus {
    bool idleHigh = false;
    bool presenceDetected = false;
    bool romFound = false;
    uint8_t deviceCount = 0U;
};

struct Ds18b20Reading {
    bool presenceDetected = false;
    bool scratchpadCrcOk = false;
    bool rangeOk = false;
    bool readOk = false;
    int16_t rawTemperature = 0;
    float temperatureC = NAN;
    uint8_t resolutionBits = 12U;
    uint8_t scratchpad[9] = {};
};

class Ds18b20Service {
public:
    Ds18b20Service(uint8_t dataPin, uint32_t retryInitMs);

    bool tryInit(bool force = false);
    bool ready() const;

    const Ds18b20BusStatus &busStatus() const;
    uint8_t deviceCount() const;
    const uint8_t *deviceAddress(uint8_t index) const;

    // Read the primary sensor used by the application. A discovered ROM is
    // preferred; the single-drop skip-ROM path is kept for the verified
    // one-device fallback setup.
    bool readPrimary(Ds18b20Reading &reading);
    bool readDevice(uint8_t index, Ds18b20Reading &reading);
    bool readSingleDrop(Ds18b20Reading &reading);

    String buildJsonPayload(const char *sensorType,
                            const char *sensorId,
                            const char *edgeSystem,
                            const char *edgeSystemId,
                            const char *edgeStream,
                            uint8_t maxReadAttempts = 1U,
                            uint32_t retryDelayMs = 100UL,
                            uint32_t maxWaitMs = 2000UL);

private:
    OneWire _oneWire;
    uint8_t _dataPin;
    uint32_t _retryInitMs;
    uint32_t _lastInitAttemptMs = 0U;
    bool _ready = false;
    bool _singleDropFallbackReady = false;
    String _lastInitError = "not_attempted";
    Ds18b20BusStatus _busStatus;
    uint8_t _addresses[DS18B20_MAX_DEVICES][8] = {};

    void prepareBus();
    bool readTemperature(const uint8_t *address,
                         bool selectRom,
                         Ds18b20Reading &reading);
    static const char *resolutionName(uint8_t bits);
};

#endif
