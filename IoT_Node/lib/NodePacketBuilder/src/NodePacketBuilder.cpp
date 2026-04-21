#include "NodePacketBuilder.h"

#include <ArduinoJson.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "Sht30Service.h"

namespace {
void copyObject(JsonObject dst, JsonObjectConst src) {
    for (JsonPairConst kv : src) {
        dst[kv.key().c_str()] = kv.value();
    }
}
}  // namespace

NodePacketBuilder::NodePacketBuilder(Sht30Service &sht30Service)
    : _sht30Service(sht30Service) {}

String NodePacketBuilder::buildCombinedNodePacket(const String &npkPayloadJson,
                                                  bool npkAlarm,
                                                  const String &firmwareVersion,
                                                  const String &runningPartition) const {
    JsonDocument outDoc;
    outDoc["schema_version"] = 3;
    outDoc["node_key"] = APP_NODE_SLOT_KEY;
    outDoc["node_id"] = APP_NODE_ID;
    outDoc["node_name"] = APP_NODE_NAME;

    JsonObject packet = outDoc["packet"].to<JsonObject>();

    JsonDocument npkDoc;
    JsonObject npkOut = packet["npk_data"].to<JsonObject>();
    if (deserializeJson(npkDoc, npkPayloadJson) == DeserializationError::Ok) {
        copyObject(npkOut, npkDoc.as<JsonObjectConst>());
    } else {
        npkOut["read_ok"] = false;
        npkOut["error_code"] = "npk_payload_invalid";
    }
    npkOut["edge_system"] = APP_EDGE_SYSTEM_NPK;
    npkOut["edge_system_id"] = APP_EDGE_SYSTEM_ID_NPK;
    npkOut["edge_stream"] = "npk";

    JsonDocument shtDoc;
    JsonObject shtOut = packet["sht30_data"].to<JsonObject>();
    String shtJson = _sht30Service.buildJsonPayload("sht30_air",
                                                    "sht30_1",
                                                    APP_EDGE_SYSTEM_SHT,
                                                    APP_EDGE_SYSTEM_ID_SHT,
                                                    "sht30",
                                                    SHT30_READ_MAX_ATTEMPTS,
                                                    SHT30_RETRY_DELAY_MS,
                                                    SHT30_MAX_WAIT_MS);
    if (deserializeJson(shtDoc, shtJson) == DeserializationError::Ok) {
        copyObject(shtOut, shtDoc.as<JsonObjectConst>());
    } else {
        shtOut["sht_read_ok"] = false;
        shtOut["sht_error"] = "sht_payload_invalid";
    }

    JsonObject systemOut = packet["system_data"].to<JsonObject>();
    systemOut["edge_system_primary"] = APP_EDGE_SYSTEM_NPK;
    systemOut["edge_system_secondary"] = APP_EDGE_SYSTEM_SHT;
    systemOut["edge_system_id_primary"] = APP_EDGE_SYSTEM_ID_NPK;
    systemOut["edge_system_id_secondary"] = APP_EDGE_SYSTEM_ID_SHT;
    systemOut["wifi_status"] = networkStatusCode();
    systemOut["wifi_connected"] = networkIsConnected();
    systemOut["rssi"] = networkSignalDbm();
    systemOut["transport"] = networkTransportName();
    systemOut["npk_alarm"] = npkAlarm;
    systemOut["sht_ready"] = _sht30Service.ready();
    systemOut["firmware_version"] = firmwareVersion;
    systemOut["running_partition"] = runningPartition;
    systemOut["ts_device_ms"] = (int)millis();

    String out;
    serializeJson(outDoc, out);
    return out;
}
