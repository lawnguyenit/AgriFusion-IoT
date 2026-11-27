#if 0

#include <Arduino.h>
#include <ArduinoJson.h>
#include <time.h>

#include "Config.h"
#include "DeviceContext.h"
#include "NPK.h"
#include "NpkMatrixTest.h"
#include "NetworkBridge.h"
#include "RawTelemetryReporter.h"
#include "RtdbRestClient.h"

// -----------------------------------------------------------------------------
// Temporary Node2 NPK payload-fit test.
//
// This entry point deliberately bypasses AppEntry/AppRuntime. It repeatedly
// reads the phase-1 map first and falls back to the confirmed sparse map in
// short debug cycles, prints every field and its protocol/value evidence, then optionally sends one canonical record to a
// debug-only RTDB path. It never writes Node2's production telemetry/latest
// paths and does not run a separate SIM diagnostic test.
// -----------------------------------------------------------------------------

namespace {
HardwareSerial gNpkSerial(1);
MyNPK gNpk;
NpkMatrixTest gNpkMatrix(gNpkSerial);
DeviceContext gDeviceContext;
RawTelemetryReporter gRawReporter(APP_RTDB_PATH_NODE_ROOT);

constexpr uint8_t NPK_TEST_READS_PER_CYCLE = APP_SENSOR_RETRY_WINDOW_COUNT;
constexpr uint32_t NPK_TEST_RETRY_INTERVAL_MS = APP_SENSOR_RETRY_WINDOW_MS;
constexpr uint32_t NPK_TEST_CYCLE_GAP_MS = 5000UL;

NPK_Data gSamples[NPK_TEST_READS_PER_CYCLE] = {};
uint8_t gSampleCount = 0;
bool gSamplesReady = false;
bool gUploadTransportReady = false;
bool gTestUploadDone = false;
bool gUploadAttempted = false;
bool gAutoCycle = true;
uint32_t gCycleNo = 0;
uint32_t gLastCycleEndMs = 0;

void setNull(JsonVariant value) {
    value.set(nullptr);
}

void copyJsonObject(JsonObject dst, JsonObjectConst src) {
    for (JsonPairConst pair : src) {
        dst[pair.key().c_str()] = pair.value();
    }
}

uint32_t currentEpochSec() {
    time_t now = time(nullptr);
    return now >= 1700000000 ? static_cast<uint32_t>(now) : 0U;
}

uint8_t validFieldCount(const NPK_Data &data) {
    return static_cast<uint8_t>(data.tempReadOk + data.humReadOk + data.phReadOk +
                                (data.ecReadOk || data.ecDerivedFromNpk) + data.nReadOk + data.pReadOk +
                                data.kReadOk);
}

uint8_t validValueFieldCount(const NPK_Data &data) {
    return static_cast<uint8_t>(data.tempValueValid + data.humValueValid +
                                data.phValueValid + data.ecValueValid +
                                data.nValueValid + data.pValueValid +
                                data.kValueValid);
}

void printHelp() {
    CUS_DBGLN("[NPK][TEST] Commands: a=toggle auto cycles, c=run cycle, r=read once, u=upload latest, m=read-only matrix, ?=help");
    CUS_DBGLN("[NPK][TEST] Each cycle has 3 sequential reads; retry delay follows APP_SENSOR_RETRY_WINDOW_MS.");
    CUS_DBGLN("[NPK][TEST] Matrix checks soil humidity/temp/EC/pH/N/P/K at candidate maps and FC03/FC04 using confirmed 9600 8N1; read-only.");
    CUS_DBGLN("[NPK][TEST] SIM is not diagnosed here; optional Firebase upload uses the existing stable SIM path.");
    CUS_DBGLN("[NPK][TEST] Firebase PUT is attempted automatically once and is limited to the debug path.");
}

void printConfiguration() {
    CUS_DBGLN("[NPK][TEST] ===== ACTIVE TEST CONFIG =====");
    CUS_DBGF("[NPK][TEST] UART=HardwareSerial(1) baud=%lu data=8N1 rx=%d tx=%d slave=%u func=0x03\n",
             static_cast<unsigned long>(NPK_BAUDRATE),
             NPK_RX_PIN,
             NPK_TX_PIN,
             static_cast<unsigned>(NPK_MODBUS_SLAVE_ID));
    CUS_DBGF("[NPK][TEST] confirmed_map=ph:0x%04X/1 npk:0x%04X/%u\n",
             static_cast<unsigned>(NPK_REG_PH),
             static_cast<unsigned>(NPK_REG_NPK),
             static_cast<unsigned>(NPK_REG_NPK_COUNT));
    CUS_DBGF("[NPK][TEST] unsupported_soil_climate_as_zero=%d (temp/hum are policy defaults, not Modbus frames)\n",
             NPK_UNSUPPORTED_SOIL_CLIMATE_AS_ZERO);
    CUS_DBGF("[NPK][TEST] phase1_probe=enabled start:0x%04X count:%u decode=hum:r0/10,temp:r1/10,ec:r2,ph:r3/10,NPK:r4..r6 fallback=sparse\n",
             static_cast<unsigned>(NPK_LEGACY_FULL_MAP_START),
             static_cast<unsigned>(NPK_LEGACY_FULL_MAP_COUNT));
    CUS_DBGF("[NPK][TEST] cycle_reads=%u retry_interval_ms=%lu cycle_gap_ms=%lu\n",
             static_cast<unsigned>(NPK_TEST_READS_PER_CYCLE),
             static_cast<unsigned long>(NPK_TEST_RETRY_INTERVAL_MS),
             static_cast<unsigned long>(NPK_TEST_CYCLE_GAP_MS));
    CUS_DBGF("[NPK][TEST] canonical_domains=sensor_record/sim_record/system_record\n");
    CUS_DBGF("[NPK][TEST] firebase_test_path=%s\n", APP_RTDB_PATH_NODE_NPK_TEST);
    CUS_DBGF("[NPK][TEST] SHT30=skipped_for_npk_test (pins/config unchanged: SDA=%d SCL=%d addr=0x%02X)\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             SHT30_I2C_ADDR);
    CUS_DBGLN("[NPK][TEST] ================================");
}

void printFieldValue(const char *name,
                    bool protocolOk,
                    bool valueValid,
                    bool defaultedZero,
                    float value) {
    if (defaultedZero) {
        CUS_DBGF(" %s=%.3f(default_unsupported_zero)", name, static_cast<double>(value));
    } else if (!protocolOk) {
        CUS_DBGF(" %s=null(no_frame)", name);
    } else if (valueValid) {
        CUS_DBGF(" %s=%.3f", name, static_cast<double>(value));
    } else {
        CUS_DBGF(" %s=%.3f(invalid_value)", name, static_cast<double>(value));
    }
}

void printFieldValue(const char *name,
                    bool protocolOk,
                    bool valueValid,
                    bool defaultedZero,
                    int value) {
    if (defaultedZero) {
        CUS_DBGF(" %s=%d(default_unsupported_zero)", name, value);
    } else if (!protocolOk) {
        CUS_DBGF(" %s=null(no_frame)", name);
    } else if (valueValid) {
        CUS_DBGF(" %s=%d", name, value);
    } else {
        CUS_DBGF(" %s=%d(invalid_value)", name, value);
    }
}

void printNpkSample(const NPK_Data &data, uint8_t sampleNo, const char *reason) {
    String json = gNpk.makeJsonFromData(data,
                                        0U,
                                        data.readOk ? 0U : 1U,
                                        false,
                                        0U,
                                        false);

    CUS_DBGF("[NPK][TEST] sample=%u reason=%s map=%s read_ok=%d error=%d status=0x%02X(%s) retries=%u timeout_ms=%lu duration_ms=%lu crc_ok=%d frame_ok=%d protocol_fields=%u/7 value_fields=%u/7\n",
             static_cast<unsigned>(sampleNo),
             reason ? reason : "unknown",
             MyNPK::readMapToString(data.readMap),
             data.readOk ? 1 : 0,
             data.error ? 1 : 0,
             static_cast<unsigned>(data.errorCodeRaw),
             MyNPK::errorCodeToString(data.errorCodeRaw),
             static_cast<unsigned>(data.retryCount),
             static_cast<unsigned long>(data.timeoutMs),
             static_cast<unsigned long>(data.readDurationMs),
             data.crcOk ? 1 : 0,
             data.frameOk ? 1 : 0,
             static_cast<unsigned>(validFieldCount(data)),
             static_cast<unsigned>(validValueFieldCount(data)));

    CUS_DBGF("[NPK][TEST] values:");
    printFieldValue("temp", data.tempReadOk, data.tempValueValid, data.tempDefaultedToZero, data.temp);
    printFieldValue("hum", data.humReadOk, data.humValueValid, data.humDefaultedToZero, data.hum);
    printFieldValue("ph", data.phReadOk, data.phValueValid, false, data.ph);
    printFieldValue("ec", data.ecReadOk || data.ecDerivedFromNpk, data.ecValueValid, false, data.ec);
    printFieldValue("N", data.nReadOk, data.nValueValid, false, data.n);
    printFieldValue("P", data.pReadOk, data.pValueValid, false, data.p);
    printFieldValue("K", data.kReadOk, data.kValueValid, false, data.k);
    CUS_DBGLN("");
    CUS_DBGF("[NPK][TEST] map_status: legacy=0x%02X(%s)/attempts=%u ph=0x%02X(%s)/attempts=%u npk=0x%02X(%s)/attempts=%u\n",
             static_cast<unsigned>(data.legacyBlockStatus),
             MyNPK::errorCodeToString(data.legacyBlockStatus),
             static_cast<unsigned>(data.legacyBlockAttempts),
             static_cast<unsigned>(data.phStatus),
             MyNPK::errorCodeToString(data.phStatus),
             static_cast<unsigned>(data.phAttempts),
             static_cast<unsigned>(data.npkStatus),
             MyNPK::errorCodeToString(data.npkStatus),
             static_cast<unsigned>(data.npkAttempts));
    CUS_DBGF("[NPK][TEST] values_registers: hum=0x%04X temp=0x%04X ec=%d ph=0x%04X N=0x%04X P=0x%04X K=0x%04X\n",
             data.rawHum, data.rawTemp, data.ec, data.rawPh,
             data.rawN, data.rawP, data.rawK);
    CUS_DBGF("[NPK][TEST] field_validity: temp=%d hum=%d ph=%d ec=%d N=%d P=%d K=%d\n",
             data.tempReadOk ? 1 : 0,
             data.humReadOk ? 1 : 0,
             data.phReadOk ? 1 : 0,
             (data.ecReadOk || data.ecDerivedFromNpk) ? 1 : 0,
             data.nReadOk ? 1 : 0,
             data.pReadOk ? 1 : 0,
             data.kReadOk ? 1 : 0);
    CUS_DBGF("[NPK][TEST] field_value_validity: temp=%d hum=%d ph=%d ec=%d N=%d P=%d K=%d ph_state=%s temp_source=%s hum_source=%s\n",
             data.tempValueValid ? 1 : 0,
             data.humValueValid ? 1 : 0,
             data.phValueValid ? 1 : 0,
             data.ecValueValid ? 1 : 0,
             data.nValueValid ? 1 : 0,
             data.pValueValid ? 1 : 0,
             data.kValueValid ? 1 : 0,
             !data.phReadOk ? "no_response" : (data.phValueValid ? "valid" : "frame_ok_value_invalid"),
             data.tempDefaultedToZero ? "unsupported_default_zero" : (data.tempReadOk ? "modbus_register" : "unavailable"),
             data.humDefaultedToZero ? "unsupported_default_zero" : (data.humReadOk ? "modbus_register" : "unavailable"));
    CUS_DBGF("[NPK][TEST] library_json=%s\n", json.c_str());
}

void collectNpkCycle() {
    ++gCycleNo;
    CUS_DBGF("\n[NPK][TEST] ===== CYCLE %lu START reads=%u =====\n",
             static_cast<unsigned long>(gCycleNo),
             static_cast<unsigned>(NPK_TEST_READS_PER_CYCLE));
    gSampleCount = 0;
    gSamplesReady = false;
    for (uint8_t i = 0; i < NPK_TEST_READS_PER_CYCLE; ++i) {
        CUS_DBGF("[NPK][TEST] cycle=%lu attempt=%u/%u READ START\n",
                 static_cast<unsigned long>(gCycleNo),
                 static_cast<unsigned>(i + 1U),
                 static_cast<unsigned>(NPK_TEST_READS_PER_CYCLE));
        gSamples[gSampleCount] = gNpk.read();
        printNpkSample(gSamples[gSampleCount], static_cast<uint8_t>(i + 1U), "cycle_retry");
        ++gSampleCount;
        if (i + 1U < NPK_TEST_READS_PER_CYCLE) {
            CUS_DBGF("[NPK][TEST] cycle=%lu next_attempt_delay_ms=%lu\n",
                     static_cast<unsigned long>(gCycleNo),
                     static_cast<unsigned long>(NPK_TEST_RETRY_INTERVAL_MS));
            delay(NPK_TEST_RETRY_INTERVAL_MS);
        }
    }
    gSamplesReady = true;
    gLastCycleEndMs = millis();
    CUS_DBGF("[NPK][TEST] ===== CYCLE %lu END attempts=%u =====\n",
             static_cast<unsigned long>(gCycleNo),
             static_cast<unsigned>(gSampleCount));
}

const NPK_Data &bestSample() {
    uint8_t bestIndex = 0;
    for (uint8_t i = 1; i < gSampleCount; ++i) {
        // Prefer a complete protocol read, then the most semantically valid
        // fields, then the later sample when equally good.
        if ((gSamples[i].readOk && !gSamples[bestIndex].readOk) ||
            (gSamples[i].readOk == gSamples[bestIndex].readOk &&
             validValueFieldCount(gSamples[i]) >= validValueFieldCount(gSamples[bestIndex]))) {
            bestIndex = i;
        }
    }
    return gSamples[bestIndex];
}

bool prepareUploadTransport() {
    if (gUploadTransportReady) {
        return true;
    }

    CUS_DBGLN("\n[NPK][TEST] Preparing existing SIM path for optional Firebase upload (no SIM diagnostic cycle).");
    bool setupOk = networkSetup();
    CUS_DBGF("[NPK][TEST] upload_transport_ready=%d transport=%s status=%d ip=%s rssi=%d\n",
             setupOk ? 1 : 0,
             networkTransportName(),
             networkStatusCode(),
             networkLocalIp().c_str(),
             networkSignalDbm());
    gUploadTransportReady = setupOk && networkIsConnected();
    if (!gUploadTransportReady) {
        CUS_DBGLN("[NPK][TEST] Existing SIM path is not ready; NPK cycles continue locally.");
    }
    return gUploadTransportReady;
}

String buildSensorPacket(const NPK_Data &data, uint32_t epochSec) {
    String npkJson = gNpk.makeJsonFromData(data,
                                           0U,
                                           data.readOk ? 0U : 1U,
                                           false,
                                           0U,
                                           false);

    JsonDocument npkDoc;
    JsonDocument packetDoc;
    JsonObject packet = packetDoc["packet"].to<JsonObject>();
    JsonObject npkOut = packet["npk_data"].to<JsonObject>();
    if (deserializeJson(npkDoc, npkJson) == DeserializationError::Ok) {
        copyJsonObject(npkOut, npkDoc.as<JsonObjectConst>());
    } else {
        npkOut["read_ok"] = false;
        npkOut["error_code"] = "npk_json_parse_fail";
    }

    JsonObject shtOut = packet["sht30_data"].to<JsonObject>();
    shtOut["sht_read_ok"] = false;
    shtOut["sht_sample_valid"] = false;
    shtOut["sht_error"] = "skipped_for_npk_test";
    shtOut["sht_retry_count"] = 0;
    shtOut["sht_read_elapsed_ms"] = 0;
    shtOut["sht_invalid_streak"] = 0;

    JsonObject systemOut = packet["system_data"].to<JsonObject>();
    systemOut["sample_epoch_sec"] = static_cast<unsigned long>(epochSec);
    systemOut["sample_time_valid"] = epochSec >= 1700000000UL;
    systemOut["sample_slot_no"] = 0;
    systemOut["sample_slot_count_day"] = static_cast<unsigned long>(APP_TELEMETRY_SEQUENCE_SLOTS_PER_DAY);
    systemOut["sample_date_key"] = epochSec >= 1700000000UL ? "network_time" : "unsynced";

    String packetJson;
    serializeJson(packetDoc, packetJson);
    return packetJson;
}

RawTelemetryRecordContext makeRecordContext(const NPK_Data &data) {
    RawTelemetryRecordContext ctx;
    gDeviceContext.begin();
    ctx.deviceId = gDeviceContext.deviceId();
    ctx.bootId = gDeviceContext.bootId();
    ctx.firmwareVersion = String("npk_payload_fit_") + __DATE__ + "_" + __TIME__;
    ctx.runningPartition = "test";
    ctx.wakeReason = gDeviceContext.wakeReason();
    ctx.recordType = data.readOk ? "sensor_sample" : "sensor_fault";
    ctx.payloadKind = "npk_test";
    ctx.seq = gDeviceContext.nextSeq();
    ctx.tsDeviceMs = millis();
    ctx.resetReason = gDeviceContext.resetReason();
    ctx.wifiStatus = networkStatusCode();
    ctx.rssi = networkSignalDbm();
    ctx.hasInternet = gUploadTransportReady;
    ctx.sensorError = !data.readOk;
    ctx.retryCount = data.retryCount;
    ctx.timeoutMs = data.timeoutMs;
    // This is deliberately enabled only for this diagnostic record. Production
    // records still require a complete, validated sensor sample before values
    // are mapped into sensor_record.values.
    ctx.includePartialSensorValues = true;
    return ctx;
}

void putValueOrNull(JsonObject object,
                    const char *key,
                    bool valid,
                    float value) {
    if (valid) {
        object[key] = value;
    } else {
        setNull(object[key]);
    }
}

void putValueOrNull(JsonObject object,
                    const char *key,
                    bool valid,
                    int value) {
    if (valid) {
        object[key] = value;
    } else {
        setNull(object[key]);
    }
}

void appendTestObservations(FirebaseJson &record) {
    JsonDocument doc;
    String existing;
    record.toString(existing, false);
    if (deserializeJson(doc, existing) != DeserializationError::Ok) {
        CUS_DBGLN("[NPK][TEST] Cannot append test observations: canonical JSON parse failed.");
        return;
    }

    JsonObject root = doc.as<JsonObject>();
    JsonObject context = root["test_context"].to<JsonObject>();
    context["test_name"] = "npk_payload_fit";
    context["test_only"] = true;
    context["sht30_skipped"] = true;
    context["canonical_schema"] = "sensor_record/sim_record/system_record";
    context["upload_path"] = APP_RTDB_PATH_NODE_NPK_TEST;
    context["cycle_no"] = static_cast<unsigned long>(gCycleNo);
    context["reads_per_cycle"] = static_cast<unsigned>(NPK_TEST_READS_PER_CYCLE);
    context["retry_interval_ms"] = static_cast<unsigned long>(NPK_TEST_RETRY_INTERVAL_MS);
    context["sample_count"] = static_cast<unsigned>(gSampleCount);
    context["partial_values_policy"] = "confirmed_fields_only";

    JsonArray observations = root["test_observations"].to<JsonArray>();
    for (uint8_t i = 0; i < gSampleCount; ++i) {
        const NPK_Data &data = gSamples[i];
        JsonObject item = observations.add<JsonObject>();
        item["sample_no"] = static_cast<unsigned>(i + 1U);
        item["read_ok"] = data.readOk;
        item["error"] = data.error;
        item["error_code"] = MyNPK::errorCodeToString(data.errorCodeRaw);
        item["error_code_raw"] = data.errorCodeRaw;
        item["retry_count"] = data.retryCount;
        item["timeout_ms"] = static_cast<unsigned long>(data.timeoutMs);
        item["read_duration_ms"] = static_cast<unsigned long>(data.readDurationMs);
        item["crc_ok"] = data.crcOk;
        item["frame_ok"] = data.frameOk;
        // Keep decoded values in test_observations when the frame was valid,
        // even if a semantic check rejects them; this is the evidence needed
        // to diagnose pH=0. Canonical sensor_record.values is filtered later
        // by field_value_validity, except for the explicit zero-default policy.
        putValueOrNull(item, "temp", data.tempReadOk || data.tempDefaultedToZero, data.temp);
        putValueOrNull(item, "hum", data.humReadOk || data.humDefaultedToZero, data.hum);
        putValueOrNull(item, "ph", data.phReadOk, data.ph);
        putValueOrNull(item, "ec", data.ecReadOk || data.ecDerivedFromNpk, data.ec);
        putValueOrNull(item, "N", data.nReadOk, data.n);
        putValueOrNull(item, "P", data.pReadOk, data.p);
        putValueOrNull(item, "K", data.kReadOk, data.k);
        JsonObject raw = item["raw_registers"].to<JsonObject>();
        if (data.humReadOk) raw["hum"] = data.rawHum; else raw["hum"] = nullptr;
        if (data.tempReadOk) raw["temp"] = data.rawTemp; else raw["temp"] = nullptr;
        if (data.ecReadOk || data.ecDerivedFromNpk) raw["ec"] = data.ec; else raw["ec"] = nullptr;
        if (data.phReadOk) raw["ph"] = data.rawPh; else raw["ph"] = nullptr;
        if (data.nReadOk) raw["N"] = data.rawN; else raw["N"] = nullptr;
        if (data.pReadOk) raw["P"] = data.rawP; else raw["P"] = nullptr;
        if (data.kReadOk) raw["K"] = data.rawK; else raw["K"] = nullptr;
        item["read_map"] = MyNPK::readMapToString(data.readMap);
        item["ph_state"] = !data.phReadOk
                                ? "no_response"
                                : (data.phValueValid ? "valid" : "frame_ok_value_invalid");

        JsonObject validity = item["field_validity"].to<JsonObject>();
        validity["temp"] = data.tempReadOk;
        validity["hum"] = data.humReadOk;
        validity["ph"] = data.phReadOk;
        validity["ec"] = data.ecReadOk || data.ecDerivedFromNpk;
        validity["N"] = data.nReadOk;
        validity["P"] = data.pReadOk;
        validity["K"] = data.kReadOk;

        JsonObject valueValidity = item["field_value_validity"].to<JsonObject>();
        valueValidity["temp"] = data.tempValueValid;
        valueValidity["hum"] = data.humValueValid;
        valueValidity["ph"] = data.phValueValid;
        valueValidity["ec"] = data.ecValueValid;
        valueValidity["N"] = data.nValueValid;
        valueValidity["P"] = data.pValueValid;
        valueValidity["K"] = data.kValueValid;

        JsonObject source = item["field_source"].to<JsonObject>();
        source["temp"] = data.tempDefaultedToZero
                              ? "unsupported_default_zero"
                              : (data.tempReadOk ? "modbus_register" : "unavailable");
        source["hum"] = data.humDefaultedToZero
                             ? "unsupported_default_zero"
                             : (data.humReadOk ? "modbus_register" : "unavailable");
        source["ph"] = data.phReadOk ? "modbus_register" : "unavailable";
        source["N"] = data.nReadOk ? "modbus_register" : "unavailable";
        source["P"] = data.pReadOk ? "modbus_register" : "unavailable";
        source["K"] = data.kReadOk ? "modbus_register" : "unavailable";

        JsonObject defaultedZero = item["field_defaulted_zero"].to<JsonObject>();
        defaultedZero["temp"] = data.tempDefaultedToZero;
        defaultedZero["hum"] = data.humDefaultedToZero;
        defaultedZero["ph"] = false;
        defaultedZero["N"] = false;
        defaultedZero["P"] = false;
        defaultedZero["K"] = false;

        JsonObject map = item["map_diagnostics"].to<JsonObject>();
        map["legacy_read_ok"] = data.legacyBlockReadOk;
        map["legacy_status"] = data.legacyBlockStatus;
        map["legacy_attempts"] = data.legacyBlockAttempts;
        map["ph_status"] = data.phStatus;
        map["ph_attempts"] = data.phAttempts;
        map["npk_status"] = data.npkStatus;
        map["npk_attempts"] = data.npkAttempts;
    }

    String updated;
    serializeJson(doc, updated);
    record.setJsonData(updated);
}

bool uploadCanonicalTestRecord(bool forceRetry) {
    if (gTestUploadDone) {
        CUS_DBGLN("[NPK][TEST] upload_guard=already_successful_this_boot");
        return true;
    }
    if (!gSamplesReady || gSampleCount == 0U) {
        CUS_DBGLN("[NPK][TEST] Upload skipped: no NPK samples.");
        return false;
    }
    if (gUploadAttempted && !forceRetry) {
        CUS_DBGLN("[NPK][TEST] automatic upload already attempted; use command 'u' for an explicit retry.");
        return false;
    }
    gUploadAttempted = true;
    if (!gUploadTransportReady && !prepareUploadTransport()) {
        CUS_DBGLN("[NPK][TEST] Upload skipped: cloud transport is not ready.");
        return false;
    }

    const NPK_Data &selected = bestSample();
    uint32_t epochSec = currentEpochSec();
    if (!epochSec) {
        CUS_DBGLN("[NPK][TEST] WARNING: clock is unsynced; record will use null sample time.");
    }

    String packetJson = buildSensorPacket(selected, epochSec);
    RawTelemetryRecordContext ctx = makeRecordContext(selected);
    FirebaseJson record;
    String errorDetail;
    if (!gRawReporter.buildRecord(packetJson.c_str(), ctx, record, errorDetail)) {
        CUS_DBGF("[NPK][TEST] canonical_build_fail=%s\n", errorDetail.c_str());
        return false;
    }
    appendTestObservations(record);

    String body;
    record.toString(body, false);
    CUS_DBGF("[NPK][TEST] selected_sample_fields=%u/7 selected_read_ok=%d payload_bytes=%u\n",
             static_cast<unsigned>(validFieldCount(selected)),
             selected.readOk ? 1 : 0,
             static_cast<unsigned>(body.length()));
    CUS_DBGF("[NPK][TEST] canonical_record=%s\n", body.c_str());

    RtdbRestResponse response;
    bool ok = rtdbRestClient().putRawJson(APP_RTDB_PATH_NODE_NPK_TEST,
                                          body,
                                          response,
                                          true);
    CUS_DBGF("[FIREBASE][NPK_TEST] put_ok=%d transport_ok=%d response_received=%d http=%d stage=%s detail=%s path=%s\n",
             ok ? 1 : 0,
             response.transportOk ? 1 : 0,
             response.responseReceived ? 1 : 0,
             response.statusCode,
             response.stage.c_str(),
             response.detail.c_str(),
             APP_RTDB_PATH_NODE_NPK_TEST);
    if (response.body.length()) {
        CUS_DBGF("[FIREBASE][NPK_TEST] response_body=%s\n", response.body.c_str());
    }

    gTestUploadDone = ok;
    return ok;
}

void runNpkPayloadFitTest() {
    collectNpkCycle();
    (void)uploadCanonicalTestRecord(false);
}

void handleCommand(char command) {
    if (command == '\r' || command == '\n' || command == ' ') {
        return;
    }

    switch (command) {
        case 'r':
            CUS_DBGLN("\n[NPK][TEST] Manual read (no Firebase write).");
            printNpkSample(gNpk.read(), 0U, "manual");
            break;
        case 'u':
            CUS_DBGLN("\n[NPK][TEST] Manual upload of latest NPK cycle requested.");
            if (!gSamplesReady) {
                collectNpkCycle();
            }
            (void)uploadCanonicalTestRecord(true);
            break;
        case 'a':
            gAutoCycle = !gAutoCycle;
            CUS_DBGF("[NPK][TEST] auto_cycles=%d\n", gAutoCycle ? 1 : 0);
            break;
        case 'c':
            CUS_DBGLN("\n[NPK][TEST] Manual NPK cycle requested.");
            collectNpkCycle();
            break;
        case 'm':
            CUS_DBGLN("\n[NPK][TEST] Running retained read-only matrix; no Firebase write.");
            gNpkMatrix.run();
            gNpk.begin(gNpkSerial);
            gLastCycleEndMs = millis();
            break;
        case '?':
        case 'h':
            printHelp();
            break;
        default:
            CUS_DBGF("[NPK][TEST] Unknown command '%c'.\n", command);
            printHelp();
            break;
    }
}
}  // namespace

void setup() {
    DEBUG_PORT.begin(DEBUG_BAUDRATE);
    delay(100);

    CUS_DBGLN("\n========== NPK NODE2 PAYLOAD-FIT TEST ==========");
    CUS_DBGLN("[NPK][TEST] Production AppEntry/AppRuntime is disabled temporarily.");
    CUS_DBGLN("[NPK][TEST] This test focuses on near-spaced NPK cycles; Firebase upload is optional and one-shot.");
    printConfiguration();

    gNpkSerial.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    gNpkSerial.setTimeout(50);
    gNpk.begin(gNpkSerial);
    gDeviceContext.begin();
    CUS_DBGF("[NPK][TEST] device_id=%s boot_id=%s wake_reason=%s\n",
             gDeviceContext.deviceId().c_str(),
             gDeviceContext.bootId().c_str(),
             gDeviceContext.wakeReason().c_str());
    printHelp();

    runNpkPayloadFitTest();
}

void loop() {
    while (DEBUG_PORT.available() > 0) {
        handleCommand(static_cast<char>(DEBUG_PORT.read()));
    }

    if (gAutoCycle &&
        gLastCycleEndMs > 0U &&
        millis() - gLastCycleEndMs >= NPK_TEST_CYCLE_GAP_MS) {
        collectNpkCycle();
        // Do not upload every debug cycle. The first automatic cycle is the
        // single low-traffic Firebase sample; later cycles are serial-only.
        (void)uploadCanonicalTestRecord(false);
    }
    delay(20);
}

#endif

// Production entry point. The complete phase-2 flow owns sensor preparation,
// collection, network/Firebase upload, offline buffering, latest publishing,
// telemetry persistence, and deep-sleep finalization.
#include "AppEntry.h"

void setup() {
    appEntrySetup();
}

void loop() {
    appEntryLoop();
}
