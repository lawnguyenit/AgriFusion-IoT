#ifndef RAW_TELEMETRY_REPORTER_H
#define RAW_TELEMETRY_REPORTER_H

#include <Arduino.h>
#include <FirebaseESP32.h>

struct RawTelemetryRecordContext {
    String deviceId;
    String bootId;
    String firmwareVersion;
    String runningPartition;
    String wakeReason;
    String recordType;
    String payloadKind;
    uint32_t seq = 0;
    uint32_t tsDeviceMs = 0;
    int resetReason = 0;
    int wifiStatus = 0;
    int rssi = 0;
    bool hasInternet = false;
    bool sensorError = false;
    uint32_t retryCount = 0;
    uint32_t timeoutMs = 0;
};

class RawTelemetryReporter {
public:
    explicit RawTelemetryReporter(const char *nodeRootPath);

    bool buildRecord(const char *sensorPayloadJson,
                     const RawTelemetryRecordContext &ctx,
                     FirebaseJson &record,
                     String &errorDetail);

    bool publish(FirebaseData &fbdo,
                 const char *sensorPayloadJson,
                 const RawTelemetryRecordContext &ctx,
                 String *outRawRefId,
                 String &errorDetail);

    bool publishRecord(FirebaseData &fbdo,
                       FirebaseJson &record,
                       String *outRawRefId,
                       String &errorDetail,
                       bool updateLatest = true);

    bool probePublishPath(FirebaseData &fbdo,
                          String *outProbePath,
                          String &errorDetail);

private:
    String _nodeRootPath;
};

#endif
