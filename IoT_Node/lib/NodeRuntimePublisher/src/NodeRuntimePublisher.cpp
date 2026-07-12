#include "NodeRuntimePublisher.h"

#include <Arduino.h>
#include <ArduinoJson.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "RtdbRestClient.h"

namespace {
bool firebaseChannelReady() {
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    return networkIsConnected();
#else
    return networkIsConnected() && Firebase.ready();
#endif
}

bool writeJsonPath(FirebaseData &fbdo, const String &path, FirebaseJson &json, String *error = nullptr) {
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    String body;
    json.toString(body, false);
    RtdbRestResponse response;
    bool ok = rtdbRestClient().putRawJson(path, body, response, true);
    if (!ok && error) {
        *error = response.detail;
    }
    return ok;
#else
    bool ok = Firebase.setJSON(fbdo, path, json);
    if (!ok && error) {
        *error = fbdo.errorReason();
    }
    return ok;
#endif
}

bool writeIntPath(FirebaseData &fbdo, const String &path, int value, String *error = nullptr) {
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    RtdbRestResponse response;
    bool ok = rtdbRestClient().putRawJson(path, String(value), response, true);
    if (!ok && error) {
        *error = response.detail;
    }
    return ok;
#else
    bool ok = Firebase.setInt(fbdo, path, value);
    if (!ok && error) {
        *error = fbdo.errorReason();
    }
    return ok;
#endif
}

bool readJsonPath(FirebaseData &fbdo, const String &path, String &jsonOut, bool &exists, String *error = nullptr) {
    exists = false;
    jsonOut = "";

#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    RtdbRestResponse response;
    if (!rtdbRestClient().getRawJson(path, response)) {
        if (response.statusCode == 404) {
            return true;
        }
        if (error) {
            *error = response.detail;
        }
        return false;
    }
    String body = response.body;
    body.trim();
    if (!body.length() || body == "null") {
        return true;
    }
    jsonOut = body;
    exists = true;
    return true;
#else
    if (!Firebase.getJSON(fbdo, path)) {
        String err = fbdo.errorReason();
        String lowered = err;
        lowered.toLowerCase();
        if (lowered.indexOf("path not exist") >= 0 || lowered.indexOf("not found") >= 0) {
            return true;
        }
        if (error) {
            *error = err;
        }
        return false;
    }
    jsonOut = fbdo.jsonString();
    jsonOut.trim();
    if (!jsonOut.length() || jsonOut == "null") {
        return true;
    }
    exists = true;
    return true;
#endif
}

bool parseRecordDoc(FirebaseJson &record, JsonDocument &doc, String *error = nullptr) {
    String json;
    record.toString(json, false);
    if (deserializeJson(doc, json) != DeserializationError::Ok) {
        if (error) {
            *error = "invalid_record_json";
        }
        return false;
    }
    return true;
}

bool saveRecordDoc(FirebaseJson &record, JsonDocument &doc, String *error = nullptr) {
    String json;
    serializeJson(doc, json);
    if (!record.setJsonData(json)) {
        if (error) {
            *error = "record_set_json_fail";
        }
        return false;
    }
    return true;
}

int64_t extractLatestTsSample(const JsonObjectConst &root) {
    JsonVariantConst tsSample = root["system_record"]["time"]["ts_sample"];
    if (tsSample.isNull()) {
        return -1;
    }
    return (int64_t)(tsSample.as<long long>());
}
}  // namespace

NodeRuntimePublisher::NodeRuntimePublisher(const NodeRuntimeConfig &cfg) : _cfg(cfg) {}

String NodeRuntimePublisher::makeStatusEventKey(uint64_t utcMs) {
    _statusEventSeq++;
    unsigned long t = (unsigned long)((utcMs > 0 ? utcMs : (uint64_t)millis()) / 1000ULL);
    char buf[40];
    snprintf(buf, sizeof(buf), "%lu_evt%03lu", t, (unsigned long)(_statusEventSeq % 1000U));
    return String(buf);
}

void NodeRuntimePublisher::publishSystemStatus(FirebaseData &fbdo,
                                               const char *state,
                                               const char *detail,
                                               uint64_t utcMs) {
    if (!firebaseChannelReady()) {
        return;
    }

    _statusJson.clear();
    _statusJson.set("state", state ? state : "unknown");
    _statusJson.set("detail", detail ? detail : "");
    _statusJson.set("online", networkIsConnected());
    _statusJson.set("signal_dbm", networkSignalDbm());
    _statusJson.set("heap_free", (int)ESP.getFreeHeap());
    _statusJson.set("ts_device", (int)(millis() / 1000U));
    if (utcMs > 0) {
        _statusJson.set("ts_server", static_cast<double>(utcMs / 1000ULL));
    }
    writeJsonPath(fbdo, _cfg.nodeDebugStatusPath, _statusJson);
}

void NodeRuntimePublisher::publishTelemetryDebug(FirebaseData &fbdo,
                                                 bool ok,
                                                 const String &refOrPath,
                                                 const String &detail,
                                                 uint64_t utcMs) {
    if (!firebaseChannelReady()) {
        return;
    }

    FirebaseJson dbg;
    dbg.set("ok", ok);
    dbg.set("ref_or_path", refOrPath);
    dbg.set("detail", detail);
    dbg.set("ts_device", (int)(millis() / 1000U));
    if (utcMs > 0) {
        dbg.set("ts_server", static_cast<double>(utcMs / 1000ULL));
    }
    writeJsonPath(fbdo, String(_cfg.nodeDebugTelemetryPath) + "/last_debug", dbg);
}

void NodeRuntimePublisher::publishTelemetryChannel(FirebaseData &fbdo,
                                                   bool ok,
                                                   bool fallbackUsed,
                                                   bool tlsError,
                                                   const char *stage,
                                                   const String &refOrPath,
                                                   const String &detail,
                                                   uint64_t utcMs) {
    if (!firebaseChannelReady()) {
        return;
    }

    if (ok) {
        _telemetryOkCount++;
    } else {
        _telemetryFailCount++;
    }
    if (fallbackUsed) {
        _telemetryFallbackCount++;
    }
    if (tlsError) {
        _telemetryTlsErrorCount++;
    }

    FirebaseJson ch;
    ch.set("last_stage", stage ? stage : "unknown");
    ch.set("last_ok", ok);
    ch.set("fallback_active", fallbackUsed);
    ch.set("tls_error", tlsError);
    ch.set("last_ref_or_path", refOrPath);
    ch.set("last_detail", detail);
    ch.set("counter_ok", (int)_telemetryOkCount);
    ch.set("counter_fail", (int)_telemetryFailCount);
    ch.set("counter_fallback", (int)_telemetryFallbackCount);
    ch.set("counter_tls_error", (int)_telemetryTlsErrorCount);
    ch.set("ts_device", (int)(millis() / 1000U));
    if (utcMs > 0) {
        ch.set("ts_server", static_cast<double>(utcMs / 1000ULL));
    }
    writeJsonPath(fbdo, String(_cfg.nodeDebugTelemetryPath) + "/channel", ch);
}

void NodeRuntimePublisher::probeTelemetryPathIfNeeded(FirebaseData &fbdo, uint64_t utcMs) {
    if (_probeOk) {
        return;
    }
    if (!firebaseChannelReady()) {
        return;
    }
    if (millis() - _lastProbeMs < _cfg.probeIntervalMs) {
        return;
    }
    _lastProbeMs = millis();

    String probePath = APP_RTDB_PATH_NODE_TELEMETRY_PROBE;
    String writeError;
    if (writeIntPath(fbdo, probePath, (int)(millis() / 1000U), &writeError)) {
        _probeOk = true;
        publishTelemetryDebug(fbdo, true, probePath, "probe_ok", utcMs);
    } else {
        publishTelemetryDebug(fbdo, false, probePath, writeError, utcMs);
    }
}

bool NodeRuntimePublisher::publishLatestIfNewer(FirebaseData &fbdo,
                                                FirebaseJson &record,
                                                bool *updatedLatest,
                                                String *error) {
    if (updatedLatest) {
        *updatedLatest = false;
    }
    if (!firebaseChannelReady()) {
        if (error) {
            *error = "latest_channel_not_ready";
        }
        return false;
    }

    JsonDocument candidateDoc;
    String parseError;
    if (!parseRecordDoc(record, candidateDoc, &parseError)) {
        if (error) {
            *error = parseError;
        }
        return false;
    }

    JsonObject candidate = candidateDoc.as<JsonObject>();
    int64_t candidateTs = extractLatestTsSample(candidate);
    if (candidateTs <= 0) {
        return true;
    }

    String currentJson;
    bool currentExists = false;
    String readError;
    if (!readJsonPath(fbdo, _cfg.nodeLatestPath, currentJson, currentExists, &readError)) {
        if (error) {
            *error = readError;
        }
        return false;
    }

    int64_t currentTs = -1;
    if (currentExists) {
        JsonDocument currentDoc;
        if (deserializeJson(currentDoc, currentJson) == DeserializationError::Ok) {
            currentTs = extractLatestTsSample(currentDoc.as<JsonObjectConst>());
        }
    }

    if (currentTs >= candidateTs) {
        return true;
    }

    candidate["system_record"]["sync"]["latest_updated"] = true;
    if (!saveRecordDoc(record, candidateDoc, &parseError)) {
        if (error) {
            *error = parseError;
        }
        return false;
    }

    String writeError;
    if (!writeJsonPath(fbdo, _cfg.nodeLatestPath, record, &writeError)) {
        if (error) {
            *error = writeError;
        }
        return false;
    }

    if (updatedLatest) {
        *updatedLatest = true;
    }
    return true;
}
