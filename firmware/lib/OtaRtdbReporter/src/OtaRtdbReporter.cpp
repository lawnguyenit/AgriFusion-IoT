#include "OtaRtdbReporter.h"

OtaRtdbReporter::OtaRtdbReporter(const char *statusPath, const char *historyPath)
    : _statusPath(statusPath), _historyPath(historyPath) {}

bool OtaRtdbReporter::reportEvent(FirebaseData &fbdo, const OtaStoredEvent &event,
                                  const String &runningVersion, const String &runningPartition) {
    if (!event.valid) {
        return true;
    }

    FirebaseJson statusJson;
    statusJson.set("stage", event.stage);
    statusJson.set("status", event.status);
    statusJson.set("detail", event.detail);
    statusJson.set("request_id", event.requestId);
    statusJson.set("firmware_version", runningVersion);
    statusJson.set("running_partition", runningPartition);
    statusJson.set("uptime_ms", (int)millis());

    if (!Firebase.setJSON(fbdo, _statusPath, statusJson)) {
        return false;
    }

    FirebaseJson historyJson;
    historyJson.set("stage", event.stage);
    historyJson.set("status", event.status);
    historyJson.set("detail", event.detail);
    historyJson.set("target_version", event.version);
    historyJson.set("request_id", event.requestId);
    historyJson.set("firmware_version", runningVersion);
    historyJson.set("running_partition", runningPartition);
    historyJson.set("uptime_ms", (int)millis());

    return Firebase.pushJSON(fbdo, _historyPath, historyJson);
}

bool OtaRtdbReporter::reportStatus(FirebaseData &fbdo, const char *state, const char *detail,
                                   const String &version, const String &requestId,
                                   const String &runningPartition) {
    OtaStoredEvent event;
    event.valid = true;
    event.stage = "status";
    event.status = state;
    event.detail = detail ? detail : "";
    event.version = version;
    event.requestId = requestId;
    return reportEvent(fbdo, event, version, runningPartition);
}

bool OtaRtdbReporter::flushPendingEvent(FirebaseData &fbdo, OtaStateStore &store,
                                        const String &runningVersion, const String &runningPartition) {
    OtaStoredEvent event;
    if (!store.loadPendingEvent(event) || !event.valid) {
        return true;
    }

    if (!reportEvent(fbdo, event, runningVersion, runningPartition)) {
        return false;
    }

    return store.clearPendingEvent();
}
