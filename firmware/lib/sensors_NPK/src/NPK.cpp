#include "NPK.h"

#include <math.h>

#include "Config.h"

namespace {
static const uint8_t NPK_MAX_ATTEMPTS = 3;  // 1 initial + 2 retries
static const uint32_t NPK_RESPONSE_TIMEOUT_MS = 2000;

struct RegisterReadResult {
    uint8_t status;
    uint8_t attempts;
};

RegisterReadResult readHoldingRegistersWithRetry(ModbusMaster &node,
                                                  uint16_t startAddress,
                                                  uint8_t quantity) {
    RegisterReadResult result = {
        ModbusMaster::ku8MBResponseTimedOut,
        0};

    while (result.attempts < NPK_MAX_ATTEMPTS) {
        result.attempts++;
        result.status = node.readHoldingRegisters(startAddress, quantity);
        if (result.status == ModbusMaster::ku8MBSuccess) {
            break;
        }
    }

    return result;
}

bool isCompleteProtocolFrame(uint8_t status) {
    return status == ModbusMaster::ku8MBSuccess ||
           (status >= ModbusMaster::ku8MBIllegalFunction &&
            status <= ModbusMaster::ku8MBSlaveDeviceFailure);
}

bool isPlausibleHumidity(float value) {
    return value >= 0.0f && value <= 100.0f;
}

bool isPlausibleTemperature(float value) {
    return value >= -10.0f && value <= 85.0f;
}

bool isPlausiblePh(float value) {
    // Soil pH=0 is not accepted as a normal measurement. Keep the existing
    // project range so a valid frame with raw pH=0 is reported as invalid
    // instead of being promoted as a real zero value.
    return value >= 3.0f && value <= 10.0f;
}

bool isPlausibleEc(int value) {
    return value >= 0;
}

bool isWithinEcCalibrationDomain(const NPK_Data &data) {
    return data.n >= NPK_EC_CALIBRATION_N_MIN &&
           data.n <= NPK_EC_CALIBRATION_N_MAX &&
           data.p >= NPK_EC_CALIBRATION_P_MIN &&
           data.p <= NPK_EC_CALIBRATION_P_MAX &&
           data.k >= NPK_EC_CALIBRATION_K_MIN &&
           data.k <= NPK_EC_CALIBRATION_K_MAX;
}

void inferEcFromNpk(NPK_Data &data) {
#if NPK_EC_INFERENCE_ENABLED
    if (!data.nReadOk || !data.pReadOk || !data.kReadOk ||
        !data.nValueValid || !data.pValueValid || !data.kValueValid) {
        return;
    }

    data.ecEstimateFloat = NPK_EC_INFERENCE_INTERCEPT +
                           NPK_EC_INFERENCE_N_COEFFICIENT * data.n +
                           NPK_EC_INFERENCE_P_COEFFICIENT * data.p +
                           NPK_EC_INFERENCE_K_COEFFICIENT * data.k;
    data.ec = static_cast<int>(lroundf(data.ecEstimateFloat));
    if (data.ec < 0) {
        data.ec = 0;
    }
    data.ecDerivedFromNpk = true;
    data.ecValueValid = isPlausibleEc(data.ec);
    data.ecInferenceWithinCalibrationDomain = isWithinEcCalibrationDomain(data);

#else
    (void)data;
#endif
}
}

MyNPK::MyNPK() {}

void MyNPK::begin(Stream &serialPort) {
    _serial = &serialPort;
    _node.begin(NPK_MODBUS_SLAVE_ID, serialPort);
}

const char *MyNPK::errorCodeToString(uint8_t code) {
    switch (code) {
        case ModbusMaster::ku8MBSuccess:
            return "ok";
        case ModbusMaster::ku8MBIllegalFunction:
            return "illegal_function";
        case ModbusMaster::ku8MBIllegalDataAddress:
            return "illegal_data_address";
        case ModbusMaster::ku8MBIllegalDataValue:
            return "illegal_data_value";
        case ModbusMaster::ku8MBSlaveDeviceFailure:
            return "slave_device_failure";
        case ModbusMaster::ku8MBInvalidSlaveID:
            return "invalid_slave_id";
        case ModbusMaster::ku8MBInvalidFunction:
            return "invalid_function";
        case ModbusMaster::ku8MBResponseTimedOut:
            return "response_timeout";
        case ModbusMaster::ku8MBInvalidCRC:
            return "invalid_crc";
        default:
            return "unknown";
    }
}

const char *MyNPK::readMapToString(uint8_t readMap) {
    switch (readMap) {
        case NPK_READ_MAP_LEGACY_FULL:
            return "legacy_full_map";
        case NPK_READ_MAP_SPARSE:
            return "sparse_confirmed_map";
        default:
            return "none";
    }
}

void MyNPK::applyExternalTemperature(NPK_Data &data,
                                     float temperatureC,
                                     int16_t rawTemperature) {
    data.temp = temperatureC;
    data.rawTemp = static_cast<uint16_t>(rawTemperature);
    // Keep Modbus protocol evidence separate: this value did not come from
    // an NPK temperature register. The external source and semantic validity
    // are recorded independently below.
    data.tempReadOk = false;
    data.tempValueValid = isPlausibleTemperature(temperatureC);
    data.tempDefaultedToZero = false;
    data.tempFromExternalSensor = data.tempValueValid;
}

void MyNPK::applyExternalMoisture(NPK_Data &data,
                                  const SoilMoistureReading &reading) {
    data.humFromExternalSensor = true;
    data.externalHumReadOk = reading.readOk;
    data.externalHumSampleValid = reading.sampleValid;
    data.externalHumCalibrationValid = reading.calibrationValid;
    data.externalHumCalibrationIsDefault = reading.calibrationIsDefault;
    data.externalHumRaw = reading.raw;
    data.externalHumRawMin = reading.rawMin;
    data.externalHumRawMax = reading.rawMax;
    data.externalHumPercent = reading.percent;
    data.externalHumVoltageMv = reading.voltageMv;
    data.externalHumState = reading.state;
    data.externalHumError = reading.error;
    data.externalHumCalibrationProfile = reading.calibrationProfile;
    data.externalHumCalibrationSource = reading.calibrationSource;

    // Preserve the existing NPK humidity field. The approved provisional
    // manufacturer-relative profile is publishable, but its calibration regime
    // remains explicit so later labels can stratify or recalibrate it.
    data.hum = reading.sampleValid ? static_cast<float>(reading.percent) : 0.0f;
    data.humReadOk = false;
    data.humValueValid = reading.sampleValid;
    data.humDefaultedToZero = false;
}

NPK_Data MyNPK::read() {
    NPK_Data result = {};
    result.error = true;
    result.readOk = false;
    result.errorCodeRaw = ModbusMaster::ku8MBResponseTimedOut;
    result.retryCount = 0;
    result.timeoutMs = NPK_RESPONSE_TIMEOUT_MS;
    result.readDurationMs = 0;
    result.crcOk = false;
    result.frameOk = false;
    result.readMap = NPK_READ_MAP_NONE;
    result.legacyBlockStatus = ModbusMaster::ku8MBResponseTimedOut;
    result.phStatus = ModbusMaster::ku8MBResponseTimedOut;
    result.npkStatus = ModbusMaster::ku8MBResponseTimedOut;
    result.ecEstimateFloat = 0.0f;

    uint32_t readStartMs = millis();

    // Phase 1 read one contiguous block and decoded all seven fields from it.
    // Probe it first to restore soil temperature/humidity/EC when this sensor
    // profile responds. Node2's confirmed sparse map remains the fallback.
#if NPK_LEGACY_FULL_MAP_ENABLED
    const RegisterReadResult legacyRead =
        readHoldingRegistersWithRetry(_node,
                                      NPK_LEGACY_FULL_MAP_START,
                                      NPK_LEGACY_FULL_MAP_COUNT);
    result.legacyBlockStatus = legacyRead.status;
    result.legacyBlockAttempts = legacyRead.attempts;
    result.legacyBlockReadOk = legacyRead.status == ModbusMaster::ku8MBSuccess;
    if (result.legacyBlockReadOk) {
        result.readMap = NPK_READ_MAP_LEGACY_FULL;
        result.rawHum = _node.getResponseBuffer(0);
        result.rawTemp = _node.getResponseBuffer(1);
        result.rawEc = _node.getResponseBuffer(2);
        result.rawPh = _node.getResponseBuffer(3);
        result.rawN = _node.getResponseBuffer(4);
        result.rawP = _node.getResponseBuffer(5);
        result.rawK = _node.getResponseBuffer(6);

        // Keep the phase-1 conversion exactly: humidity/temp/pH are tenths,
        // while EC and N/P/K are direct register values.
        result.hum = result.rawHum / 10.0f;
        result.temp = result.rawTemp / 10.0f;
        result.ec = result.rawEc;
        result.ph = result.rawPh / 10.0f;
        result.n = result.rawN;
        result.p = result.rawP;
        result.k = result.rawK;
        result.humReadOk = true;
        result.tempReadOk = true;
        result.phReadOk = true;
        result.ecReadOk = true;
        result.nReadOk = true;
        result.pReadOk = true;
        result.kReadOk = true;
        result.humValueValid = isPlausibleHumidity(result.hum);
        result.tempValueValid = isPlausibleTemperature(result.temp);
        result.phValueValid = isPlausiblePh(result.ph);
        result.ecValueValid = isPlausibleEc(result.ec);
        result.nValueValid = true;
        result.pValueValid = true;
        result.kValueValid = true;
        result.phStatus = legacyRead.status;
        result.phAttempts = legacyRead.attempts;
        result.npkStatus = legacyRead.status;
        result.npkAttempts = legacyRead.attempts;
        result.readDurationMs = millis() - readStartMs;
        result.retryCount = legacyRead.attempts > 0 ? legacyRead.attempts - 1 : 0;
        result.errorCodeRaw = ModbusMaster::ku8MBSuccess;
        result.readOk = true;
        result.error = false;
        result.crcOk = true;
        result.frameOk = true;

        CUS_DBGF("-> [NPK] Read success map=%s legacy=0x%04X..0x%04X, duration=%lu ms\n",
                 readMapToString(result.readMap),
                 (unsigned)NPK_LEGACY_FULL_MAP_START,
                 (unsigned)(NPK_LEGACY_FULL_MAP_START + NPK_LEGACY_FULL_MAP_COUNT - 1U),
                 (unsigned long)result.readDurationMs);
        CUS_DBGF("[NPK][RAW] hum=0x%04X temp=0x%04X ec=0x%04X ph=0x%04X N=0x%04X P=0x%04X K=0x%04X\n",
                 result.rawHum, result.rawTemp, result.rawEc, result.rawPh,
                 result.rawN, result.rawP, result.rawK);
        return result;
    }

    CUS_DBGF("[NPK][MAP] legacy_full failed status=0x%02X(%s) attempts=%u; fallback=sparse\n",
             legacyRead.status,
             errorCodeToString(legacyRead.status),
             (unsigned)legacyRead.attempts);
#endif

    result.readMap = NPK_READ_MAP_SPARSE;
#if NPK_UNSUPPORTED_SOIL_CLIMATE_AS_ZERO
    // The confirmed sparse profile has no responding soil temperature or
    // humidity registers. Keep the schema populated with the requested zero
    // policy, while tempReadOk/humReadOk remain false as protocol evidence.
    result.temp = 0.0f;
    result.hum = 0.0f;
    result.tempDefaultedToZero = true;
    result.humDefaultedToZero = true;
#endif
    // Node2's confirmed sparse holding-register groups. These are separate
    // transactions because the contiguous phase-1 request may timeout.
    const RegisterReadResult phRead =
        readHoldingRegistersWithRetry(_node, NPK_REG_PH, 1U);
    result.phStatus = phRead.status;
    result.phAttempts = phRead.attempts;
    if (phRead.status == ModbusMaster::ku8MBSuccess) {
        result.rawPh = _node.getResponseBuffer(0);
        result.ph = result.rawPh / 10.0f;
        result.phReadOk = true;
        result.phValueValid = isPlausiblePh(result.ph);
    }

    const RegisterReadResult npkRead =
        readHoldingRegistersWithRetry(_node, NPK_REG_NPK, NPK_REG_NPK_COUNT);
    result.npkStatus = npkRead.status;
    result.npkAttempts = npkRead.attempts;
    if (npkRead.status == ModbusMaster::ku8MBSuccess) {
        result.rawN = _node.getResponseBuffer(0);
        result.rawP = _node.getResponseBuffer(1);
        result.rawK = _node.getResponseBuffer(2);
        result.n = result.rawN;
        result.p = result.rawP;
        result.k = result.rawK;
        result.nReadOk = true;
        result.pReadOk = true;
        result.kReadOk = true;
        result.nValueValid = true;
        result.pValueValid = true;
        result.kValueValid = true;
    }

    // EC register 0x0015 did not respond in the retained matrix. Once all
    // three proxy channels are available, write the empirical EC proxy into
    // the public data.ec field while preserving the raw-register distinction.
    inferEcFromNpk(result);

    result.readDurationMs = millis() - readStartMs;
    result.retryCount = (result.legacyBlockAttempts > 0 ? result.legacyBlockAttempts - 1 : 0) +
                        (phRead.attempts > 0 ? phRead.attempts - 1 : 0) +
                        (npkRead.attempts > 0 ? npkRead.attempts - 1 : 0);

    // Report the first failed confirmed group. If both groups succeed, this
    // is the standard Modbus success code. A failed legacy probe is retained
    // separately and does not turn a successful sparse fallback into a fault.
    result.errorCodeRaw = phRead.status != ModbusMaster::ku8MBSuccess
                              ? phRead.status
                              : npkRead.status;
    result.readOk = (phRead.status == ModbusMaster::ku8MBSuccess) &&
                    (npkRead.status == ModbusMaster::ku8MBSuccess);
    result.error = !result.readOk;

    result.crcOk = isCompleteProtocolFrame(phRead.status) &&
                   isCompleteProtocolFrame(npkRead.status);
    result.frameOk = result.crcOk;

    if (result.readOk) {
        CUS_DBGF("-> [NPK] Read success map=%s ph=0x%04X npk=0x%04X..0x%04X, duration=%lu ms\n",
                 readMapToString(result.readMap),
                 (unsigned)NPK_REG_PH,
                 (unsigned)NPK_REG_NPK,
                 (unsigned)(NPK_REG_NPK + NPK_REG_NPK_COUNT - 1U),
                 (unsigned long)result.readDurationMs);
        CUS_DBGF("[NPK][RAW] ph=0x%04X (%.1f via raw/10) N=0x%04X P=0x%04X K=0x%04X\n",
                 result.rawPh, result.ph, result.rawN, result.rawP, result.rawK);
        CUS_DBGF("[NPK][VALUES] temp=%.1f hum=%.1f ph=%.1f ec=%d N=%d P=%d K=%d ph_valid=%d ec_valid=%d\n",
                 result.temp,
                 result.hum,
                 result.ph,
                 result.ec,
                 result.n,
                 result.p,
                 result.k,
                 result.phValueValid ? 1 : 0,
                 result.ecValueValid ? 1 : 0);
    } else {
        CUS_DBGF("-> [NPK] Read fail map=%s code=0x%02X (%s), ph_status=0x%02X npk_status=0x%02X, retry=%u, duration=%lu ms\n",
                 readMapToString(result.readMap),
                 result.errorCodeRaw, errorCodeToString(result.errorCodeRaw),
                 phRead.status,
                 npkRead.status,
                 (unsigned)result.retryCount, (unsigned long)result.readDurationMs);
    }

    if (result.phReadOk) {
        CUS_DBGF("[NPK][PH] frame=ok raw=0x%04X decoded=%.1f conversion=raw/10 value_valid=%d range=3.0..10.0\n",
                 result.rawPh, result.ph, result.phValueValid ? 1 : 0);
    } else {
        CUS_DBGF("[NPK][PH] frame=missing status=0x%02X(%s) attempts=%u raw=unavailable\n",
                 result.phStatus,
                 errorCodeToString(result.phStatus),
                 (unsigned)result.phAttempts);
    }

    return result;
}

String MyNPK::makeJsonFromData(const NPK_Data &data,
                               uint32_t sampleIntervalMs,
                               uint32_t consecutiveFailCount,
                               bool recoveredAfterFail,
                               uint32_t failStreakBeforeRecover,
                               bool sensorAlarm) {
    JsonDocument doc;
    bool nutrientSignal = ((data.ecReadOk || data.ecDerivedFromNpk) && data.ec > 0) ||
                          (data.nReadOk && data.n > 0) ||
                          (data.pReadOk && data.p > 0) ||
                          (data.kReadOk && data.k > 0) ||
                          (data.humValueValid && data.hum > 0.01f);
    bool allValueFieldsValid = (data.tempValueValid || data.tempDefaultedToZero) &&
                               (data.humValueValid || data.humDefaultedToZero) &&
                               data.phValueValid && data.ecValueValid &&
                               data.nValueValid && data.pValueValid &&
                               data.kValueValid;
    bool npkValuesValid = data.readOk && allValueFieldsValid && nutrientSignal;

    doc["sensor_type"] = APP_SENSOR_TYPE_SOIL_7IN1;
    doc["sensor_id"] = APP_SENSOR_ID_SOIL_7IN1;

    doc["read_ok"] = data.readOk;
    doc["error_code"] = errorCodeToString(data.errorCodeRaw);
    doc["error_code_raw"] = data.errorCodeRaw;
    doc["retry_count"] = data.retryCount;
    doc["timeout_ms"] = data.timeoutMs;
    doc["read_duration_ms"] = data.readDurationMs;
    doc["crc_ok"] = data.crcOk;
    doc["frame_ok"] = data.frameOk;
    doc["read_map"] = readMapToString(data.readMap);
    doc["sample_interval_ms"] = sampleIntervalMs;
    doc["consecutive_fail_count"] = consecutiveFailCount;
    doc["recovered_after_fail"] = recoveredAfterFail;
    doc["fail_streak_before_recover"] = failStreakBeforeRecover;
    doc["sensor_alarm"] = sensorAlarm;
    doc["npk_values_valid"] = npkValuesValid;
    doc["npk_signal_present"] = nutrientSignal;

    JsonObject fieldValidity = doc["field_validity"].to<JsonObject>();
    fieldValidity["temp"] = data.tempReadOk;
    fieldValidity["hum"] = data.humReadOk;
    fieldValidity["ph"] = data.phReadOk;
    fieldValidity["ec"] = data.ecReadOk || data.ecDerivedFromNpk;
    fieldValidity["N"] = data.nReadOk;
    fieldValidity["P"] = data.pReadOk;
    fieldValidity["K"] = data.kReadOk;

    JsonObject valueValidity = doc["field_value_validity"].to<JsonObject>();
    valueValidity["temp"] = data.tempValueValid;
    valueValidity["hum"] = data.humValueValid;
    valueValidity["ph"] = data.phValueValid;
    valueValidity["ec"] = data.ecValueValid;
    valueValidity["N"] = data.nValueValid;
    valueValidity["P"] = data.pValueValid;
    valueValidity["K"] = data.kValueValid;

    JsonObject fieldSource = doc["field_source"].to<JsonObject>();
    fieldSource["temp"] = data.tempFromExternalSensor
                               ? "ds18b20"
                               : (data.tempDefaultedToZero
                                      ? "unsupported_default_zero"
                                      : (data.tempReadOk ? "modbus_register" : "unavailable"));
    fieldSource["hum"] = data.humFromExternalSensor
                              ? (data.externalHumSampleValid
                                     ? "soil_moisture_v1_2"
                                     : (data.externalHumReadOk
                                            ? "soil_moisture_v1_2_uncalibrated"
                                            : "soil_moisture_v1_2_read_error"))
                              : (data.humDefaultedToZero
                                     ? "unsupported_default_zero"
                                     : (data.humReadOk ? "modbus_register" : "unavailable"));
    fieldSource["ph"] = data.phReadOk ? "modbus_register" : "unavailable";
    fieldSource["ec"] = data.ecDerivedFromNpk
                             ? "npk_proxy_derived"
                             : (data.ecReadOk ? "modbus_register" : "unavailable");
    fieldSource["N"] = data.nReadOk ? "modbus_register" : "unavailable";
    fieldSource["P"] = data.pReadOk ? "modbus_register" : "unavailable";
    fieldSource["K"] = data.kReadOk ? "modbus_register" : "unavailable";

    JsonObject defaultedZero = doc["field_defaulted_zero"].to<JsonObject>();
    defaultedZero["temp"] = data.tempDefaultedToZero;
    defaultedZero["hum"] = data.humDefaultedToZero;
    defaultedZero["ph"] = false;
    defaultedZero["N"] = false;
    defaultedZero["P"] = false;
    defaultedZero["K"] = false;

    JsonObject raw = doc["raw_registers"].to<JsonObject>();
    if (data.humReadOk) raw["hum"] = data.rawHum; else raw["hum"] = nullptr;
    if (data.tempReadOk && !data.tempFromExternalSensor) raw["temp"] = data.rawTemp; else raw["temp"] = nullptr;
    if (data.ecReadOk || data.ecDerivedFromNpk) raw["ec"] = data.ec; else raw["ec"] = nullptr;
    if (data.phReadOk) raw["ph"] = data.rawPh; else raw["ph"] = nullptr;
    if (data.nReadOk) raw["N"] = data.rawN; else raw["N"] = nullptr;
    if (data.pReadOk) raw["P"] = data.rawP; else raw["P"] = nullptr;
    if (data.kReadOk) raw["K"] = data.rawK; else raw["K"] = nullptr;

    JsonObject conversion = doc["conversion"].to<JsonObject>();
    conversion["hum"] = data.humFromExternalSensor
                              ? "manufacturer_two_point_relative"
                              : (data.humDefaultedToZero
                                     ? "unsupported_default_zero"
                                     : "raw_register/10.0");
    conversion["temp"] = data.tempFromExternalSensor
                               ? "ds18b20_raw/16.0"
                               : (data.tempDefaultedToZero
                                      ? "unsupported_default_zero"
                                      : "raw_register/10.0");
    conversion["ec"] = data.ecDerivedFromNpk
                           ? NPK_EC_INFERENCE_FORMULA_VERSION
                           : "raw_register";
    conversion["ph"] = "raw_register/10.0";
    conversion["N"] = "raw_register";
    conversion["P"] = "raw_register";
    conversion["K"] = "raw_register";

    // Compact semantic fields are promoted separately so the production
    // packet can drop the verbose maps while Layer0/Layer1 still know the
    // source, validity, and calibration regime of every public value.
    doc["temp_protocol_ok"] = data.tempReadOk;
    doc["temp_value_valid"] = data.tempValueValid;
    doc["temp_source"] = data.tempFromExternalSensor
                              ? "ds18b20"
                              : (data.tempDefaultedToZero
                                     ? "unsupported_default_zero"
                                     : (data.tempReadOk ? "modbus_register" : "unavailable"));
    doc["temp_defaulted_zero"] = data.tempDefaultedToZero;
    doc["hum_protocol_ok"] = data.humReadOk;
    doc["hum_value_valid"] = data.humValueValid;
    doc["hum_source"] = data.humFromExternalSensor
                             ? (data.externalHumSampleValid
                                    ? "soil_moisture_v1_2"
                                    : "soil_moisture_v1_2_invalid")
                             : (data.humDefaultedToZero
                                    ? "unsupported_default_zero"
                                    : (data.humReadOk ? "modbus_register" : "unavailable"));
    doc["hum_defaulted_zero"] = data.humDefaultedToZero;
    doc["ph_protocol_ok"] = data.phReadOk;
    doc["ph_value_valid"] = data.phValueValid;
    doc["ph_state"] = !data.phReadOk
                           ? "no_response"
                           : (data.phValueValid ? "valid" : "frame_ok_value_invalid");
    doc["ec_protocol_ok"] = data.ecReadOk;
    doc["ec_value_valid"] = data.ecValueValid;
    doc["ec_source"] = data.ecDerivedFromNpk
                            ? "npk_proxy_derived"
                            : (data.ecReadOk ? "modbus_register" : "unavailable");
    doc["ec_measurement_kind"] = data.ecDerivedFromNpk
                                       ? "derived_proxy"
                                       : (data.ecReadOk ? "observed_register" : "unavailable");
    doc["N_value_valid"] = data.nValueValid;
    doc["N_source"] = data.nReadOk ? "modbus_register" : "unavailable";
    doc["P_value_valid"] = data.pValueValid;
    doc["P_source"] = data.pReadOk ? "modbus_register" : "unavailable";
    doc["K_value_valid"] = data.kValueValid;
    doc["K_source"] = data.kReadOk ? "modbus_register" : "unavailable";
    if (data.humFromExternalSensor) {
        const char *calibrationStatus = !data.externalHumReadOk
                                            ? "read_error"
                                            : (!data.externalHumCalibrationValid
                                                   ? "uncalibrated"
                                                   : (data.externalHumCalibrationIsDefault
                                                          ? "provisional_default"
                                                          : "field_calibrated"));
        doc["hum_calibration_status"] = calibrationStatus;
        doc["hum_calibration_profile"] = data.externalHumCalibrationProfile;
        doc["hum_value_semantics"] = "relative_index_0_100_not_vwc";
        doc["hum_raw_adc"] = data.externalHumRaw;
        doc["hum_voltage_mv"] = data.externalHumVoltageMv;
        doc["hum_install_depth_cm_min"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN;
        doc["hum_install_depth_cm_max"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX;
    } else {
        doc["hum_calibration_status"] = "not_applicable";
        doc["hum_calibration_profile"] = nullptr;
        doc["hum_value_semantics"] = nullptr;
        doc["hum_raw_adc"] = nullptr;
        doc["hum_voltage_mv"] = nullptr;
        doc["hum_install_depth_cm_min"] = nullptr;
        doc["hum_install_depth_cm_max"] = nullptr;
    }

    JsonObject mapDiagnostics = doc["map_diagnostics"].to<JsonObject>();
    mapDiagnostics["selected"] = readMapToString(data.readMap);
    mapDiagnostics["legacy_start"] = NPK_LEGACY_FULL_MAP_START;
    mapDiagnostics["legacy_count"] = NPK_LEGACY_FULL_MAP_COUNT;
    mapDiagnostics["legacy_read_ok"] = data.legacyBlockReadOk;
    mapDiagnostics["legacy_status"] = data.legacyBlockStatus;
    mapDiagnostics["legacy_attempts"] = data.legacyBlockAttempts;
    mapDiagnostics["ph_status"] = data.phStatus;
    mapDiagnostics["ph_attempts"] = data.phAttempts;
    mapDiagnostics["npk_status"] = data.npkStatus;
    mapDiagnostics["npk_attempts"] = data.npkAttempts;
    bool hasExternalSource = false;
    JsonObject externalSources = doc["external_sources"].to<JsonObject>();
    if (data.tempFromExternalSensor) {
        externalSources["temp"] = "ds18b20";
        externalSources["temp_raw"] = data.rawTemp;
        externalSources["temp_conversion"] = "raw/16.0";
        hasExternalSource = true;
    }
    if (data.humFromExternalSensor) {
        externalSources["hum"] = "soil_moisture_v1_2";
        externalSources["hum_read_ok"] = data.externalHumReadOk;
        externalSources["hum_value_valid"] = data.humValueValid;
        externalSources["hum_calibration_valid"] = data.externalHumCalibrationValid;
        externalSources["hum_calibration_is_default"] = data.externalHumCalibrationIsDefault;
        externalSources["hum_calibration_status"] = !data.externalHumReadOk
                                                           ? "read_error"
                                                           : (!data.externalHumCalibrationValid
                                                                  ? "uncalibrated"
                                                                  : (data.externalHumCalibrationIsDefault
                                                                         ? "provisional_default"
                                                                         : "field_calibrated"));
        externalSources["hum_calibration_profile"] = data.externalHumCalibrationProfile;
        externalSources["hum_calibration_source"] = data.externalHumCalibrationSource;
        externalSources["hum_raw_adc"] = data.externalHumRaw;
        externalSources["hum_raw_min"] = data.externalHumRawMin;
        externalSources["hum_raw_max"] = data.externalHumRawMax;
        externalSources["hum_voltage_mv"] = data.externalHumVoltageMv;
        if (data.externalHumSampleValid) {
            externalSources["hum_percent"] = data.externalHumPercent;
        } else {
            externalSources["hum_percent"] = nullptr;
        }
        externalSources["hum_state"] = data.externalHumState;
        externalSources["hum_error"] = data.externalHumError;
        externalSources["hum_conversion"] = "manufacturer_two_point_relative";
        externalSources["hum_install_depth_cm_min"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN;
        externalSources["hum_install_depth_cm_max"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX;
        hasExternalSource = true;

        JsonObject moistureCalibration = doc["moisture_calibration"].to<JsonObject>();
        moistureCalibration["status"] = !data.externalHumReadOk
                                             ? "read_error"
                                             : (!data.externalHumCalibrationValid
                                                    ? "uncalibrated"
                                                    : (data.externalHumCalibrationIsDefault
                                                           ? "provisional_default"
                                                           : "field_calibrated"));
        moistureCalibration["is_default"] = data.externalHumCalibrationIsDefault;
        moistureCalibration["profile"] = data.externalHumCalibrationProfile;
        moistureCalibration["source"] = data.externalHumCalibrationSource;
        moistureCalibration["method"] = "manufacturer_two_point_relative";
        moistureCalibration["value_semantics"] = "relative_index_0_100_not_vwc";
        moistureCalibration["dry_adc"] = SOIL_MOISTURE_AIR_ADC;
        moistureCalibration["wet_adc"] = SOIL_MOISTURE_WATER_ADC;
        moistureCalibration["manufacturer_dry_10bit"] = SOIL_MOISTURE_MANUFACTURER_DRY_10BIT;
        moistureCalibration["manufacturer_wet_10bit"] = SOIL_MOISTURE_MANUFACTURER_WET_10BIT;
        moistureCalibration["target_depth_cm"] = SOIL_MOISTURE_CALIBRATION_TARGET_DEPTH_CM;
        moistureCalibration["install_depth_cm_min"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN;
        moistureCalibration["install_depth_cm_max"] = SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX;
        moistureCalibration["latest_read_ok"] = data.externalHumReadOk;
        moistureCalibration["latest_sample_valid"] = data.externalHumSampleValid;
        if (data.externalHumReadOk) {
            moistureCalibration["latest_raw_adc"] = data.externalHumRaw;
            moistureCalibration["latest_raw_min"] = data.externalHumRawMin;
            moistureCalibration["latest_raw_max"] = data.externalHumRawMax;
            moistureCalibration["latest_voltage_mv"] = data.externalHumVoltageMv;
        } else {
            moistureCalibration["latest_raw_adc"] = nullptr;
            moistureCalibration["latest_raw_min"] = nullptr;
            moistureCalibration["latest_raw_max"] = nullptr;
            moistureCalibration["latest_voltage_mv"] = nullptr;
        }
        if (data.externalHumSampleValid) {
            moistureCalibration["latest_percent"] = data.externalHumPercent;
        } else {
            moistureCalibration["latest_percent"] = nullptr;
        }
        moistureCalibration["latest_state"] = data.externalHumState;
        moistureCalibration["latest_error"] = data.externalHumError;
        moistureCalibration["recalibration_policy"] = "replace_profile_after_long_term_field_observations";
    }
    if (!hasExternalSource) {
        doc.remove("external_sources");
    }
    // Keep the field names stable. Unsupported NPK channels may still have a
    // policy default, while the external DS18B20/moisture sources are emitted
    // only when their semantic values are valid. Their source/error metadata
    // remains present even when the value is null.
    if (data.tempReadOk || data.tempFromExternalSensor || data.tempDefaultedToZero) doc["temp"] = data.temp; else doc["temp"] = nullptr;
    if (data.humReadOk ||
        (data.humFromExternalSensor && data.humValueValid) ||
        data.humDefaultedToZero) {
        doc["hum"] = data.hum;
    } else {
        doc["hum"] = nullptr;
    }
    if (data.phReadOk) doc["ph"] = data.ph; else doc["ph"] = nullptr;
    if (data.ecReadOk || data.ecDerivedFromNpk) doc["ec"] = data.ec; else doc["ec"] = nullptr;
    if (data.nReadOk) doc["N"] = data.n; else doc["N"] = nullptr;
    if (data.pReadOk) doc["P"] = data.p; else doc["P"] = nullptr;
    if (data.kReadOk) doc["K"] = data.k; else doc["K"] = nullptr;

    String jsonString;
    serializeJson(doc, jsonString);
    return jsonString;
}
