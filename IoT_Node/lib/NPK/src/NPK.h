#ifndef NPK_H
#define NPK_H

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ModbusMaster.h>

struct NPK_Data {
    float hum;
    float temp;
    float ph;
    int ec;
    int n;
    int p;
    int k;

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

    String makeJsonFromData(const NPK_Data &data,
                            uint32_t sampleIntervalMs,
                            uint32_t consecutiveFailCount,
                            bool recoveredAfterFail,
                            uint32_t failStreakBeforeRecover,
                            bool sensorAlarm);

    static const char *errorCodeToString(uint8_t code);
};

#endif
