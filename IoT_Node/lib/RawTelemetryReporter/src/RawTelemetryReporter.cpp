#include "RawTelemetryReporter.h"

#include <ArduinoJson.h>
#include <esp_system.h>
#include <time.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "RtdbRestClient.h"

#if USE_SIM_NETWORK
#include "SimA7680C.h"
#endif

namespace {
void setNull(JsonVariant value) {
    value.set(nullptr);
}

String sanitizeBuildToken(const String &input) {
    String out = input;
    out.replace(":", "_");
    out.replace(" ", "_");
    return out;
}

String currentBuildId() {
    return "build_" + sanitizeBuildToken(String(__DATE__)) + "_" + sanitizeBuildToken(String(__TIME__));
}

String resetReasonName(int resetReason) {
#if defined(ESP_RST_UNKNOWN)
    switch (resetReason) {
        case ESP_RST_UNKNOWN: return "unknown";
        case ESP_RST_POWERON: return "power_on";
        case ESP_RST_EXT: return "external";
        case ESP_RST_SW: return "software";
        case ESP_RST_PANIC: return "panic";
        case ESP_RST_INT_WDT: return "interrupt_watchdog";
        case ESP_RST_TASK_WDT: return "task_watchdog";
        case ESP_RST_WDT: return "watchdog";
        case ESP_RST_DEEPSLEEP: return "deep_sleep";
        case ESP_RST_BROWNOUT: return "brownout";
        case ESP_RST_SDIO: return "sdio";
        default: return "other";
    }
#else
    (void)resetReason;
    return "unknown";
#endif
}

bool sampleTimeValid(uint32_t tsSample) {
    return tsSample >= 1700000000UL;
}

String dateKeyFromEpoch(uint32_t epochSec) {
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

String makeRecordId(uint32_t tsSample, uint32_t seqNo) {
    char buf[48];
    snprintf(buf, sizeof(buf), "%lu_%lu", (unsigned long)tsSample, (unsigned long)seqNo);
    return String(buf);
}

String makeTelemetryPath(uint32_t tsSample, uint32_t seqNo) {
    if (!sampleTimeValid(tsSample)) {
        return "";
    }
    return String(APP_RTDB_PATH_NODE_TELEMETRY) + "/" + dateKeyFromEpoch(tsSample) + "/" + makeRecordId(tsSample, seqNo);
}

bool parseFirebaseJson(FirebaseJson &record, JsonDocument &doc, String &errorDetail) {
    String json;
    record.toString(json, false);
    if (deserializeJson(doc, json) != DeserializationError::Ok) {
        errorDetail = "invalid_record_json";
        return false;
    }
    return true;
}

bool saveFirebaseJson(FirebaseJson &record, JsonDocument &doc, String &errorDetail) {
    String json;
    serializeJson(doc, json);
    if (!record.setJsonData(json)) {
        errorDetail = "record_set_json_fail";
        return false;
    }
    return true;
}

bool loadExistingPath(FirebaseData &fbdo,
                      const String &path,
                      bool &exists,
                      String &errorDetail,
                      TelemetryPublishResult *publishResult) {
    exists = false;

#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    RtdbRestResponse response;
    if (!rtdbRestClient().getRawJson(path, response)) {
        if (publishResult) {
            publishResult->transportOk = response.transportOk;
            publishResult->responseReceived = response.responseReceived;
            publishResult->httpStatus = response.statusCode;
            publishResult->stage = response.stage;
            publishResult->detail = response.detail;
        }
        if (response.statusCode == 404) {
            return true;
        }
        errorDetail = response.detail.length() ? response.detail : "rtdb_get_fail";
        return false;
    }

    String body = response.body;
    body.trim();
    exists = body.length() > 0 && body != "null";
    if (publishResult) {
        publishResult->transportOk = response.transportOk;
        publishResult->responseReceived = response.responseReceived;
        publishResult->httpStatus = response.statusCode;
        publishResult->stage = response.stage;
        publishResult->detail = response.detail;
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
        if (publishResult) {
            publishResult->httpStatus = fbdo.httpCode();
            publishResult->stage = "firebase_get_fail";
            publishResult->detail = err;
        }
        errorDetail = err.length() ? err : "firebase_get_fail";
        return false;
    }

    String body = fbdo.jsonString();
    body.trim();
    exists = body.length() > 0 && body != "null";
    if (publishResult) {
        publishResult->httpStatus = fbdo.httpCode();
        publishResult->stage = "firebase_get_ok";
        publishResult->detail = "ok";
    }
    return true;
#endif
}

bool writeRecordPath(FirebaseData &fbdo,
                     const String &path,
                     FirebaseJson &record,
                     String &errorDetail,
                     TelemetryPublishResult &publishResult) {
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    String body;
    record.toString(body, false);
    RtdbRestResponse response;
    bool ok = rtdbRestClient().putRawJson(path, body, response, true);
    publishResult.transportOk = response.transportOk;
    publishResult.responseReceived = response.responseReceived;
    publishResult.httpStatus = response.statusCode;
    publishResult.stage = response.stage;
    publishResult.detail = response.detail;
    if (!ok) {
        errorDetail = response.detail.length() ? response.detail : "rtdb_write_fail";
    }
    return ok;
#else
    bool ok = Firebase.setJSON(fbdo, path, record);
    publishResult.transportOk = networkIsConnected();
    publishResult.responseReceived = ok || fbdo.httpCode() != 0;
    publishResult.httpStatus = fbdo.httpCode();
    publishResult.stage = ok ? "firebase_write_ok" : "firebase_write_fail";
    publishResult.detail = ok ? "ok" : fbdo.errorReason();
    if (!ok) {
        errorDetail = publishResult.detail.length() ? publishResult.detail : "firebase_write_fail";
    }
    return ok;
#endif
}

uint32_t extractTsSample(JsonObjectConst root) {
    JsonVariantConst tsValue = root["system_record"]["time"]["ts_sample"];
    if (tsValue.isNull()) {
        return 0;
    }
    return static_cast<uint32_t>(tsValue.as<unsigned long>());
}

uint32_t extractSeqNo(JsonObjectConst root) {
    JsonVariantConst seqValue = root["system_record"]["identity"]["seq_no"];
    if (seqValue.isNull()) {
        return 0;
    }
    return static_cast<uint32_t>(seqValue.as<unsigned long>());
}

void fillUploadSlotDefaults(JsonObject slot, size_t payloadBytes, const char *stage) {
    slot["attempted"] = false;
    slot["upload_ok"] = false;
    slot["upload_stage"] = stage ? stage : "not_attempted";
    setNull(slot["http_status"]);
    setNull(slot["tls_ok"]);
    setNull(slot["upload_latency_ms"]);
    slot["payload_bytes"] = static_cast<unsigned long>(payloadBytes);
    slot["buffer_reason_code"] = "";
    slot["last_error_code"] = "";
}

void populateSht30Record(JsonObject sensorRecord, JsonObjectConst shtPayload) {
    JsonObject sht30 = sensorRecord[APP_SENSOR_ID_SHT30].to<JsonObject>();
    sht30["sensor_type"] = APP_SENSOR_TYPE_SHT30;

    JsonObject values = sht30["values"].to<JsonObject>();
    bool sampleValid = shtPayload["sht_sample_valid"] | false;
    if (sampleValid) {
        values["air_temp_c"] = shtPayload["sht_temp_c"];
        values["air_rh_pct"] = shtPayload["sht_hum_pct"];
    } else {
        setNull(values["air_temp_c"]);
        setNull(values["air_rh_pct"]);
    }

    JsonObject readStatus = sht30["read_status"].to<JsonObject>();
    readStatus["read_ok"] = shtPayload["sht_read_ok"] | false;
    readStatus["sample_valid"] = sampleValid;
    readStatus["error_code"] = String(shtPayload["sht_error"] | "");
    readStatus["retry_count"] = shtPayload["sht_retry_count"] | 0;
    readStatus["read_elapsed_ms"] = shtPayload["sht_read_elapsed_ms"] | 0;
    readStatus["invalid_streak"] = shtPayload["sht_invalid_streak"] | 0;
}

void populateSoilRecord(JsonObject sensorRecord, JsonObjectConst npkPayload) {
    JsonObject soil = sensorRecord[APP_SENSOR_ID_SOIL_7IN1].to<JsonObject>();
    soil["sensor_type"] = APP_SENSOR_TYPE_SOIL_7IN1;

    JsonObject values = soil["values"].to<JsonObject>();
    bool sampleValid = npkPayload["npk_values_valid"] | false;
    if (sampleValid) {
        values["soil_temp_c"] = npkPayload["temp"];
        values["soil_moisture_pct"] = npkPayload["hum"];
        values["soil_ph"] = npkPayload["ph"];
        values["soil_ec_us_cm"] = npkPayload["ec"];
        values["soil_n_proxy"] = npkPayload["N"];
        values["soil_p_proxy"] = npkPayload["P"];
        values["soil_k_proxy"] = npkPayload["K"];
    } else {
        setNull(values["soil_temp_c"]);
        setNull(values["soil_moisture_pct"]);
        setNull(values["soil_ph"]);
        setNull(values["soil_ec_us_cm"]);
        setNull(values["soil_n_proxy"]);
        setNull(values["soil_p_proxy"]);
        setNull(values["soil_k_proxy"]);
    }

    JsonObject readStatus = soil["read_status"].to<JsonObject>();
    readStatus["read_ok"] = npkPayload["read_ok"] | false;
    readStatus["sample_valid"] = sampleValid;
    readStatus["crc_ok"] = npkPayload["crc_ok"] | false;
    readStatus["frame_ok"] = npkPayload["frame_ok"] | false;
    readStatus["error_code"] = String(npkPayload["error_code"] | "");
    readStatus["raw_error_code"] = npkPayload["error_code_raw"] | 0;
    readStatus["retry_count"] = npkPayload["retry_count"] | 0;
    readStatus["read_elapsed_ms"] = npkPayload["read_duration_ms"] | 0;
    readStatus["timeout_ms"] = npkPayload["timeout_ms"] | 0;
    readStatus["consecutive_fail_count"] = npkPayload["consecutive_fail_count"] | 0;
    readStatus["recovered_after_fail"] = npkPayload["recovered_after_fail"] | false;
}

void populateNetworkRecord(JsonObject network) {
    String localIp = networkLocalIp();
    bool ipValid = localIp.length() > 0 && localIp != "0.0.0.0";

#if USE_SIM_NETWORK
    SimNetworkState sim = simReadNetworkState(false);
    network["registered"] = sim.networkRegistered;
    network["attached"] = sim.packetAttached;
    network["pdp_active"] = sim.gprsConnected;
    network["operator"] = sim.operatorName;
    setNull(network["rat"]);
    network["signal_dbm"] = sim.signalDbm;
    network["ip_valid"] = ipValid;
#else
    bool connected = networkIsConnected();
    network["registered"] = connected;
    network["attached"] = connected;
    network["pdp_active"] = connected;
    network["operator"] = "";
    setNull(network["rat"]);
    network["signal_dbm"] = networkSignalDbm();
    network["ip_valid"] = ipValid;
#endif
}

void populateCoreRecord(JsonDocument &outDoc,
                        JsonObjectConst packetPayload,
                        const RawTelemetryRecordContext &ctx,
                        size_t payloadBytes) {
    JsonObject sensorRecord = outDoc["sensor_record"].to<JsonObject>();
    JsonObjectConst npkPayload = packetPayload["npk_data"];
    JsonObjectConst shtPayload = packetPayload["sht30_data"];
    JsonObjectConst systemPayload = packetPayload["system_data"];

    populateSht30Record(sensorRecord, shtPayload);
    populateSoilRecord(sensorRecord, npkPayload);

    JsonObject simRecord = outDoc["sim_record"].to<JsonObject>();
    simRecord["transport"] = networkTransportName();
    JsonObject network = simRecord["network"].to<JsonObject>();
    populateNetworkRecord(network);

    JsonObject upload = simRecord["upload"].to<JsonObject>();
    upload["target"] = "firebase_rtdb";
    fillUploadSlotDefaults(upload["direct"].to<JsonObject>(), payloadBytes, "not_attempted");
    fillUploadSlotDefaults(upload["replay"].to<JsonObject>(), payloadBytes, "not_replayed");

    JsonObject systemRecord = outDoc["system_record"].to<JsonObject>();
    systemRecord["schema_version"] = 2;
    systemRecord["source_level"] = "raw_telemetry";
    systemRecord["synthetic"] = false;
    systemRecord["manual_edit"] = false;
    systemRecord["debug_mode"] = false;

    uint32_t tsSample = systemPayload["sample_epoch_sec"] | 0;
    bool timeValid = (systemPayload["sample_time_valid"] | false) && sampleTimeValid(tsSample);
    String recordId = timeValid ? makeRecordId(tsSample, ctx.seq) : "";
    String recordPath = timeValid ? makeTelemetryPath(tsSample, ctx.seq) : "";

    JsonObject identity = systemRecord["identity"].to<JsonObject>();
    identity["node_id"] = APP_NODE_ID;
    identity["site_id"] = APP_NODE_SITE_ID;
    identity["device_uid"] = ctx.deviceId.length() ? ctx.deviceId : APP_NODE_DEVICE_UID;
    if (recordId.length()) {
        identity["record_id"] = recordId;
        identity["record_path"] = recordPath;
    } else {
        setNull(identity["record_id"]);
        setNull(identity["record_path"]);
    }
    identity["seq_no"] = static_cast<unsigned long>(ctx.seq);
    identity["boot_id"] = ctx.bootId;

    JsonObject timeObject = systemRecord["time"].to<JsonObject>();
    if (timeValid) {
        timeObject["ts_sample"] = static_cast<unsigned long>(tsSample);
    } else {
        setNull(timeObject["ts_sample"]);
    }
    setNull(timeObject["ts_server"]);
    timeObject["timezone"] = APP_NODE_TIMEZONE;
    timeObject["clock_source"] = timeValid ? "network_time" : "unsynced_device";
    timeObject["time_valid"] = timeValid;
    timeObject["time_reconstructed"] = false;
    timeObject["sample_interval_sec"] = static_cast<unsigned long>(APP_SENSOR_SAMPLE_INTERVAL_MS / 1000UL);
    timeObject["device_uptime_sec"] = static_cast<unsigned long>(ctx.tsDeviceMs / 1000UL);

    JsonObject cycle = systemRecord["cycle"].to<JsonObject>();
    cycle["record_type"] = ctx.recordType;
    cycle["wake_reason"] = ctx.wakeReason;
    cycle["cycle_type"] = String(ctx.payloadKind) == APP_PAYLOAD_KIND_SENSOR_ALARM ? "sensor_alarm" : "periodic";
    cycle["cycle_duration_ms"] = (npkPayload["read_duration_ms"] | 0) + (shtPayload["sht_read_elapsed_ms"] | 0);
    cycle["sleep_planned_sec"] = static_cast<unsigned long>(APP_SENSOR_SAMPLE_INTERVAL_MS / 1000UL);

    JsonObject power = systemRecord["power"].to<JsonObject>();
    power["power_type"] = APP_NODE_POWER_TYPE;
    setNull(power["battery_mv"]);
    setNull(power["battery_pct"]);
    setNull(power["panel_mv"]);
    setNull(power["charge_state"]);
    setNull(power["brownout_count"]);

    JsonObject deviceHealth = systemRecord["device_health"].to<JsonObject>();
    deviceHealth["heap_free"] = static_cast<unsigned long>(ESP.getFreeHeap());
    setNull(deviceHealth["reset_count"]);
    deviceHealth["reset_reason"] = resetReasonName(ctx.resetReason);
    setNull(deviceHealth["watchdog_count"]);
    setNull(deviceHealth["storage_free_bytes"]);
    setNull(deviceHealth["buffer_queue_len"]);

    JsonObject firmware = systemRecord["firmware"].to<JsonObject>();
    firmware["firmware_version"] = ctx.firmwareVersion;
    firmware["build_id"] = currentBuildId();
    firmware["config_version"] = APP_CONFIG_VERSION;
    firmware["calibration_version"] = APP_CALIBRATION_VERSION;
    firmware["running_partition"] = ctx.runningPartition;

    JsonObject integrity = systemRecord["integrity"].to<JsonObject>();
    setNull(integrity["record_hash"]);
    setNull(integrity["payload_crc_ok"]);
    integrity["duplicate_policy"] = "deterministic_key";
    integrity["overwrite_protected"] = true;

    JsonObject sync = systemRecord["sync"].to<JsonObject>();
    sync["telemetry_persisted"] = false;
    setNull(sync["telemetry_record_path"]);
    sync["buffered"] = false;
    sync["replayed"] = false;
    sync["latest_updated"] = false;
    sync["buffer_reason_code"] = "";
    sync["last_error_code"] = "";
}

}  // namespace

RawTelemetryReporter::RawTelemetryReporter(const char *nodeRootPath)
    : _nodeRootPath(nodeRootPath ? nodeRootPath : APP_RTDB_PATH_NODE_ROOT) {}

bool RawTelemetryReporter::buildRecord(const char *sensorPayloadJson,
                                       const RawTelemetryRecordContext &ctx,
                                       FirebaseJson &record,
                                       String &errorDetail) {
    if (!sensorPayloadJson || !strlen(sensorPayloadJson)) {
        errorDetail = "empty_sensor_payload";
        return false;
    }

    JsonDocument payloadDoc;
    if (deserializeJson(payloadDoc, sensorPayloadJson) != DeserializationError::Ok) {
        errorDetail = "invalid_sensor_payload_json";
        return false;
    }

    JsonObjectConst packetPayload = payloadDoc["packet"];
    if (packetPayload.isNull()) {
        errorDetail = "missing_packet_payload";
        return false;
    }

    JsonDocument outDoc;
    populateCoreRecord(outDoc, packetPayload, ctx, strlen(sensorPayloadJson));

    String out;
    serializeJson(outDoc, out);
    if (!record.setJsonData(out)) {
        errorDetail = "record_set_json_fail";
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

    TelemetryPublishResult publishResult;
    bool ok = publishRecord(fbdo, record, publishResult, errorDetail);
    if (outRawRefId) {
        *outRawRefId = publishResult.path.length() ? publishResult.path : publishResult.refId;
    }
    return ok;
}

bool RawTelemetryReporter::publishRecord(FirebaseData &fbdo,
                                         FirebaseJson &record,
                                         TelemetryPublishResult &publishResult,
                                         String &errorDetail) {
    publishResult = TelemetryPublishResult{};

    JsonDocument doc;
    if (!parseFirebaseJson(record, doc, errorDetail)) {
        publishResult.stage = "invalid_record_json";
        publishResult.detail = errorDetail;
        return false;
    }

    JsonObject root = doc.as<JsonObject>();
    uint32_t tsSample = extractTsSample(root);
    uint32_t seqNo = extractSeqNo(root);
    String recordPath = makeTelemetryPath(tsSample, seqNo);
    String recordId = sampleTimeValid(tsSample) ? makeRecordId(tsSample, seqNo) : "";

    publishResult.path = recordPath;
    publishResult.refId = recordId;

    if (!sampleTimeValid(tsSample) || !recordPath.length() || !recordId.length()) {
        errorDetail = "invalid_time_quarantined";
        publishResult.stage = "invalid_time_quarantined";
        publishResult.detail = errorDetail;
        return false;
    }

    root["system_record"]["identity"]["record_id"] = recordId;
    root["system_record"]["identity"]["record_path"] = recordPath;
    root["system_record"]["sync"]["telemetry_persisted"] = true;
    root["system_record"]["sync"]["telemetry_record_path"] = recordPath;

    if (!saveFirebaseJson(record, doc, errorDetail)) {
        publishResult.stage = "record_prepare_fail";
        publishResult.detail = errorDetail;
        return false;
    }

    bool exists = false;
    if (!loadExistingPath(fbdo, recordPath, exists, errorDetail, &publishResult)) {
        root["system_record"]["sync"]["telemetry_persisted"] = false;
        setNull(root["system_record"]["sync"]["telemetry_record_path"]);
        saveFirebaseJson(record, doc, errorDetail);
        return false;
    }

    if (exists) {
        record.set("system_record/sync/last_error_code", "duplicate_key");
        publishResult.duplicate = true;
        publishResult.stage = "duplicate_key";
        publishResult.detail = "telemetry_record_exists";
        errorDetail = publishResult.detail;
        return false;
    }

    if (writeRecordPath(fbdo, recordPath, record, errorDetail, publishResult)) {
        publishResult.ok = true;
        publishResult.path = recordPath;
        publishResult.refId = recordId;
        return true;
    }

    if (parseFirebaseJson(record, doc, errorDetail)) {
        JsonObject retryRoot = doc.as<JsonObject>();
        retryRoot["system_record"]["sync"]["telemetry_persisted"] = false;
        setNull(retryRoot["system_record"]["sync"]["telemetry_record_path"]);
        saveFirebaseJson(record, doc, errorDetail);
    }
    return false;
}

bool RawTelemetryReporter::probePublishPath(FirebaseData &fbdo,
                                            String *outProbePath,
                                            String &errorDetail) {
    String probePath = APP_RTDB_PATH_NODE_TELEMETRY_PROBE;
    if (outProbePath) {
        *outProbePath = probePath;
    }

#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    RtdbRestResponse response;
    bool ok = rtdbRestClient().putRawJson(probePath, String(static_cast<unsigned long>(millis() / 1000UL)), response, true);
    if (!ok) {
        errorDetail = response.detail.length() ? response.detail : "rtdb_probe_write_fail";
    }
    return ok;
#else
    if (!Firebase.setInt(fbdo, probePath, static_cast<int>(millis() / 1000UL))) {
        errorDetail = fbdo.errorReason();
        return false;
    }
    return true;
#endif
}
