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

bool isUsefulOperator(const String &operatorName) {
    String value = operatorName;
    value.trim();
    return value.length() > 0 &&
           value.indexOf("ERROR") < 0 &&
           value.indexOf("+COPS:") < 0;
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
    (void)seqNo;
    // Keep the event key identical to Node1/Layer0: one numeric sample
    // timestamp under the local date bucket. The sequence remains in the
    // record identity for diagnostics and future collision analysis.
    return String((unsigned long)tsSample);
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

bool classifyRtdbJsonBody(const String &rawBody,
                          bool &exists,
                          String &errorDetail) {
    String body = rawBody;
    body.trim();
    if (!body.length()) {
        errorDetail = "rtdb_get_empty_body";
        return false;
    }

    JsonDocument doc;
    DeserializationError parseError = deserializeJson(doc, body);
    if (parseError != DeserializationError::Ok) {
        errorDetail = "rtdb_get_invalid_json_body";
        return false;
    }

    // RTDB returns the JSON literal null for a valid GET of a missing path.
    // Any valid JSON value other than null means the path has content.
    exists = !doc.as<JsonVariantConst>().isNull();
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

    if (publishResult) {
        publishResult->transportOk = response.transportOk;
        publishResult->responseReceived = response.responseReceived;
        publishResult->httpStatus = response.statusCode;
        publishResult->stage = response.stage;
        publishResult->detail = response.detail;
    }
    if (!classifyRtdbJsonBody(response.body, exists, errorDetail)) {
        if (publishResult) {
            publishResult->stage = errorDetail;
            publishResult->detail = errorDetail;
        }
        return false;
    }
    CUS_DBGF("[FIREBASE][TELEMETRY] existing path=%s exists=%d body_bytes=%u http=%d\n",
             path.c_str(),
             exists ? 1 : 0,
             (unsigned)response.body.length(),
             response.statusCode);
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

    if (publishResult) {
        publishResult->httpStatus = fbdo.httpCode();
        publishResult->stage = "firebase_get_ok";
        publishResult->detail = "ok";
    }
    String body = fbdo.jsonString();
    if (!classifyRtdbJsonBody(body, exists, errorDetail)) {
        if (publishResult) {
            publishResult->stage = errorDetail;
            publishResult->detail = errorDetail;
        }
        return false;
    }
    CUS_DBGF("[FIREBASE][TELEMETRY] existing path=%s exists=%d body_bytes=%u http=%d\n",
             path.c_str(),
             exists ? 1 : 0,
             (unsigned)body.length(),
             fbdo.httpCode());
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
    readStatus["value_valid"] = shtPayload["sht_value_valid"] | sampleValid;
    readStatus["values_available"] = shtPayload["sht_values_available"] | sampleValid;
    readStatus["values_recorded_with_error"] =
        (shtPayload["sht_values_available"] | sampleValid) && !sampleValid;
    readStatus["error_code"] = String(shtPayload["sht_error"] | "");
    readStatus["retry_count"] = shtPayload["sht_retry_count"] | 0;
    readStatus["read_elapsed_ms"] = shtPayload["sht_read_elapsed_ms"] | 0;
    readStatus["invalid_streak"] = shtPayload["sht_invalid_streak"] | 0;
    readStatus["i2c_address_ack"] = shtPayload["sht_i2c_address_ack"] | false;
    readStatus["i2c_error"] = shtPayload["sht_i2c_error"] | 255;
    const bool keepShtDiagnostics = !sampleValid || !(shtPayload["sht_read_ok"] | false);
    if (keepShtDiagnostics) {
        readStatus["init_attempts"] = shtPayload["sht_init_attempts"] | 0;
        readStatus["init_error"] = String(shtPayload["sht_init_error"] | "not_attempted");
        readStatus["init_probe_read_ok"] = shtPayload["sht_init_probe_read_ok"] | false;
        readStatus["frame_ok"] = shtPayload["sht_frame_ok"] | false;
        readStatus["temp_crc_ok"] = shtPayload["sht_temp_crc_ok"] | false;
        readStatus["hum_crc_ok"] = shtPayload["sht_hum_crc_ok"] | false;
        readStatus["received_bytes"] = shtPayload["sht_received_bytes"] | 0;
        readStatus["raw_values_available"] = shtPayload["sht_raw_values_available"] | false;
        readStatus["raw_temp"] = shtPayload["sht_raw_temp"];
        readStatus["raw_hum"] = shtPayload["sht_raw_hum"];
        if (!shtPayload["sht_observed_temp_c"].isNull()) {
            readStatus["observed_temp_c"] = shtPayload["sht_observed_temp_c"];
        } else {
            setNull(readStatus["observed_temp_c"]);
        }
        if (!shtPayload["sht_observed_hum_pct"].isNull()) {
            readStatus["observed_hum_pct"] = shtPayload["sht_observed_hum_pct"];
        } else {
            setNull(readStatus["observed_hum_pct"]);
        }
        if (!shtPayload["sht_init_probe_temp_c"].isNull()) {
            readStatus["init_probe_temp_c"] = shtPayload["sht_init_probe_temp_c"];
        }
        if (!shtPayload["sht_init_probe_hum_pct"].isNull()) {
            readStatus["init_probe_hum_pct"] = shtPayload["sht_init_probe_hum_pct"];
        }
    }
}

bool diagnosticFieldIsValid(JsonObjectConst valueValidity,
                            JsonObjectConst protocolValidity,
                            const char *field) {
    // New NPK payloads distinguish a valid Modbus frame from a plausible
    // measurement. Keep the old protocol map as a backward-compatible
    // fallback for payloads produced by older firmware.
    if (!valueValidity.isNull()) {
        return valueValidity[field] | false;
    }
    return protocolValidity[field] | false;
}

bool diagnosticFieldShouldInclude(JsonObjectConst valueValidity,
                                   JsonObjectConst protocolValidity,
                                   JsonObjectConst defaultedZero,
                                   const char *field) {
    // A configured zero for an unsupported field is intentionally serialized,
    // but remains false in field_value_validity so consumers can distinguish a
    // policy default from an observed measurement.
    return diagnosticFieldIsValid(valueValidity, protocolValidity, field) ||
           (defaultedZero[field] | false);
}

bool payloadFieldBool(JsonObjectConst payload,
                      const char *scalarKey,
                      const char *objectKey,
                      const char *fieldKey,
                      bool fallback) {
    JsonVariantConst scalar = payload[scalarKey];
    if (!scalar.isNull()) {
        return scalar | false;
    }
    JsonObjectConst nested = payload[objectKey];
    if (!nested.isNull() && !nested[fieldKey].isNull()) {
        return nested[fieldKey] | false;
    }
    return fallback;
}

String payloadFieldString(JsonObjectConst payload,
                          const char *scalarKey,
                          const char *objectKey,
                          const char *fieldKey) {
    JsonVariantConst scalar = payload[scalarKey];
    if (!scalar.isNull()) {
        return String(scalar.as<const char *>() ? scalar.as<const char *>() : "");
    }
    JsonObjectConst nested = payload[objectKey];
    if (!nested.isNull() && !nested[fieldKey].isNull()) {
        return String(nested[fieldKey].as<const char *>() ? nested[fieldKey].as<const char *>() : "");
    }
    return "";
}

void copyPayloadField(JsonObject destination,
                      const char *destinationKey,
                      JsonObjectConst payload,
                      const char *scalarKey,
                      const char *objectKey,
                      const char *fieldKey) {
    JsonVariantConst scalar = payload[scalarKey];
    if (!scalar.isNull()) {
        destination[destinationKey] = scalar;
        return;
    }
    JsonObjectConst nested = payload[objectKey];
    if (!nested.isNull() && !nested[fieldKey].isNull()) {
        destination[destinationKey] = nested[fieldKey];
    }
}

void populateSoilRecord(JsonObject sensorRecord,
                        JsonObjectConst npkPayload,
                        bool includePartialSensorValues) {
    JsonObject soil = sensorRecord[APP_SENSOR_ID_SOIL_7IN1].to<JsonObject>();
    soil["sensor_type"] = APP_SENSOR_TYPE_SOIL_7IN1;

    JsonObject values = soil["values"].to<JsonObject>();
    bool sampleValid = npkPayload["npk_values_valid"] | false;
    JsonObjectConst fieldValidity = npkPayload["field_validity"];
    JsonObjectConst valueValidity = npkPayload["field_value_validity"];
    JsonObjectConst defaultedZero = npkPayload["field_defaulted_zero"];
    const bool tempValid = payloadFieldBool(
        npkPayload, "temp_value_valid", "field_value_validity", "temp", !npkPayload["temp"].isNull());
    const bool humValid = payloadFieldBool(
        npkPayload, "hum_value_valid", "field_value_validity", "hum", !npkPayload["hum"].isNull());
    const bool phValid = payloadFieldBool(
        npkPayload, "ph_value_valid", "field_value_validity", "ph", !npkPayload["ph"].isNull());
    const bool ecValid = payloadFieldBool(
        npkPayload, "ec_value_valid", "field_value_validity", "ec", !npkPayload["ec"].isNull());
    const bool nValid = payloadFieldBool(
        npkPayload, "N_value_valid", "field_value_validity", "N", !npkPayload["N"].isNull());
    const bool pValid = payloadFieldBool(
        npkPayload, "P_value_valid", "field_value_validity", "P", !npkPayload["P"].isNull());
    const bool kValid = payloadFieldBool(
        npkPayload, "K_value_valid", "field_value_validity", "K", !npkPayload["K"].isNull());
    const bool tempDefaulted = payloadFieldBool(
        npkPayload, "temp_defaulted_zero", "field_defaulted_zero", "temp", false);
    const bool humDefaulted = payloadFieldBool(
        npkPayload, "hum_defaulted_zero", "field_defaulted_zero", "hum", false);
    if (sampleValid) {
        values["soil_temp_c"] = npkPayload["temp"];
        values["soil_moisture_pct"] = npkPayload["hum"];
        values["soil_ph"] = npkPayload["ph"];
        values["soil_ec_us_cm"] = npkPayload["ec"];
        values["soil_n_proxy"] = npkPayload["N"];
        values["soil_p_proxy"] = npkPayload["P"];
        values["soil_k_proxy"] = npkPayload["K"];
    } else if (includePartialSensorValues) {
        // Diagnostic records may expose confirmed fields; the only missing
        // fields allowed through here are the explicit sparse zero defaults.
        if (tempValid || tempDefaulted || diagnosticFieldShouldInclude(valueValidity, fieldValidity, defaultedZero, "temp")) {
            values["soil_temp_c"] = npkPayload["temp"];
        } else {
            setNull(values["soil_temp_c"]);
        }
        if (humValid || humDefaulted || diagnosticFieldShouldInclude(valueValidity, fieldValidity, defaultedZero, "hum")) {
            values["soil_moisture_pct"] = npkPayload["hum"];
        } else {
            setNull(values["soil_moisture_pct"]);
        }
        if (phValid || diagnosticFieldIsValid(valueValidity, fieldValidity, "ph")) {
            values["soil_ph"] = npkPayload["ph"];
        } else {
            setNull(values["soil_ph"]);
        }
        if (ecValid || diagnosticFieldIsValid(valueValidity, fieldValidity, "ec")) {
            values["soil_ec_us_cm"] = npkPayload["ec"];
        } else {
            setNull(values["soil_ec_us_cm"]);
        }
        if (nValid || diagnosticFieldIsValid(valueValidity, fieldValidity, "N")) {
            values["soil_n_proxy"] = npkPayload["N"];
        } else {
            setNull(values["soil_n_proxy"]);
        }
        if (pValid || diagnosticFieldIsValid(valueValidity, fieldValidity, "P")) {
            values["soil_p_proxy"] = npkPayload["P"];
        } else {
            setNull(values["soil_p_proxy"]);
        }
        if (kValid || diagnosticFieldIsValid(valueValidity, fieldValidity, "K")) {
            values["soil_k_proxy"] = npkPayload["K"];
        } else {
            setNull(values["soil_k_proxy"]);
        }
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
    readStatus["partial_values_included"] = includePartialSensorValues && !sampleValid;
    readStatus["soil_temp_valid"] = tempValid && !tempDefaulted;
    readStatus["soil_temp_source"] = payloadFieldString(npkPayload, "temp_source", "field_source", "temp");
    readStatus["soil_moisture_valid"] = humValid && !humDefaulted;
    readStatus["soil_moisture_source"] = payloadFieldString(npkPayload, "hum_source", "field_source", "hum");
    readStatus["ph_protocol_ok"] = payloadFieldBool(npkPayload, "ph_protocol_ok", "field_validity", "ph", false);
    readStatus["ph_valid"] = phValid;
    readStatus["ph_state"] = npkPayload["ph_state"] | "unknown";
    readStatus["ec_valid"] = ecValid;
    readStatus["ec_source"] = payloadFieldString(npkPayload, "ec_source", "field_source", "ec");
    readStatus["ec_measurement_kind"] = npkPayload["ec_measurement_kind"] | "legacy_unknown";
    readStatus["n_proxy_valid"] = nValid;
    readStatus["p_proxy_valid"] = pValid;
    readStatus["k_proxy_valid"] = kValid;
    copyPayloadField(readStatus, "soil_moisture_calibration_status", npkPayload, "hum_calibration_status", "moisture_calibration", "status");
    copyPayloadField(readStatus, "soil_moisture_calibration_profile", npkPayload, "hum_calibration_profile", "moisture_calibration", "profile");
    copyPayloadField(readStatus, "soil_moisture_value_semantics", npkPayload, "hum_value_semantics", "moisture_calibration", "value_semantics");
    copyPayloadField(readStatus, "soil_moisture_raw_adc", npkPayload, "hum_raw_adc", "moisture_calibration", "latest_raw_adc");
    copyPayloadField(readStatus, "soil_moisture_voltage_mv", npkPayload, "hum_voltage_mv", "moisture_calibration", "latest_voltage_mv");
    copyPayloadField(readStatus, "soil_moisture_install_depth_cm_min", npkPayload, "hum_install_depth_cm_min", "moisture_calibration", "install_depth_cm_min");
    copyPayloadField(readStatus, "soil_moisture_install_depth_cm_max", npkPayload, "hum_install_depth_cm_max", "moisture_calibration", "install_depth_cm_max");
    if (!sampleValid || !(npkPayload["read_ok"] | false)) {
        if (!fieldValidity.isNull()) readStatus["field_validity"] = fieldValidity;
        if (!valueValidity.isNull()) readStatus["field_value_validity"] = valueValidity;
        if (!npkPayload["field_source"].isNull()) readStatus["field_source"] = npkPayload["field_source"];
        if (!defaultedZero.isNull()) readStatus["field_defaulted_zero"] = defaultedZero;
        if (!npkPayload["raw_registers"].isNull()) readStatus["raw_registers"] = npkPayload["raw_registers"];
        if (!npkPayload["map_diagnostics"].isNull()) readStatus["map_diagnostics"] = npkPayload["map_diagnostics"];
    }
    readStatus["read_map"] = npkPayload["read_map"] | "unknown";
}

void populateNetworkRecord(JsonObject network) {
#if USE_SIM_NETWORK
    SimNetworkState sim = simReadNetworkState(false);
    bool signalValid = sim.signalCsq >= 0 && sim.signalCsq != 99;
    bool operatorValid = isUsefulOperator(sim.operatorName);
    network["registered"] = sim.networkRegistered;
    network["attached"] = sim.packetAttached;
    network["pdp_active"] = sim.gprsConnected;
    network["operator_valid"] = operatorValid;
    if (operatorValid) {
        network["operator"] = sim.operatorName;
    } else {
        setNull(network["operator"]);
    }
    setNull(network["rat"]);
    network["signal_dbm"] = sim.signalDbm;
    network["signal_csq"] = sim.signalCsq;
    network["signal_valid"] = signalValid;
    network["ip_valid"] = sim.localIpValid;
    network["local_ip_valid"] = sim.localIpValid;
    if (sim.localIpValid) {
        network["local_ip"] = sim.localIp;
        network["local_ip_source"] = sim.localIpSource;
    } else {
        setNull(network["local_ip"]);
        setNull(network["local_ip_source"]);
    }
#else
    bool connected = networkIsConnected();
    String localIp = networkLocalIp();
    bool ipValid = localIp.length() > 0 && localIp != "0.0.0.0";
    int signalDbm = networkSignalDbm();
    network["registered"] = connected;
    network["attached"] = connected;
    network["pdp_active"] = connected;
    network["operator_valid"] = false;
    setNull(network["operator"]);
    setNull(network["rat"]);
    network["signal_dbm"] = signalDbm;
    setNull(network["signal_csq"]);
    network["signal_valid"] = signalDbm != 0;
    network["ip_valid"] = ipValid;
    network["local_ip_valid"] = ipValid;
    if (ipValid) {
        network["local_ip"] = localIp;
        network["local_ip_source"] = "wifi.localIP";
    } else {
        setNull(network["local_ip"]);
        setNull(network["local_ip_source"]);
    }
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
    populateSoilRecord(sensorRecord, npkPayload, ctx.includePartialSensorValues);

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
    cycle["cycle_duration_ms"] = (npkPayload["read_duration_ms"] | 0) +
                                   (shtPayload["sht_read_elapsed_ms"] | 0);
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
        CUS_DBGF("[FIREBASE][TELEMETRY] reject ts=%lu seq=%lu stage=%s detail=%s\n",
                 (unsigned long)tsSample,
                 (unsigned long)seqNo,
                 publishResult.stage.c_str(),
                 publishResult.detail.c_str());
        return false;
    }

    CUS_DBGF("[FIREBASE][TELEMETRY] check path=%s ts=%lu seq=%lu\n",
             recordPath.c_str(),
             (unsigned long)tsSample,
             (unsigned long)seqNo);

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
        CUS_DBGF("[FIREBASE][TELEMETRY] check FAIL path=%s http=%d stage=%s detail=%s\n",
                 recordPath.c_str(),
                 publishResult.httpStatus,
                 publishResult.stage.c_str(),
                 errorDetail.c_str());
        return false;
    }

    if (exists) {
        record.set("system_record/sync/last_error_code", "duplicate_key");
        publishResult.duplicate = true;
        publishResult.stage = "duplicate_key";
        publishResult.detail = "telemetry_record_exists";
        errorDetail = publishResult.detail;
        CUS_DBGF("[FIREBASE][TELEMETRY] DUPLICATE path=%s http=%d\n",
                 recordPath.c_str(),
                 publishResult.httpStatus);
        return false;
    }

    if (writeRecordPath(fbdo, recordPath, record, errorDetail, publishResult)) {
        publishResult.ok = true;
        publishResult.path = recordPath;
        publishResult.refId = recordId;
        CUS_DBGF("[FIREBASE][TELEMETRY] WRITE OK path=%s http=%d stage=%s\n",
                 recordPath.c_str(),
                 publishResult.httpStatus,
                 publishResult.stage.c_str());
        return true;
    }

    CUS_DBGF("[FIREBASE][TELEMETRY] WRITE FAIL path=%s http=%d stage=%s detail=%s\n",
             recordPath.c_str(),
             publishResult.httpStatus,
             publishResult.stage.c_str(),
             errorDetail.c_str());

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
