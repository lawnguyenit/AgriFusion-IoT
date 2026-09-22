#ifndef SHT30_SERVICE_H
#define SHT30_SERVICE_H

#include <Arduino.h>
#include <ArduinoJson.h>

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
    uint8_t _lastI2cError = 0xFF;
    uint8_t _lastInitAttempts = 0;
    bool _lastInitProbeReadOk = false;
    float _lastInitProbeTemperature = NAN;
    float _lastInitProbeHumidity = NAN;
    String _lastInitError = "not_attempted";

    bool _lastMeasurementTransportOk = false;
    bool _lastMeasurementAttempted = false;
    bool _lastFrameOk = false;
    bool _lastTemperatureCrcOk = false;
    bool _lastHumidityCrcOk = false;
    uint8_t _lastReceivedBytes = 0;
    uint16_t _lastRawTemperature = 0;
    uint16_t _lastRawHumidity = 0;
    uint8_t _lastMeasurementI2cError = 0xFF;
    String _lastMeasurementError = "not_attempted";

    void ensureWireReady(bool forceRefresh = false);
    void clearMeasurementDiagnostics();
    bool sendCommand(uint16_t command, uint8_t &i2cError);
    bool readRawMeasurement(float *temperatureOut, float *humidityOut);
    void writeMeasurementDiagnostics(JsonDocument &doc);
};

#endif
