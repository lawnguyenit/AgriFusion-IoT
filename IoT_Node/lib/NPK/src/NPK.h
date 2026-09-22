#ifndef NPK_H
#define NPK_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ModbusMaster.h>

#include "SoilMoistureService.h"

enum NPK_ReadMap : uint8_t {
    NPK_READ_MAP_NONE = 0,
    NPK_READ_MAP_LEGACY_FULL = 1,
    NPK_READ_MAP_SPARSE = 2
};

struct NPK_Data {
    float hum;
    float temp;
    float ph;
    int ec;
    int n;
    int p;
    int k;

    // Raw holding-register values are retained so a decoded zero can be
    // distinguished from a missing response or an incorrect register map.
    uint16_t rawHum;
    uint16_t rawTemp;
    uint16_t rawEc;
    uint16_t rawPh;
    uint16_t rawN;
    uint16_t rawP;
    uint16_t rawK;

    // Per-field protocol evidence. A field is true only when its register
    // group returned a valid Modbus response in this read cycle.
    bool humReadOk;
    bool tempReadOk;
    bool phReadOk;
    bool ecReadOk;
    bool nReadOk;
    bool pReadOk;
    bool kReadOk;

    // Semantic evidence is separate from protocol evidence. For example, a
    // valid frame containing raw pH=0 is a successful register read but not a
    // plausible soil-pH measurement.
    bool humValueValid;
    bool tempValueValid;
    bool phValueValid;
    bool ecValueValid;
    bool nValueValid;
    bool pValueValid;
    bool kValueValid;

    // Derived/defaulted fields are deliberately separate from protocol
    // evidence. ecReadOk remains false when no EC register frame was read,
    // while ecDerivedFromNpk allows the inferred EC to be written to npk.ec.
    bool ecDerivedFromNpk;
    float ecEstimateFloat;
    bool ecInferenceWithinCalibrationDomain;
    bool tempDefaultedToZero;
    bool tempFromExternalSensor;
    bool humDefaultedToZero;
    bool humFromExternalSensor;
    bool externalHumReadOk;
    bool externalHumSampleValid;
    bool externalHumCalibrationValid;
    bool externalHumCalibrationIsDefault;
    int externalHumRaw;
    int externalHumRawMin;
    int externalHumRawMax;
    int externalHumPercent;
    uint32_t externalHumVoltageMv;
    String externalHumState;
    String externalHumError;
    String externalHumCalibrationProfile;
    String externalHumCalibrationSource;

    uint8_t readMap;
    bool legacyBlockReadOk;
    uint8_t legacyBlockStatus;
    uint8_t legacyBlockAttempts;
    uint8_t phStatus;
    uint8_t phAttempts;
    uint8_t npkStatus;
    uint8_t npkAttempts;

    bool error;
    bool readOk;
    uint8_t errorCodeRaw;
    uint8_t retryCount;
    uint32_t timeoutMs;
    uint32_t readDurationMs;
    bool crcOk;
    bool frameOk;
};

class MyNPK {
private:
    ModbusMaster _node;
    Stream *_serial = nullptr;

public:
    MyNPK();
    void begin(Stream &serialPort);
    NPK_Data read();

    // Replace the unsupported NPK soil-temperature channel with a validated
    // external reading while keeping the existing NPK payload/schema.
    void applyExternalTemperature(NPK_Data &data,
                                  float temperatureC,
                                  int16_t rawTemperature);
    void applyExternalMoisture(NPK_Data &data,
                               const SoilMoistureReading &reading);

    static const char *readMapToString(uint8_t readMap);

    String makeJsonFromData(const NPK_Data &data,
                            uint32_t sampleIntervalMs,
                            uint32_t consecutiveFailCount,
                            bool recoveredAfterFail,
                            uint32_t failStreakBeforeRecover,
                            bool sensorAlarm);

    static const char *errorCodeToString(uint8_t code);
};

#endif
