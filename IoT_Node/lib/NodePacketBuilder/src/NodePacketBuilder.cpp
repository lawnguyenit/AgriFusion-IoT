#include "NodePacketBuilder.h"

#include <ArduinoJson.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "Sht30Service.h"
#include <time.h>

namespace {
void compactProductionNpkPayload(JsonObject npkPayload) {
    // The scalar semantic fields are emitted by MyNPK and consumed by the
    // reporter. These verbose objects are duplicated in every valid packet,
    // but remain valuable evidence when the aggregate NPK sample is invalid.
    const bool keepFailureEvidence = !(npkPayload["read_ok"] | false) ||
                                     !(npkPayload["npk_values_valid"] | false);
    if (!keepFailureEvidence) {
        for (const char *key : {"field_validity",
                                "field_value_validity",
                                "field_source",
                                "field_defaulted_zero",
                                "raw_registers",
                                "conversion",
                                "map_diagnostics",
                                "external_sources",
                                "moisture_calibration"}) {
            npkPayload.remove(key);
        }
    }
}

void compactProductionShtPayload(JsonObject shtPayload) {
    const bool sampleValid = shtPayload["sht_sample_valid"] | false;
    const bool readOk = shtPayload["sht_read_ok"] | false;
    if (sampleValid && readOk) {
        for (const char *key : {"sht_init_attempts",
                                "sht_init_error",
                                "sht_init_probe_read_ok",
                                "sht_init_probe_temp_c",
                                "sht_init_probe_hum_pct",
                                "sht_measurement_transport_ok",
                                "sht_frame_ok",
                                "sht_temp_crc_ok",
                                "sht_hum_crc_ok",
                                "sht_received_bytes",
                                "sht_measurement_i2c_error",
                                "sht_measurement_error",
                                "sht_raw_values_available",
                                "sht_raw_temp",
                                "sht_raw_hum",
                                "sht_observed_temp_c",
                                "sht_observed_hum_pct"}) {
            shtPayload.remove(key);
        }
    }
}

bool parseAndCopyObject(JsonObject destination,
                        const String &payloadJson,
                        const char *readOkKey,
                        const char *errorKey,
                        const char *invalidError) {
    JsonDocument sourceDoc;
    const DeserializationError parseError = deserializeJson(sourceDoc, payloadJson);
    if (parseError != DeserializationError::Ok) {
        destination[readOkKey] = false;
        destination[errorKey] = invalidError;
        return false;
    }

    const JsonObjectConst sourceObject = sourceDoc.as<JsonObjectConst>();
    if (sourceObject.isNull() || !destination.set(sourceObject)) {
        destination[readOkKey] = false;
        destination[errorKey] = "payload_copy_overflow";
        return false;
    }

    return true;
}

uint32_t currentUtcSecIfSynced() {
    time_t now = time(nullptr);
    if (now < 1700000000) {
        return 0;
    }
    return static_cast<uint32_t>(now);
}

uint32_t slotIndexFromEpoch(uint32_t epochSec) {
    if (epochSec == 0) {
        return 0;
    }

    uint32_t slotsPerDay = (uint32_t)APP_TELEMETRY_SEQUENCE_SLOTS_PER_DAY;
    if (slotsPerDay == 0) {
        return 0;
    }

    time_t sec = static_cast<time_t>(epochSec);
    struct tm tmLocal;
#if defined(_WIN32)
    localtime_s(&tmLocal, &sec);
#else
    localtime_r(&sec, &tmLocal);
#endif

    uint32_t secOfDay = (uint32_t)tmLocal.tm_hour * 3600U +
                        (uint32_t)tmLocal.tm_min * 60U +
                        (uint32_t)tmLocal.tm_sec;
    uint32_t slotLenSec = 86400U / slotsPerDay;
    if (slotLenSec == 0) {
        return 0;
    }

    uint32_t slotIndex = (secOfDay / slotLenSec) + 1U;
    if (slotIndex > slotsPerDay) {
        slotIndex = slotsPerDay;
    }
    return slotIndex;
}

String dateKeyFromEpoch(uint32_t epochSec) {
    if (epochSec == 0) {
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
}  // namespace

NodePacketBuilder::NodePacketBuilder(Sht30Service &sht30Service)
    : _sht30Service(sht30Service) {}

String NodePacketBuilder::buildCombinedNodePacket(const String &npkPayloadJson,
                                                  const String &shtPayloadJson,
                                                  bool npkAlarm,
                                                  const String &firmwareVersion,
                                                  const String &runningPartition,
                                                  const char *testMode,
                                                  uint32_t testCycleNo,
                                                  bool firebaseUploadEnabled) const {
    JsonDocument outDoc;
    outDoc["schema_version"] = 3;

    JsonObject packet = outDoc["packet"].to<JsonObject>();

    JsonObject npkOut = packet["npk_data"].to<JsonObject>();
    if (!parseAndCopyObject(npkOut,
                            npkPayloadJson,
                            "read_ok",
                            "error_code",
                            "npk_payload_invalid")) {
        npkOut["read_ok"] = false;
    }
    npkOut.remove("sensor_type");
    npkOut.remove("sensor_id");

    JsonObject shtOut = packet["sht30_data"].to<JsonObject>();
    if (!parseAndCopyObject(shtOut,
                            shtPayloadJson,
                            "sht_read_ok",
                            "sht_error",
                            "sht_payload_invalid")) {
        shtOut["sht_read_ok"] = false;
    }
    shtOut.remove("sensor_type");
    shtOut.remove("sensor_id");
    shtOut.remove("edge_system");
    shtOut.remove("edge_system_id");
    shtOut.remove("edge_stream");
    shtOut.remove("sht_addr");
    shtOut.remove("sht_sda");
    shtOut.remove("sht_scl");
    shtOut.remove("sht_retry_limit");
    shtOut.remove("sht_retry_delay_ms");
    shtOut.remove("sht_max_wait_ms");

    // Full diagnostic mode keeps raw protocol evidence for the serial test.
    // The production path keeps the compact semantic contract instead.
    if (testMode == nullptr || testMode[0] == '\0') {
        compactProductionNpkPayload(npkOut);
        compactProductionShtPayload(shtOut);
    }

    JsonObject systemOut = packet["system_data"].to<JsonObject>();
    (void)firmwareVersion;
    (void)runningPartition;

    if (testMode != nullptr && testMode[0] != '\0') {
        systemOut["test_mode"] = testMode;
        systemOut["test_cycle_no"] = testCycleNo;
        systemOut["firebase_upload_enabled"] = firebaseUploadEnabled;
        systemOut["sensor_alarm"] = npkAlarm;
    }

    uint32_t sampleEpochSec = currentUtcSecIfSynced();
    uint32_t sampleSlotNo = slotIndexFromEpoch(sampleEpochSec);
    systemOut["sample_epoch_sec"] = (int)sampleEpochSec;
    systemOut["sample_time_valid"] = sampleEpochSec > 0;
    systemOut["sample_slot_no"] = (int)sampleSlotNo;
    systemOut["sample_slot_count_day"] = (int)APP_TELEMETRY_SEQUENCE_SLOTS_PER_DAY;
    systemOut["sample_date_key"] = dateKeyFromEpoch(sampleEpochSec);

    String out;
    serializeJson(outDoc, out);
    return out;
}

String NodePacketBuilder::buildCombinedNodePacket(const String &npkPayloadJson,
                                                  bool npkAlarm,
                                                  const String &firmwareVersion,
                                                  const String &runningPartition) const {
    String shtJson = _sht30Service.buildJsonPayload(APP_SENSOR_TYPE_SHT30,
                                                    APP_SENSOR_ID_SHT30,
                                                    APP_EDGE_SYSTEM_SHT,
                                                    APP_EDGE_SYSTEM_ID_SHT,
                                                    "sht30",
                                                    SHT30_READ_MAX_ATTEMPTS,
                                                    SHT30_RETRY_DELAY_MS,
                                                    SHT30_MAX_WAIT_MS);
    return buildCombinedNodePacket(npkPayloadJson,
                                   shtJson,
                                   npkAlarm,
                                   firmwareVersion,
                                   runningPartition);
}
