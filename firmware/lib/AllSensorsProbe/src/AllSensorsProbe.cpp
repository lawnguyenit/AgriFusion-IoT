#include "AllSensorsProbe.h"

#include <Arduino.h>
#include <ArduinoJson.h>

#include "Config.h"
#include "Ds18b20Service.h"
#include "NPK.h"
#include "NodePacketBuilder.h"
#include "Sht30Service.h"
#include "SoilMoistureService.h"

namespace {
HardwareSerial gNpkSerial(1);
MyNPK gNpk;
Sht30Service gSht30(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, APP_SHT30_RETRY_INIT_MS);
Ds18b20Service gDs18b20(DS18B20_DATA_PIN, DS18B20_RETRY_INIT_MS);
SoilMoistureService gMoisture(SOIL_MOISTURE_ADC_PIN,
                              SOIL_MOISTURE_AIR_ADC,
                              SOIL_MOISTURE_WATER_ADC,
                              SOIL_MOISTURE_SAMPLE_COUNT,
                              SOIL_MOISTURE_SAMPLE_GAP_MS);
NodePacketBuilder gPacketBuilder(gSht30);
uint32_t gLastCycleMs = 0U;
uint32_t gCycleNo = 0U;

struct ShtSummary {
    bool readOk = false;
    bool sampleValid = false;
    float observedTempC = NAN;
    float observedHumPct = NAN;
    String error = "not_read";
};

struct PacketShapeSummary {
    bool parseOk = false;
    bool hasNpk = false;
    bool hasSht30 = false;
    bool hasSystem = false;
};

ShtSummary parseShtSummary(const String &json) {
    ShtSummary summary;
    JsonDocument doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) {
        summary.error = "json_parse_fail";
        return summary;
    }

    summary.readOk = doc["sht_read_ok"] | false;
    summary.sampleValid = doc["sht_sample_valid"] | false;
    summary.error = doc["sht_error"] | "unknown";
    if (!doc["sht_observed_temp_c"].isNull()) {
        summary.observedTempC = doc["sht_observed_temp_c"] | NAN;
    }
    if (!doc["sht_observed_hum_pct"].isNull()) {
        summary.observedHumPct = doc["sht_observed_hum_pct"] | NAN;
    }
    return summary;
}

PacketShapeSummary inspectPacketShape(const String &json) {
    PacketShapeSummary summary;
    JsonDocument doc;
    if (deserializeJson(doc, json) != DeserializationError::Ok) {
        return summary;
    }

    const JsonObjectConst packet = doc["packet"].as<JsonObjectConst>();
    if (packet.isNull()) {
        return summary;
    }

    summary.parseOk = true;
    summary.hasNpk = packet["npk_data"].as<JsonObjectConst>().size() > 0;
    summary.hasSht30 = packet["sht30_data"].as<JsonObjectConst>().size() > 0;
    summary.hasSystem = packet["system_data"].as<JsonObjectConst>().size() > 0;
    return summary;
}

void runFullSensorCycle(const char *reason) {
    ++gCycleNo;
    CUS_DBGF("\n[FULL_SENSOR_TEST][CYCLE] ===== START seq=%lu reason=%s =====\n",
             static_cast<unsigned long>(gCycleNo),
             reason ? reason : "unknown");

    NPK_Data npk = gNpk.read();

    if (!gSht30.ready()) {
        gSht30.tryInit(true);
    }
    const String shtJson = gSht30.buildJsonPayload(APP_SENSOR_TYPE_SHT30,
                                                   APP_SENSOR_ID_SHT30,
                                                   APP_EDGE_SYSTEM_SHT,
                                                   APP_EDGE_SYSTEM_ID_SHT,
                                                   "sht30",
                                                   SHT30_READ_MAX_ATTEMPTS,
                                                   SHT30_RETRY_DELAY_MS,
                                                   SHT30_MAX_WAIT_MS);
    const ShtSummary sht = parseShtSummary(shtJson);

    if (!gDs18b20.ready()) {
        gDs18b20.tryInit(true);
    }
    Ds18b20Reading ds18b20;
    const bool dsReadOk = gDs18b20.readPrimary(ds18b20);
    if (dsReadOk) {
        gNpk.applyExternalTemperature(npk,
                                       ds18b20.temperatureC,
                                       ds18b20.rawTemperature);
    }

    SoilMoistureReading moisture;
    const bool moistureReadOk = gMoisture.read(moisture);
    // Keep the source diagnostics in the NPK-shaped packet even when the ADC
    // read or calibration is invalid; only the semantic value is withheld.
    gNpk.applyExternalMoisture(npk, moisture);

    const bool sensorAlarm = !npk.readOk ||
                             !npk.phValueValid ||
                             !sht.sampleValid ||
                             !dsReadOk ||
                             !moisture.sampleValid;
    const String npkJson = gNpk.makeJsonFromData(npk,
                                                 0U,
                                                 0U,
                                                 false,
                                                 0U,
                                                 sensorAlarm);
    const String packet = gPacketBuilder.buildCombinedNodePacket(
        npkJson,
        shtJson,
        sensorAlarm,
        "full_sensor_test",
        "serial",
        "full_sensor_serial_only",
        gCycleNo,
        false);
    const PacketShapeSummary packetShape = inspectPacketShape(packet);
    const bool packetComposeOk = packetShape.parseOk &&
                                 packetShape.hasNpk &&
                                 packetShape.hasSht30 &&
                                 packetShape.hasSystem;
    const bool aggregateAlarm = sensorAlarm || !packetComposeOk;

    CUS_DBGF("[FULL_SENSOR_TEST][NPK] read_ok=%d values_valid=%d ph_value_valid=%d temp=%.2f hum=%.2f ph=%.2f ec=%d N=%d P=%d K=%d error=%s\n",
             npk.readOk ? 1 : 0,
             npkJson.indexOf("\"npk_values_valid\":true") >= 0 ? 1 : 0,
             npk.phValueValid ? 1 : 0,
             static_cast<double>(npk.temp),
             static_cast<double>(npk.hum),
             static_cast<double>(npk.ph),
             npk.ec,
             npk.n,
             npk.p,
             npk.k,
             MyNPK::errorCodeToString(npk.errorCodeRaw));
    CUS_DBGF("[FULL_SENSOR_TEST][SHT30] read_ok=%d sample_valid=%d observed_temp=%.2f observed_hum=%.2f error=%s\n",
             sht.readOk ? 1 : 0,
             sht.sampleValid ? 1 : 0,
             static_cast<double>(sht.observedTempC),
             static_cast<double>(sht.observedHumPct),
             sht.error.c_str());
    CUS_DBGF("[FULL_SENSOR_TEST][DS18B20] read_ok=%d presence=%d crc=%d temp=%.2f error=%s\n",
             dsReadOk ? 1 : 0,
             ds18b20.presenceDetected ? 1 : 0,
             ds18b20.scratchpadCrcOk ? 1 : 0,
             static_cast<double>(ds18b20.temperatureC),
             dsReadOk ? "ok" : "read_failed");
    CUS_DBGF("[FULL_SENSOR_TEST][MOISTURE] read_ok=%d sample_valid=%d raw=%d raw_min=%d raw_max=%d voltage_mv=%lu percent=%d state=%s error=%s calibration=%s profile=%s dry_adc=%d wet_adc=%d depth_cm=%d..%d\n",
             moistureReadOk ? 1 : 0,
             moisture.sampleValid ? 1 : 0,
             moisture.raw,
             moisture.rawMin,
             moisture.rawMax,
             static_cast<unsigned long>(moisture.voltageMv),
             moisture.percent,
             moisture.state.c_str(),
             moisture.error.c_str(),
             moisture.calibrationIsDefault ? "provisional_default" : "field_calibrated",
             moisture.calibrationProfile.c_str(),
             SOIL_MOISTURE_AIR_ADC,
             SOIL_MOISTURE_WATER_ADC,
             static_cast<int>(SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN),
             static_cast<int>(SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX));
    CUS_DBGF("[FULL_SENSOR_TEST][PACKET_CHECK] parse=%d npk_data=%d sht30_data=%d system_data=%d compose_ok=%d\n",
             packetShape.parseOk ? 1 : 0,
             packetShape.hasNpk ? 1 : 0,
             packetShape.hasSht30 ? 1 : 0,
             packetShape.hasSystem ? 1 : 0,
             packetComposeOk ? 1 : 0);
    CUS_DBGF("[FULL_SENSOR_TEST][RESULT] sensor_alarm=%d packet_bytes=%u firebase_upload=0\n",
             aggregateAlarm ? 1 : 0,
             static_cast<unsigned>(packet.length()));
    CUS_DBGF("[FULL_SENSOR_TEST][PACKET] %s\n", packet.c_str());
    CUS_DBGF("[FULL_SENSOR_TEST][CYCLE] ===== END seq=%lu =====\n",
             static_cast<unsigned long>(gCycleNo));
}

}  // namespace

void allSensorsProbeBegin() {
    gNpkSerial.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    gNpkSerial.setTimeout(50);
    gNpk.begin(gNpkSerial);
    gMoisture.begin();
    gSht30.tryInit(true);
    gDs18b20.tryInit(true);

    CUS_DBGF("[FULL_SENSOR_TEST][TEST] NPK UART=%lu 8N1 RX=%d TX=%d; SHT30 SDA=%d SCL=%d addr=0x%02X; DS18B20 GPIO=%d; moisture ADC_GPIO=%d interval_ms=%lu\n",
             static_cast<unsigned long>(NPK_BAUDRATE),
             NPK_RX_PIN,
             NPK_TX_PIN,
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             SHT30_I2C_ADDR,
             DS18B20_DATA_PIN,
             SOIL_MOISTURE_ADC_PIN,
             static_cast<unsigned long>(APP_ALL_SENSORS_TEST_INTERVAL_MS));
    CUS_DBGLN("[FULL_SENSOR_TEST][TEST] Serial-only: no Firebase upload, no modem diagnostics, no deep sleep.");
    CUS_DBGF("[FULL_SENSOR_TEST][TEST] Moisture uses manufacturer_two_point_relative; provisional profile=%s dry_adc=%d wet_adc=%d target_depth_cm=%.1f; percentage is a relative index, not VWC.\n",
             SOIL_MOISTURE_CALIBRATION_PROFILE,
             SOIL_MOISTURE_AIR_ADC,
             SOIL_MOISTURE_WATER_ADC,
             static_cast<double>(SOIL_MOISTURE_CALIBRATION_TARGET_DEPTH_CM));

    runFullSensorCycle("boot");
    gLastCycleMs = millis();
}

void allSensorsProbeLoop() {
    if (millis() - gLastCycleMs >= APP_ALL_SENSORS_TEST_INTERVAL_MS) {
        runFullSensorCycle("interval");
        gLastCycleMs = millis();
    }
}
