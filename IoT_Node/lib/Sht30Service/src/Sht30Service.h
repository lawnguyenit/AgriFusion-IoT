#ifndef SHT30_SERVICE_H
#define SHT30_SERVICE_H

#include <Arduino.h>

class Sht30Service {
public:
    Sht30Service(uint8_t sdaPin, uint8_t sclPin, uint8_t address, uint32_t retryInitMs);

    bool tryInit(bool force = false);
    bool ready() const;
    bool isAddressReachable(bool refreshBus = false);

    String buildJsonPayload(const char *sensorType,
                            const char *sensorId,
                            const char *edgeSystem,
                            const char *edgeSystemId,
                            const char *edgeStream,
                            uint8_t maxReadAttempts = 4,
                            uint32_t retryDelayMs = 120,
                            uint32_t maxWaitMs = 1200);

private:
    uint8_t _sdaPin;
    uint8_t _sclPin;
    uint8_t _address;
    uint32_t _retryInitMs;
    bool _ready = false;
    bool _wireReady = false;
    uint32_t _lastInitAttemptMs = 0;
    uint32_t _consecutiveInvalidCount = 0;

    void ensureWireReady(bool forceRefresh = false);
};

#endif
