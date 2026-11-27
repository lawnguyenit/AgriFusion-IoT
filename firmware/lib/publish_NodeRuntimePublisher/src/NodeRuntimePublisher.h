#ifndef NODE_RUNTIME_PUBLISHER_H
#define NODE_RUNTIME_PUBLISHER_H

#include <Arduino.h>
#include <FirebaseESP32.h>

#include "Config.h"
#include "DeviceContext.h"
#include "RawTelemetryReporter.h"

struct NodeRuntimeConfig {
    const char *nodeRootPath = APP_RTDB_PATH_NODE_ROOT;
    const char *nodeInfoPath = APP_RTDB_PATH_NODE_INFO;
    const char *nodeLatestPath = APP_RTDB_PATH_NODE_LATEST;
    const char *nodeLatestMetaPath = APP_RTDB_PATH_NODE_LATEST_META;
    const char *nodeDebugRootPath = APP_RTDB_PATH_NODE_DEBUG_ROOT;
    const char *nodeDebugStatusPath = APP_RTDB_PATH_NODE_DEBUG_STATUS;
    const char *nodeDebugTelemetryPath = APP_RTDB_PATH_NODE_DEBUG_TELEMETRY;

    const char *nodeId = APP_NODE_ID;
    const char *deviceUid = APP_NODE_DEVICE_UID;
    const char *siteId = "farm_a_zone_2";
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
