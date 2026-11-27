#include "NodeRuntimePublisher.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <time.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "RtdbRestClient.h"

#if USE_SIM_NETWORK
#include "SimA7680C.h"
#endif

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

bool classifyRtdbJsonBody(const String &rawBody,
                          String &jsonOut,
                          bool &exists,
                          String *error = nullptr) {
    jsonOut = "";
    exists = false;

    String body = rawBody;
    body.trim();
    if (!body.length()) {
        if (error) {
            *error = "rtdb_get_empty_body";
        }
        return false;
    }

    JsonDocument doc;
    if (deserializeJson(doc, body) != DeserializationError::Ok) {
        if (error) {
            *error = "rtdb_get_invalid_json_body";
        }
        return false;
    }

    exists = !doc.as<JsonVariantConst>().isNull();
    if (exists) {
        jsonOut = body;
    }
    return true;
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
    if (!classifyRtdbJsonBody(response.body, jsonOut, exists, error)) {
        if (error && error->length()) {
            *error = String("path=") + path + " " + *error;
        }
        return false;
    }
    CUS_DBGF("[FIREBASE][LATEST] read path=%s exists=%d body_bytes=%u http=%d\n",
             path.c_str(),
             exists ? 1 : 0,
             (unsigned)response.body.length(),
             response.statusCode);
    if (!exists) {
        return true;
    }
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
    if (!classifyRtdbJsonBody(fbdo.jsonString(), jsonOut, exists, error)) {
        if (error && error->length()) {
            *error = String("path=") + path + " " + *error;
        }
        return false;
    }
    if (!exists) {
        return true;
    }
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

bool sampleTimeValid(uint32_t tsSample) {
    return tsSample >= 1700000000UL;
}

String dateKeyFromEpoch(uint32_t epochSec) {
    if (!sampleTimeValid(epochSec)) {
        return "unsynced";
    }

    time_t sec = static_cast<time_t>(epochSec);
    struct tm tmLocal;
#if defined(_WIN32)
    localtime_s(&tmLocal, &sec);
#else
    localtime_r(&sec, &tmLocal);
#endif
    char buf[16];
    strftime(buf, sizeof(buf), "%Y-%m-%d", &tmLocal);
    return String(buf);
}

bool publishLatestMeta(FirebaseData &fbdo,
                       const NodeRuntimeConfig &cfg,
                       JsonObjectConst candidate,
                       String *error) {
    uint32_t tsSample = static_cast<uint32_t>(candidate["system_record"]["time"]["ts_sample"] | 0UL);
    if (!sampleTimeValid(tsSample)) {
        if (error) {
            *error = "latest_meta_invalid_sample_time";
        }
        return false;
    }

    String eventKey = candidate["system_record"]["identity"]["record_id"] | String((unsigned long)tsSample);
    String recordPath = candidate["system_record"]["identity"]["record_path"] | String();
    while (recordPath.startsWith("/")) {
        recordPath.remove(0, 1);
    }
    String metaPath = cfg.nodeLatestMetaPath ? cfg.nodeLatestMetaPath : String(APP_RTDB_PATH_NODE_LATEST_META);

    FirebaseJson meta;
    meta.set("schema_version", 1);
    meta.set("node_id", APP_NODE_ID);
    meta.set("detected_device_uid", APP_NODE_DEVICE_UID);
    meta.set("detected_site_id", APP_NODE_SITE_ID);
    meta.set("latest_date_key", dateKeyFromEpoch(tsSample));
    meta.set("latest_event_key", eventKey);
    meta.set("latest_path", recordPath);
    meta.set("ts_device", candidate["system_record"]["time"]["device_uptime_sec"] | 0UL);
    meta.set("ts_server", static_cast<unsigned long>(tsSample));
    meta.set("primary_poll_after_sec", (int)(APP_SENSOR_SAMPLE_INTERVAL_MS / 1000UL));
    meta.set("retry_after_no_change_sec", (int)(APP_SLEEP_FAIL_RETRY_INTERVAL_MS / 1000UL));
    meta.set("source_type", "firebase");
    meta.set("source_uri", String("firebase://") + APP_NODE_ID + "/latest/meta");
    meta.set("updated_at_utc", static_cast<unsigned long>(tsSample));

    if (!writeJsonPath(fbdo, metaPath, meta, error)) {
        if (error && error->length()) {
            *error = String("path=") + metaPath + " " + *error;
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
#if !APP_RTDB_DEBUG_PUBLISH_ENABLED
    (void)fbdo;
    (void)state;
    (void)detail;
    (void)utcMs;
    return;
#else
    if (!firebaseChannelReady()) {
        return;
    }

    _statusJson.clear();
    _statusJson.set("state", state ? state : "unknown");
    _statusJson.set("detail", detail ? detail : "");
    _statusJson.set("online", networkIsConnected());

#if USE_SIM_NETWORK
    SimNetworkState sim = simReadNetworkState(false);
    _statusJson.set("signal_dbm", sim.signalDbm);
    _statusJson.set("signal_csq", sim.signalCsq);
    _statusJson.set("signal_valid", sim.signalCsq >= 0 && sim.signalCsq != 99);
    _statusJson.set("local_ip_valid", sim.localIpValid);
    if (sim.localIpValid) {
        _statusJson.set("local_ip", sim.localIp);
        _statusJson.set("local_ip_source", sim.localIpSource);
    }
    if (sim.operatorName.length() > 0 &&
        sim.operatorName.indexOf("ERROR") < 0 &&
        sim.operatorName.indexOf("+COPS:") < 0) {
        _statusJson.set("operator", sim.operatorName);
        _statusJson.set("operator_valid", true);
    } else {
        _statusJson.set("operator_valid", false);
    }
#else
    String localIp = networkLocalIp();
    bool localIpValid = localIp.length() > 0 && localIp != "0.0.0.0";
    int signalDbm = networkSignalDbm();
    _statusJson.set("signal_dbm", signalDbm);
    _statusJson.set("signal_valid", signalDbm != 0);
    _statusJson.set("local_ip_valid", localIpValid);
    if (localIpValid) {
        _statusJson.set("local_ip", localIp);
        _statusJson.set("local_ip_source", "wifi.localIP");
    }
    _statusJson.set("operator_valid", false);
#endif

    _statusJson.set("heap_free", (int)ESP.getFreeHeap());
    _statusJson.set("ts_device", (int)(millis() / 1000U));
    if (utcMs > 0) {
        _statusJson.set("ts_server", static_cast<double>(utcMs / 1000ULL));
    }
    writeJsonPath(fbdo, _cfg.nodeDebugStatusPath, _statusJson);
#endif
}

void NodeRuntimePublisher::publishTelemetryDebug(FirebaseData &fbdo,
                                                 bool ok,
                                                 const String &refOrPath,
                                                 const String &detail,
                                                 uint64_t utcMs) {
#if !APP_RTDB_DEBUG_PUBLISH_ENABLED
    (void)fbdo;
    (void)ok;
    (void)refOrPath;
    (void)detail;
    (void)utcMs;
    return;
#else
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
#endif
}

void NodeRuntimePublisher::publishTelemetryChannel(FirebaseData &fbdo,
                                                   bool ok,
                                                   bool fallbackUsed,
                                                   bool tlsError,
                                                   const char *stage,
                                                   const String &refOrPath,
                                                   const String &detail,
                                                   uint64_t utcMs) {
#if !APP_RTDB_DEBUG_PUBLISH_ENABLED
    (void)fbdo;
    (void)ok;
    (void)fallbackUsed;
    (void)tlsError;
    (void)stage;
    (void)refOrPath;
    (void)detail;
    (void)utcMs;
    return;
#else
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
#endif
}

void NodeRuntimePublisher::probeTelemetryPathIfNeeded(FirebaseData &fbdo, uint64_t utcMs) {
#if !APP_RTDB_DEBUG_PUBLISH_ENABLED
    (void)fbdo;
    (void)utcMs;
    return;
#else
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
#endif
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
            *error = String("path=") + _cfg.nodeLatestPath + " " + writeError;
        }
        return false;
    }

    if (!publishLatestMeta(fbdo, _cfg, candidate, &writeError)) {
        if (error) {
            *error = writeError;
        }
        return false;
    }

    CUS_DBGF("[FIREBASE] latest current/meta OK current=%s meta=%s event=%s\n",
             _cfg.nodeLatestPath,
             _cfg.nodeLatestMetaPath ? _cfg.nodeLatestMetaPath : APP_RTDB_PATH_NODE_LATEST_META,
             candidate["system_record"]["identity"]["record_id"] | "unknown");

    if (updatedLatest) {
        *updatedLatest = true;
    }
    return true;
}
