#include "RawTelemetryReporter.h"

#include <ArduinoJson.h>
#include <time.h>

#include "RtdbRestClient.h"

namespace {
void copyObject(JsonObject dst, JsonObjectConst src) {
    for (JsonPairConst kv : src) {
        dst[kv.key().c_str()] = kv.value();
    }
}

void setIfPresent(JsonObject dst, const char *key, JsonVariantConst value) {
    if (value.isNull()) {
        return;
    }
    dst[key] = value;
}

uint32_t currentUtcSecIfSynced() {
    time_t now = time(nullptr);
    if (now < 1700000000) {
        return 0;
    }
    return static_cast<uint32_t>(now);
}

String dateKeyFromEpoch(uint32_t epochSec) {
    if (epochSec == 0) {
        return "unsynced";
    }

    time_t sec = static_cast<time_t>(epochSec);
    struct tm tmUtc;
#if defined(_WIN32)
    gmtime_s(&tmUtc, &sec);
#else
    gmtime_r(&sec, &tmUtc);
#endif
    char buf[16];
    strftime(buf, sizeof(buf), "%Y-%m-%d", &tmUtc);
    return String(buf);
}

String telemetryKey(uint32_t keyTs, uint32_t seq) {
    char buf[40];
    snprintf(buf, sizeof(buf), "%lu_%03lu", (unsigned long)keyTs, (unsigned long)(seq % 1000U));
    return String(buf);
}

bool mapPacket(JsonObjectConst payload, JsonObject &packetOut) {
    JsonVariantConst packetSrc = payload["packet"];
    if (packetSrc.is<JsonObjectConst>()) {
        copyObject(packetOut, packetSrc.as<JsonObjectConst>());
        return true;
    }

    JsonObject npk = packetOut["npk_data"].to<JsonObject>();
    setIfPresent(npk, "sensor_type", payload["sensor_type"]);
    setIfPresent(npk, "sensor_id", payload["sensor_id"]);
    setIfPresent(npk, "read_ok", payload["read_ok"]);
    setIfPresent(npk, "error_code", payload["error_code"]);
    setIfPresent(npk, "error_code_raw", payload["error_code_raw"]);
    setIfPresent(npk, "retry_count", payload["retry_count"]);
    setIfPresent(npk, "timeout_ms", payload["timeout_ms"]);
    setIfPresent(npk, "read_duration_ms", payload["read_duration_ms"]);
    setIfPresent(npk, "crc_ok", payload["crc_ok"]);
    setIfPresent(npk, "frame_ok", payload["frame_ok"]);
    setIfPresent(npk, "sample_interval_ms", payload["sample_interval_ms"]);
    setIfPresent(npk, "consecutive_fail_count", payload["consecutive_fail_count"]);
    setIfPresent(npk, "recovered_after_fail", payload["recovered_after_fail"]);
    setIfPresent(npk, "fail_streak_before_recover", payload["fail_streak_before_recover"]);
    setIfPresent(npk, "sensor_alarm", payload["sensor_alarm"]);
    setIfPresent(npk, "npk_values_valid", payload["npk_values_valid"]);
    setIfPresent(npk, "temp", payload["temp"]);
    setIfPresent(npk, "hum", payload["hum"]);
    setIfPresent(npk, "ph", payload["ph"]);
    setIfPresent(npk, "ec", payload["ec"]);
    setIfPresent(npk, "N", payload["N"]);
    setIfPresent(npk, "P", payload["P"]);
    setIfPresent(npk, "K", payload["K"]);

    JsonObject sht = packetOut["sht30_data"].to<JsonObject>();
    setIfPresent(sht, "sht_read_ok", payload["sht_read_ok"]);
    setIfPresent(sht, "sht_sample_valid", payload["sht_sample_valid"]);
    setIfPresent(sht, "sht_temp_c", payload["sht_temp_c"]);
    setIfPresent(sht, "sht_hum_pct", payload["sht_hum_pct"]);
    setIfPresent(sht, "sht_error", payload["sht_error"]);
    setIfPresent(sht, "sht_retry_count", payload["sht_retry_count"]);
    setIfPresent(sht, "sht_read_elapsed_ms", payload["sht_read_elapsed_ms"]);
    setIfPresent(sht, "sht_invalid_streak", payload["sht_invalid_streak"]);
    setIfPresent(sht, "sht_addr", payload["sht_addr"]);
    setIfPresent(sht, "sht_sda", payload["sht_sda"]);
    setIfPresent(sht, "sht_scl", payload["sht_scl"]);
    return true;
}
}  // namespace

RawTelemetryReporter::RawTelemetryReporter(const char *nodeRootPath)
    : _nodeRootPath(nodeRootPath) {}

bool RawTelemetryReporter::buildRecord(const char *sensorPayloadJson,
                                       const RawTelemetryRecordContext &ctx,
                                       FirebaseJson &record,
                                       String &errorDetail) {
    errorDetail = "";
    record.clear();

    if (!sensorPayloadJson || strlen(sensorPayloadJson) == 0) {
        errorDetail = "empty payload";
        return false;
    }

    JsonDocument payloadDoc;
    if (deserializeJson(payloadDoc, sensorPayloadJson) != DeserializationError::Ok) {
        errorDetail = "invalid raw payload json";
        return false;
    }

    JsonObjectConst payload = payloadDoc.as<JsonObjectConst>();
    JsonDocument outDoc;
    outDoc["schema_version"] = 1;

    uint32_t tsDeviceSec = ctx.tsDeviceMs / 1000U;
    uint32_t tsServerSec = currentUtcSecIfSynced();
    uint32_t keyTs = tsServerSec > 0 ? tsServerSec : tsDeviceSec;
    String eventId = telemetryKey(keyTs, ctx.seq);
    String dateKey = dateKeyFromEpoch(tsServerSec);

    outDoc["ts_device"] = (int)tsDeviceSec;
    if (tsServerSec > 0) {
        outDoc["ts_server"] = (int)tsServerSec;
    }
    outDoc["seq_no"] = (int)ctx.seq;
    outDoc["_event_id"] = eventId;
    outDoc["_date_key"] = dateKey;

    JsonObject eventMeta = outDoc["event_meta"].to<JsonObject>();
    eventMeta["cycle_type"] = "periodic";
    eventMeta["wake_reason"] = ctx.wakeReason;
    eventMeta["duration_ms"] = 0;

    JsonObject packet = outDoc["packet"].to<JsonObject>();
    if (!mapPacket(payload, packet)) {
        errorDetail = "failed to map packet";
        return false;
    }

    JsonObjectConst npkSrc = packet["npk_data"].as<JsonObjectConst>();
    JsonObjectConst shtSrc = packet["sht30_data"].as<JsonObjectConst>();

    JsonObject sensors = outDoc["sensors"].to<JsonObject>();
    JsonObject npkOut = sensors["npk"].to<JsonObject>();
    bool npkReadOk = npkSrc["read_ok"] | false;
    bool npkSampleValid = npkSrc["npk_values_valid"] | npkReadOk;
    npkOut["read_ok"] = npkReadOk;
    npkOut["sample_valid"] = npkSampleValid;
    npkOut["status"] = npkSampleValid ? "ok" : "error";
    double npkQuality = npkSampleValid ? 0.93 : 0.0;
    npkOut["quality"] = npkQuality;
    npkOut["ts_sample"] = (int)tsDeviceSec;
    if (npkSampleValid) {
        npkOut["error_code"] = "";
    } else {
        npkOut["error_code"] = npkSrc["error_code"] | "read_fail";
    }

    JsonObject shtOut = sensors["sht30"].to<JsonObject>();
    bool shtReadOk = shtSrc["sht_read_ok"] | false;
    bool shtSampleValid = shtSrc["sht_sample_valid"] | false;
    shtOut["read_ok"] = shtReadOk;
    shtOut["sample_valid"] = shtSampleValid;
    shtOut["status"] = shtSampleValid ? "ok" : "error";
    double shtQuality = shtSampleValid ? 0.98 : 0.0;
    shtOut["quality"] = shtQuality;
    shtOut["ts_sample"] = (int)tsDeviceSec;
    if (shtSampleValid) {
        shtOut["error_code"] = "";
    } else {
        shtOut["error_code"] = shtSrc["sht_error"] | "read_fail";
    }

    eventMeta["duration_ms"] = npkSrc["read_duration_ms"] | 0;

    JsonObject modules = outDoc["modules"].to<JsonObject>();
    JsonObject sim = modules["sim"].to<JsonObject>();
    sim["operator"] = "";
    sim["signal_dbm"] = 0;
    sim["network_status"] = "inactive";
    sim["ts_sample"] = 0;
    JsonObject gps = modules["gps"].to<JsonObject>();
    gps["enabled"] = false;
    gps["status"] = "inactive";
    gps["ts_sample"] = 0;

    JsonObject health = outDoc["health"].to<JsonObject>();
    JsonObject overall = health["overall"].to<JsonObject>();
    overall["battery_v"] = -1.0;
    overall["heap_free"] = (int)ESP.getFreeHeap();
    overall["rssi"] = ctx.rssi;
    overall["online"] = ctx.hasInternet;

    JsonObject npkHealth = health["npk"].to<JsonObject>();
    npkHealth["status"] = npkSampleValid ? "ok" : "error";
    npkHealth["quality"] = npkQuality;
    if (npkSampleValid) {
        npkHealth["error_code"] = "";
    } else {
        npkHealth["error_code"] = npkSrc["error_code"] | "read_fail";
    }

    JsonObject shtHealth = health["sht30"].to<JsonObject>();
    shtHealth["status"] = shtSampleValid ? "ok" : "error";
    shtHealth["quality"] = shtQuality;
    if (shtSampleValid) {
        shtHealth["error_code"] = "";
    } else {
        shtHealth["error_code"] = shtSrc["sht_error"] | "read_fail";
    }

    JsonObject simHealth = health["sim"].to<JsonObject>();
    simHealth["status"] = "inactive";
    simHealth["error_code"] = "";

    String outJson;
    serializeJson(outDoc, outJson);
    if (!record.setJsonData(outJson)) {
        errorDetail = "failed to convert telemetry record to FirebaseJson";
        return false;
    }

    return true;
}

bool RawTelemetryReporter::publish(FirebaseData &fbdo,
                                   const char *sensorPayloadJson,
                                   const RawTelemetryRecordContext &ctx,
                                   String *outRawRefId,
                                   String &errorDetail) {
    FirebaseJson record;
    if (!buildRecord(sensorPayloadJson, ctx, record, errorDetail)) {
        return false;
    }

    return publishRecord(fbdo, record, outRawRefId, errorDetail, true);
}

bool RawTelemetryReporter::publishRecord(FirebaseData &fbdo,
                                         FirebaseJson &record,
                                         String *outRawRefId,
                                         String &errorDetail,
                                         bool updateLatest) {
    (void)updateLatest;

    String recordJson;
    record.toString(recordJson, false);
    JsonDocument recDoc;
    if (deserializeJson(recDoc, recordJson) != DeserializationError::Ok) {
        errorDetail = "invalid telemetry record json";
        return false;
    }

    JsonObjectConst recObj = recDoc.as<JsonObjectConst>();
    String dateKey = recObj["_date_key"] | "unsynced";
    String entryKey = recObj["_event_id"] | telemetryKey((uint32_t)(millis() / 1000U), 0);
    record.remove("_date_key");
    record.remove("_event_id");
    String path = _nodeRootPath + "/telemetry/" + dateKey + "/" + entryKey;

#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    String recordBody;
    record.toString(recordBody, false);
    RtdbRestResponse response;
    if (!rtdbRestClient().putRawJson(path, recordBody, response, true)) {
        errorDetail = path + " -> " + response.detail;
        return false;
    }
#else
    if (!Firebase.setJSON(fbdo, path, record)) {
        errorDetail = path + " -> " + fbdo.errorReason();
        return false;
    }
#endif

    record.set("raw_ref_id", entryKey);

    if (outRawRefId) {
        *outRawRefId = entryKey;
    }

    return true;
}
