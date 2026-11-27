#include "SoilMoistureService.h"

#include "Config.h"

SoilMoistureService::SoilMoistureService(uint8_t adcPin,
                                         int dryValue,
                                         int wetValue,
                                         uint8_t sampleCount,
                                         uint16_t sampleGapMs)
    : _sensor(adcPin, dryValue, wetValue, sampleCount, sampleGapMs),
      _adcPin(adcPin),
      _dryValue(dryValue),
      _wetValue(wetValue),
      _sampleCount(sampleCount),
      _sampleGapMs(sampleGapMs) {}

void SoilMoistureService::begin() {
    if (_begun) {
        return;
    }

    _sensor.begin();
    _begun = true;
}

bool SoilMoistureService::read(SoilMoistureReading &reading) {
    if (!_begun) {
        begin();
    }

    const SoilData data = _sensor.read();
    reading = {};
    reading.raw = data.raw;
    reading.rawMin = data.rawMin;
    reading.rawMax = data.rawMax;
    reading.voltageMv = data.voltageMv;
    reading.percent = data.percent;
    reading.sampleCount = _sampleCount;
    reading.sampleGapMs = _sampleGapMs;
    reading.calibrationValid = data.calibrationValid;
    reading.calibrationIsDefault = SOIL_MOISTURE_CALIBRATION_IS_DEFAULT != 0;
    reading.calibrationProfile = SOIL_MOISTURE_CALIBRATION_PROFILE;
    reading.calibrationSource = SOIL_MOISTURE_CALIBRATION_SOURCE;
    reading.readOk = data.rawMin >= 0 && data.rawMax >= data.rawMin;
    reading.sampleValid = reading.readOk && reading.calibrationValid &&
                          reading.percent >= 0 && reading.percent <= 100;
    reading.state = data.state.length() ? data.state : "UNKNOWN";
    reading.error = !reading.readOk
                        ? "adc_read_failed"
                        : (!reading.calibrationValid ? "uncalibrated" :
                           (reading.sampleValid ? "ok" : "value_invalid"));

    _lastReading = reading;
    return reading.readOk;
}

String SoilMoistureService::buildJsonPayload(const char *sensorType,
                                             const char *sensorId,
                                             const char *edgeSystem,
                                             const char *edgeSystemId,
                                             const char *edgeStream) const {
    JsonDocument doc;
    doc["sensor_type"] = sensorType ? sensorType : "soil_moisture_v1_2";
    doc["sensor_id"] = sensorId ? sensorId : "soil_moisture_v1_2_01";
    doc["edge_system"] = edgeSystem ? edgeSystem : "soil_npk_edge";
    doc["edge_system_id"] = edgeSystemId ? edgeSystemId : "edge_npk";
    doc["edge_stream"] = edgeStream ? edgeStream : "soil_moisture_v1_2";
    doc["moisture_adc_gpio"] = _adcPin;
    doc["moisture_read_ok"] = _lastReading.readOk;
    doc["moisture_sample_valid"] = _lastReading.sampleValid;
    doc["moisture_error"] = _lastReading.error;
    doc["moisture_state"] = _lastReading.state;
    doc["moisture_calibration_valid"] = _lastReading.calibrationValid;
    doc["moisture_calibration_is_default"] = _lastReading.calibrationIsDefault;
    doc["moisture_calibration_status"] = !_lastReading.readOk
                                              ? "read_error"
                                              : (!_lastReading.calibrationValid
                                                     ? "uncalibrated"
                                                     : (_lastReading.calibrationIsDefault
                                                            ? "provisional_default"
                                                            : "field_calibrated"));
    doc["moisture_calibration_profile"] = _lastReading.calibrationProfile;
    doc["moisture_calibration_source"] = _lastReading.calibrationSource;
    doc["moisture_calibration_method"] = "manufacturer_two_point_relative";
    doc["moisture_value_semantics"] = "relative_index_0_100_not_vwc";
    doc["moisture_manufacturer_dry_10bit"] = SOIL_MOISTURE_MANUFACTURER_DRY_10BIT;
    doc["moisture_manufacturer_wet_10bit"] = SOIL_MOISTURE_MANUFACTURER_WET_10BIT;
    doc["moisture_dry_adc"] = _dryValue;
    doc["moisture_wet_adc"] = _wetValue;
    if (_lastReading.readOk) {
        doc["moisture_raw"] = _lastReading.raw;
        doc["moisture_raw_min"] = _lastReading.rawMin;
        doc["moisture_raw_max"] = _lastReading.rawMax;
        doc["moisture_voltage_mv"] = _lastReading.voltageMv;
    } else {
        doc["moisture_raw"] = nullptr;
        doc["moisture_raw_min"] = nullptr;
        doc["moisture_raw_max"] = nullptr;
        doc["moisture_voltage_mv"] = nullptr;
    }
    doc["moisture_sample_count"] = _lastReading.sampleCount;
    doc["moisture_sample_gap_ms"] = _lastReading.sampleGapMs;
    doc["moisture_calibration_target_depth_cm"] = SOIL_MOISTURE_CALIBRATION_TARGET_DEPTH_CM;
    doc["moisture_install_depth_cm_min"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN;
    doc["moisture_install_depth_cm_max"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX;
    if (_lastReading.sampleValid) {
        doc["moisture_percent"] = _lastReading.percent;
    } else {
        doc["moisture_percent"] = nullptr;
    }

    String json;
    serializeJson(doc, json);
    return json;
}
