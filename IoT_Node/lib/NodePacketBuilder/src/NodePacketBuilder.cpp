#include "NodePacketBuilder.h"

#include <ArduinoJson.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "Sht30Service.h"
#include <time.h>

namespace {
void copyObject(JsonObject dst, JsonObjectConst src) {
    for (JsonPairConst kv : src) {
        dst[kv.key().c_str()] = kv.value();
    }
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
                                                  const String &runningPartition) const {
    JsonDocument outDoc;
    outDoc["schema_version"] = 3;

    JsonObject packet = outDoc["packet"].to<JsonObject>();

    JsonDocument npkDoc;
    JsonObject npkOut = packet["npk_data"].to<JsonObject>();
    if (deserializeJson(npkDoc, npkPayloadJson) == DeserializationError::Ok) {
        copyObject(npkOut, npkDoc.as<JsonObjectConst>());
    } else {
        npkOut["read_ok"] = false;
        npkOut["error_code"] = "npk_payload_invalid";
    }
    npkOut.remove("sensor_type");
    npkOut.remove("sensor_id");

    JsonDocument shtDoc;
    JsonObject shtOut = packet["sht30_data"].to<JsonObject>();
    if (deserializeJson(shtDoc, shtPayloadJson) == DeserializationError::Ok) {
        copyObject(shtOut, shtDoc.as<JsonObjectConst>());
    } else {
        shtOut["sht_read_ok"] = false;
        shtOut["sht_error"] = "sht_payload_invalid";
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

    JsonObject systemOut = packet["system_data"].to<JsonObject>();
    (void)npkAlarm;
    (void)firmwareVersion;
    (void)runningPartition;

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
    String shtJson = _sht30Service.buildJsonPayload("sht30_air",
                                                    "sht30_1",
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
