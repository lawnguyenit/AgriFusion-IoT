#ifndef NODE_RUNTIME_PUBLISHER_H
#define NODE_RUNTIME_PUBLISHER_H

#include <Arduino.h>
#include <FirebaseESP32.h>

#include "DeviceContext.h"
#include "RawTelemetryReporter.h"

struct NodeRuntimeConfig {
    const char *nodeRootPath = "/Node1";
    const char *nodeInfoPath = "/Node1/info";
    const char *nodeLatestPath = "/Node1/latest";
    const char *nodeDebugRootPath = "/debug/Node1";
    const char *nodeDebugStatusPath = "/debug/Node1/status";
    const char *nodeDebugTelemetryPath = "/debug/Node1/telemetry";

    const char *nodeId = "Node1";
    const char *deviceUid = "esp32s3_node1";
    const char *siteId = "farm_a_zone_1";
    const char *powerType = "solar_battery";
    const char *timezone = "Asia/Ho_Chi_Minh";

    uint32_t telemetryRetentionDays = 30;
    uint32_t wakeIntervalSec = 60;
    uint32_t probeIntervalMs = 30000;
};

class NodeRuntimePublisher {
public:
    explicit NodeRuntimePublisher(const NodeRuntimeConfig &cfg);

    void publishSystemStatus(FirebaseData &fbdo, const char *state, const char *detail, uint64_t utcMs);

    void publishTelemetryDebug(FirebaseData &fbdo,
                               bool ok,
                               const String &refOrPath,
                               const String &detail,
                               uint64_t utcMs);

    void publishTelemetryChannel(FirebaseData &fbdo,
                                 bool ok,
                                 bool fallbackUsed,
                                 bool tlsError,
                                 const char *stage,
                                 const String &refOrPath,
                                 const String &detail,
                                 uint64_t utcMs);

    void probeTelemetryPathIfNeeded(FirebaseData &fbdo, uint64_t utcMs);

    bool publishLatestIfNewer(FirebaseData &fbdo,
                              FirebaseJson &record,
                              bool *updatedLatest,
                              String *error = nullptr);

private:
    NodeRuntimeConfig _cfg;
    FirebaseJson _statusJson;
    String _lastState;
    uint32_t _statusEventSeq = 0;
    uint32_t _lastProbeMs = 0;
    bool _probeOk = false;
    uint32_t _telemetryOkCount = 0;
    uint32_t _telemetryFailCount = 0;
    uint32_t _telemetryFallbackCount = 0;
    uint32_t _telemetryTlsErrorCount = 0;

    String makeStatusEventKey(uint64_t utcMs);
};

#endif
