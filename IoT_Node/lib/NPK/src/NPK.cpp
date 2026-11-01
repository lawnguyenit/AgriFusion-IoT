#include "NPK.h"

#include "Config.h"

namespace {
static const uint8_t NPK_MAX_ATTEMPTS = 3;  // 1 initial + 2 retries
static const uint32_t NPK_RESPONSE_TIMEOUT_MS = 2000;
}

MyNPK::MyNPK() {}

void MyNPK::begin(Stream &serialPort) {
    _serial = &serialPort;
    _node.begin(1, serialPort);
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

    uint32_t readStartMs = millis();
    uint8_t attempts = 0;
    uint8_t status = ModbusMaster::ku8MBResponseTimedOut;

    while (attempts < NPK_MAX_ATTEMPTS) {
        attempts++;
        status = _node.readHoldingRegisters(0x0000, 7);
        if (status == ModbusMaster::ku8MBSuccess) {
            break;
        }
    }

    result.readDurationMs = millis() - readStartMs;
    result.retryCount = attempts > 0 ? (attempts - 1) : 0;
    result.errorCodeRaw = status;
    result.readOk = (status == ModbusMaster::ku8MBSuccess);
    result.error = !result.readOk;

    if (result.readOk) {
        result.hum = _node.getResponseBuffer(0) / 10.0f;
        result.temp = _node.getResponseBuffer(1) / 10.0f;
        result.ec = _node.getResponseBuffer(2);
        result.ph = _node.getResponseBuffer(3) / 10.0f;
        result.n = _node.getResponseBuffer(4);
        result.p = _node.getResponseBuffer(5);
        result.k = _node.getResponseBuffer(6);
        result.crcOk = true;
        result.frameOk = true;
        CUS_DBGLN("-> [NPK] Read success");
    } else {
        if (status == ModbusMaster::ku8MBInvalidCRC) {
            result.crcOk = false;
            result.frameOk = false;
        } else if (status == ModbusMaster::ku8MBResponseTimedOut) {
            result.crcOk = false;
            result.frameOk = false;
        } else if (status <= ModbusMaster::ku8MBSlaveDeviceFailure) {
            // Slave exception responses are valid protocol frames.
            result.crcOk = true;
            result.frameOk = true;
        } else {
            result.crcOk = false;
            result.frameOk = false;
        }

        CUS_DBGF("-> [NPK] Read fail code=0x%02X (%s), retry=%u, duration=%lu ms\n",
                 status, errorCodeToString(status),
                 (unsigned)result.retryCount, (unsigned long)result.readDurationMs);
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
    bool nutrientSignal = (data.ec > 0) || (data.n > 0) || (data.p > 0) || (data.k > 0) || (data.hum > 0.01f);
    bool chemistryPlausible = (data.ph >= 3.0f && data.ph <= 10.0f);
    bool thermalPlausible = (data.temp >= -10.0f && data.temp <= 85.0f);
    bool npkValuesValid = data.readOk && nutrientSignal && chemistryPlausible && thermalPlausible;

    doc["sensor_type"] = "npk7in1";
    doc["sensor_id"] = "npk_7in1_1";

    doc["read_ok"] = data.readOk;
    doc["error_code"] = errorCodeToString(data.errorCodeRaw);
    doc["error_code_raw"] = data.errorCodeRaw;
    doc["retry_count"] = data.retryCount;
    doc["timeout_ms"] = data.timeoutMs;
    doc["read_duration_ms"] = data.readDurationMs;
    doc["crc_ok"] = data.crcOk;
    doc["frame_ok"] = data.frameOk;

    doc["sample_interval_ms"] = sampleIntervalMs;
    doc["consecutive_fail_count"] = consecutiveFailCount;
    doc["recovered_after_fail"] = recoveredAfterFail;
    doc["fail_streak_before_recover"] = failStreakBeforeRecover;
    doc["sensor_alarm"] = sensorAlarm;
    doc["npk_values_valid"] = npkValuesValid;
    doc["npk_signal_present"] = nutrientSignal;

    // Always publish NPK value fields so upstream schemas stay stable.
    // On failed reads these remain default-initialized (typically 0).
    doc["temp"] = data.temp;
    doc["hum"] = data.hum;
    doc["ph"] = data.ph;
    doc["ec"] = data.ec;
    doc["N"] = data.n;
    doc["P"] = data.p;
    doc["K"] = data.k;

    String jsonString;
    serializeJson(doc, jsonString);
    return jsonString;
}
