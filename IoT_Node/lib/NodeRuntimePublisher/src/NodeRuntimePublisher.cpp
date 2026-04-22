#include "NodeRuntimePublisher.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <cstdlib>

#include "Config.h"
#include "NetworkBridge.h"
#include "RtdbRestClient.h"

namespace {
float readFloatOr(JsonVariantConst value, float fallback = 0.0f) {
    if (value.is<float>()) {
        return value.as<float>();
    }
    if (value.is<double>()) {
        return static_cast<float>(value.as<double>());
    }
    if (value.is<long>()) {
        return static_cast<float>(value.as<long>());
    }
    if (value.is<int>()) {
        return static_cast<float>(value.as<int>());
    }
    if (value.is<const char *>()) {
        const char *s = value.as<const char *>();
        if (s && *s) {
            return strtof(s, nullptr);
        }
    }
    return fallback;
}

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

bool deletePath(FirebaseData &fbdo, const String &path, String *error = nullptr) {
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    RtdbRestResponse response;
    bool ok = rtdbRestClient().deletePath(path, response);
    if (!ok && error) {
        *error = response.detail;
    }
    return ok;
#else
    bool ok = Firebase.deleteNode(fbdo, path);
    if (!ok && error) {
        *error = fbdo.errorReason();
    }
    return ok;
#endif
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

void NodeRuntimePublisher::publishSystemStatus(FirebaseData &fbdo, const char *state, const char *detail, uint64_t utcMs) {
    if (!firebaseChannelReady()) {
        return;
    }

    _statusJson.clear();
    _statusJson.set("online", networkIsConnected());
    _statusJson.set("battery_v", -1.0);
    _statusJson.set("heap_free", (int)ESP.getFreeHeap());
    _statusJson.set("rssi", networkSignalDbm());
    _statusJson.set("heartbeat_age_sec", 0);
    _statusJson.set("system_state", state);
    _statusJson.set("state_detail", detail);
    _statusJson.set("ts_device", (int)(millis() / 1000U));
    _statusJson.set("last_sync_ts", utcMs ? static_cast<double>(utcMs / 1000ULL) : 0);

    String healthPath = String(_cfg.nodeLivePath) + "/health/overall";
    String writeError;
    if (!writeJsonPath(fbdo, healthPath, _statusJson, &writeError)) {
        CUS_DBGF("[FIREBASE] Status update fail: %s\n", writeError.c_str());
    }

    String newState = state ? state : "unknown";
    if (newState == _lastState) {
        return;
    }

    FirebaseJson ev;
    ev.set("component", "system");
    ev.set("from", _lastState.length() ? _lastState : "unknown");
    ev.set("to", newState);
    ev.set("reason", detail ? detail : "");
    ev.set("ts", utcMs ? static_cast<double>(utcMs / 1000ULL) : static_cast<double>(millis() / 1000U));
    bool warn = (newState == "degraded" || newState == "sensor_alarm" || newState == "offline_buffering");
    ev.set("severity", warn ? "warning" : "info");
    if (utcMs) {
        ev.set("ts_server_ms", static_cast<double>(utcMs));
    }

    String statusPath = String(_cfg.nodeStatusEventsPath) + "/" + makeStatusEventKey(utcMs);
    if (writeJsonPath(fbdo, statusPath, ev)) {
        _lastState = newState;
    }
}

void NodeRuntimePublisher::publishNodeInfoIfDue(FirebaseData &fbdo,
                                                const DeviceContext &deviceContext,
                                                const String &fwVersion,
                                                bool force,
                                                uint64_t utcMs) {
    uint32_t now = millis();
    if (!force && (now - _lastInfoPushMs < _cfg.nodeInfoPushIntervalMs)) {
        return;
    }
    _lastInfoPushMs = now;

    if (!firebaseChannelReady()) {
        return;
    }

    JsonDocument infoDoc;
    infoDoc["schema_version"] = 1;

    JsonObject identity = infoDoc["identity"].to<JsonObject>();
    identity["node_id"] = _cfg.nodeId;
    identity["device_uid"] = _cfg.deviceUid;
    identity["site_id"] = _cfg.siteId;

    JsonObject hardware = infoDoc["hardware"].to<JsonObject>();
    hardware["board"] = "ESP32-S3";
    hardware["power_type"] = _cfg.powerType;
    hardware["reset_count"] = deviceContext.resetReason();

    JsonObject firmware = infoDoc["firmware"].to<JsonObject>();
    firmware["version"] = fwVersion;
    firmware["build_id"] = String("build_") + __DATE__ + "_" + __TIME__;
    firmware["last_update_ts"] = utcMs > 0 ? static_cast<double>(utcMs / 1000ULL) : 0;

    JsonObject config = infoDoc["config"].to<JsonObject>();
    config["sampling_mode"] = "periodic";
    config["wake_interval_sec"] = (int)_cfg.wakeIntervalSec;
    config["timezone"] = _cfg.timezone;
    config["telemetry_retention_days"] = (int)_cfg.telemetryRetentionDays;

    JsonObject network = infoDoc["network"].to<JsonObject>();
    network["transport"] = networkTransportName();
    network["ip"] = networkLocalIp();
    network["mac"] = "";
    network["last_rssi"] = networkSignalDbm();

    String infoJson;
    serializeJson(infoDoc, infoJson);

    FirebaseJson out;
    if (!out.setJsonData(infoJson)) {
        return;
    }

    String writeError;
    if (!writeJsonPath(fbdo, _cfg.nodeInfoPath, out, &writeError)) {
        CUS_DBGF("[FIREBASE] %s update fail: %s\n", _cfg.nodeInfoPath, writeError.c_str());
    } else {
        CUS_DBGF("[FIREBASE] %s updated.\n", _cfg.nodeInfoPath);
    }
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
    dbg.set("ts_server", utcMs ? static_cast<double>(utcMs / 1000ULL) : 0);
    writeJsonPath(fbdo, String(_cfg.nodeLivePath) + "/meta/telemetry_debug", dbg);
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
    ch.set("key_mode", "deterministic_only");
    ch.set("counter_ok", (int)_telemetryOkCount);
    ch.set("counter_fail", (int)_telemetryFailCount);
    ch.set("counter_fallback", (int)_telemetryFallbackCount);
    ch.set("counter_tls_error", (int)_telemetryTlsErrorCount);
    ch.set("ts_device", (int)(millis() / 1000U));
    ch.set("ts_server", utcMs ? static_cast<double>(utcMs / 1000ULL) : 0);
    writeJsonPath(fbdo, String(_cfg.nodeLivePath) + "/meta/telemetry_channel", ch);
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

    String probePath = String(_cfg.nodeRootPath) + "/telemetry/_write_probe";
    String writeError;
    if (writeIntPath(fbdo, probePath, (int)(millis() / 1000U), &writeError)) {
        _probeOk = true;
        deletePath(fbdo, probePath);
        publishTelemetryDebug(fbdo, true, probePath, "probe_ok", utcMs);
        CUS_DBGF("[FIREBASE] Probe telemetry path OK: %s\n", probePath.c_str());
    } else {
        String err = writeError;
        publishTelemetryDebug(fbdo, false, probePath, err, utcMs);
        CUS_DBGF("[FIREBASE] Probe telemetry path FAIL: %s -> %s\n", probePath.c_str(), err.c_str());
    }
}

void NodeRuntimePublisher::publishNodeLive(FirebaseData &fbdo,
                                           const char *payload,
                                           const String &telemetryRefId,
                                           const RawTelemetryRecordContext &ctx,
                                           bool sensorError,
                                           uint64_t utcMs) {
    if (!firebaseChannelReady()) {
        return;
    }

    JsonDocument sourceDoc;
    if (deserializeJson(sourceDoc, payload) != DeserializationError::Ok) {
        return;
    }

    JsonObjectConst src = sourceDoc.as<JsonObjectConst>();
    JsonDocument liveDoc;
    liveDoc["schema_version"] = 1;

    JsonObject meta = liveDoc["meta"].to<JsonObject>();
    meta["last_event_id"] = telemetryRefId;
    uint32_t tsDeviceSec = ctx.tsDeviceMs / 1000U;
    meta["last_seen_ts"] = (int)tsDeviceSec;
    meta["uptime_sec"] = (int)(millis() / 1000U);
    meta["boot_reason"] = ctx.wakeReason;
    meta["last_sync_ts"] = utcMs ? static_cast<double>(utcMs / 1000ULL) : 0;

    JsonObject sensors = liveDoc["sensors"].to<JsonObject>();
    JsonVariantConst packetSrc = src["packet"];
    if (packetSrc.is<JsonObjectConst>()) {
        JsonObjectConst packet = packetSrc.as<JsonObjectConst>();
        JsonVariantConst npkSrc = packet["npk_data"];
        if (npkSrc.is<JsonObjectConst>()) {
            JsonObjectConst npk = npkSrc.as<JsonObjectConst>();
            JsonObject npkOut = sensors["npk"].to<JsonObject>();
            bool npkOk = npk["read_ok"] | false;
            bool npkValid = npk["npk_values_valid"] | npkOk;
            npkOut["n"] = npk["N"] | 0;
            npkOut["p"] = npk["P"] | 0;
            npkOut["k"] = npk["K"] | 0;
            npkOut["ec"] = readFloatOr(npk["ec"], 0.0f);
            npkOut["ph"] = readFloatOr(npk["ph"], 0.0f);
            npkOut["temperature_c"] = readFloatOr(npk["temp"], 0.0f);
            npkOut["humidity_percent"] = readFloatOr(npk["hum"], 0.0f);
            npkOut["ts_sample"] = (int)tsDeviceSec;
            npkOut["read_ok"] = npkOk;
            npkOut["sample_valid"] = npkValid;
            npkOut["status"] = npkValid ? "ok" : "error";
            npkOut["quality"] = npkValid ? 0.93 : 0.0;
            npkOut["error_code"] = npkValid ? "" : (npk["error_code"] | "read_fail");
        }

        JsonVariantConst shtSrc = packet["sht30_data"];
        if (shtSrc.is<JsonObjectConst>()) {
            JsonObjectConst sht = shtSrc.as<JsonObjectConst>();
            JsonObject shtOut = sensors["sht30"].to<JsonObject>();
            bool shtOk = sht["sht_read_ok"] | false;
            bool shtValid = sht["sht_sample_valid"] | false;
            shtOut["temperature_c"] = readFloatOr(sht["sht_temp_c"], 0.0f);
            shtOut["humidity_percent"] = readFloatOr(sht["sht_hum_pct"], 0.0f);
            shtOut["ts_sample"] = (int)tsDeviceSec;
            shtOut["read_ok"] = shtOk;
            shtOut["sample_valid"] = shtValid;
            shtOut["retry_count"] = sht["sht_retry_count"] | 0;
            shtOut["read_elapsed_ms"] = sht["sht_read_elapsed_ms"] | 0;
            shtOut["invalid_streak"] = sht["sht_invalid_streak"] | 0;
            shtOut["status"] = shtValid ? "ok" : "error";
            shtOut["quality"] = shtValid ? 0.98 : 0.0;
            shtOut["error_code"] = shtValid ? "" : (sht["sht_error"] | "read_fail");
        }
    }

    JsonObject modules = liveDoc["modules"].to<JsonObject>();
    JsonObject sim = modules["sim"].to<JsonObject>();
    sim["operator"] = "";
    sim["signal_dbm"] = 0;
    sim["network_status"] = "inactive";
    sim["ts_sample"] = 0;
    JsonObject gps = modules["gps"].to<JsonObject>();
    gps["enabled"] = false;
    gps["status"] = "inactive";
    gps["ts_sample"] = 0;

    bool npkReadOk = sensors["npk"]["read_ok"] | false;
    bool npkValid = sensors["npk"]["sample_valid"] | false;
    bool shtReadOk = sensors["sht30"]["read_ok"] | false;
    bool shtValid = sensors["sht30"]["sample_valid"] | false;
    JsonObject health = liveDoc["health"].to<JsonObject>();
    JsonObject overall = health["overall"].to<JsonObject>();
    overall["online"] = ctx.hasInternet;
    overall["battery_v"] = -1.0;
    overall["heap_free"] = (int)ESP.getFreeHeap();
    overall["rssi"] = ctx.rssi;
    overall["heartbeat_age_sec"] = 0;
    overall["sensor_error"] = sensorError;

    JsonObject hs = health["sensors"].to<JsonObject>();
    hs["npk"].to<JsonObject>()["read_ok"] = npkReadOk;
    hs["npk"].to<JsonObject>()["sample_valid"] = npkValid;
    hs["npk"].to<JsonObject>()["status"] = npkValid ? "ok" : "error";
    hs["npk"].to<JsonObject>()["last_success_ts"] = npkValid ? (int)tsDeviceSec : 0;
    hs["sht30"].to<JsonObject>()["read_ok"] = shtReadOk;
    hs["sht30"].to<JsonObject>()["sample_valid"] = shtValid;
    hs["sht30"].to<JsonObject>()["status"] = shtValid ? "ok" : "error";
    hs["sht30"].to<JsonObject>()["last_success_ts"] = shtValid ? (int)tsDeviceSec : 0;

    JsonObject hm = health["modules"].to<JsonObject>();
    hm["sim"].to<JsonObject>()["status"] = "inactive";
    hm["sim"].to<JsonObject>()["last_success_ts"] = 0;
    hm["gps"].to<JsonObject>()["status"] = "inactive";
    hm["gps"].to<JsonObject>()["last_success_ts"] = 0;

    String liveJson;
    serializeJson(liveDoc, liveJson);

    FirebaseJson out;
    if (!out.setJsonData(liveJson)) {
        return;
    }
    writeJsonPath(fbdo, _cfg.nodeLivePath, out);
}
