#include "Sht30Service.h"

#include <ArduinoJson.h>
#include <Adafruit_SHT31.h>
#include <Wire.h>

#include "Config.h"

namespace {
Adafruit_SHT31 gSht30;
}

Sht30Service::Sht30Service(uint8_t sdaPin, uint8_t sclPin, uint8_t address, uint32_t retryInitMs)
    : _sdaPin(sdaPin), _sclPin(sclPin), _address(address), _retryInitMs(retryInitMs) {}

void Sht30Service::ensureWireReady(bool forceRefresh) {
    if (_wireReady && !forceRefresh) {
        return;
    }

    Wire.begin(_sdaPin, _sclPin, APP_SHT30_WIRE_CLOCK_HZ);
    Wire.setTimeOut(APP_SHT30_WIRE_TIMEOUT_MS);
    delay(APP_SHT30_POST_WIRE_BEGIN_DELAY_MS);
    _wireReady = true;
}

bool Sht30Service::isAddressReachable(bool refreshBus) {
    ensureWireReady(refreshBus);
    Wire.beginTransmission(_address);
    uint8_t error = Wire.endTransmission();
    return error == 0;
}

bool Sht30Service::tryInit(bool force) {
    uint32_t now = millis();
    if (!force && _lastInitAttemptMs != 0 && (now - _lastInitAttemptMs) < _retryInitMs) {
        return _ready;
    }
    _lastInitAttemptMs = now;

    ensureWireReady(force);
    if (!isAddressReachable(false)) {
        _ready = false;
        CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X => BUS_MISSING\n",
                 _sdaPin,
                 _sclPin,
                 _address);
        return false;
    }

    _ready = false;
    for (uint8_t attempt = 1; attempt <= (uint8_t)APP_SHT30_INIT_ATTEMPTS; ++attempt) {
        _ready = gSht30.begin(_address);
        if (_ready) {
            gSht30.heater(false);
            _consecutiveInvalidCount = 0;
            CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X attempt=%u/%u => OK\n",
                     _sdaPin,
                     _sclPin,
                     _address,
                     attempt,
                     (unsigned)APP_SHT30_INIT_ATTEMPTS);
            return true;
        }

        if (attempt < (uint8_t)APP_SHT30_INIT_ATTEMPTS) {
            delay(APP_SHT30_INIT_RETRY_DELAY_MS);
        }
    }

    CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X attempts=%u => FAIL\n",
             _sdaPin,
             _sclPin,
             _address,
             (unsigned)APP_SHT30_INIT_ATTEMPTS);
    return _ready;
}

bool Sht30Service::ready() const {
    return _ready;
}

String Sht30Service::buildJsonPayload(const char *sensorType,
                                      const char *sensorId,
                                      const char *edgeSystem,
                                      const char *edgeSystemId,
                                      const char *edgeStream,
                                      uint8_t maxReadAttempts,
                                      uint32_t retryDelayMs,
                                      uint32_t maxWaitMs) {
    JsonDocument doc;
    doc["sensor_type"] = sensorType ? sensorType : "sht30_air";
    doc["sensor_id"] = sensorId ? sensorId : "sht30_1";
    doc["edge_system"] = edgeSystem ? edgeSystem : "";
    doc["edge_system_id"] = edgeSystemId ? edgeSystemId : "";
    doc["edge_stream"] = edgeStream ? edgeStream : "sht30";
    doc["sht_addr"] = "0x44";
    doc["sht_sda"] = _sdaPin;
    doc["sht_scl"] = _sclPin;
    doc["sht_retry_limit"] = maxReadAttempts;
    doc["sht_retry_delay_ms"] = retryDelayMs;
    doc["sht_max_wait_ms"] = maxWaitMs;

    if (!_ready) {
        doc["sht_read_ok"] = false;
        doc["sht_sample_valid"] = false;
        doc["sht_error"] = "not_initialized";
        doc["sht_retry_count"] = 0;
        doc["sht_read_elapsed_ms"] = 0;
        doc["sht_invalid_streak"] = _consecutiveInvalidCount;
    } else {
        uint32_t startMs = millis();
        uint8_t attempts = 0;
        bool valid = false;
        bool readOk = false;
        float t = NAN;
        float h = NAN;
        const float TEMP_MIN_C = -20.0f;
        const float TEMP_MAX_C = 80.0f;
        const float HUM_MIN_PCT = 0.0f;
        const float HUM_MAX_PCT = 100.0f;
        const char *lastError = "nan_read";

        while (attempts < maxReadAttempts) {
            uint32_t elapsed = millis() - startMs;
            if (elapsed >= maxWaitMs) {
                lastError = "read_timeout_window";
                break;
            }

            attempts++;
            readOk = gSht30.readBoth(&t, &h);
            if (!readOk) {
                lastError = "nan_read";
            } else if (t < TEMP_MIN_C || t > TEMP_MAX_C || h < HUM_MIN_PCT || h > HUM_MAX_PCT) {
                lastError = "out_of_range";
            } else {
                valid = true;
                lastError = "ok";
                break;
            }

            if (attempts < maxReadAttempts) {
                gSht30.reset();
                delay(20);
            }
            uint32_t afterReadMs = millis() - startMs;
            if (attempts < maxReadAttempts && (afterReadMs + retryDelayMs) < maxWaitMs) {
                delay(retryDelayMs);
            }
        }

        doc["sht_read_ok"] = readOk;
        doc["sht_sample_valid"] = valid;
        doc["sht_retry_count"] = attempts > 0 ? (attempts - 1) : 0;
        doc["sht_read_elapsed_ms"] = (millis() - startMs);

        if (valid) {
            _consecutiveInvalidCount = 0;
            doc["sht_temp_c"] = t;
            doc["sht_hum_pct"] = h;
            doc["sht_error"] = "ok";
        } else {
            _consecutiveInvalidCount++;
            doc["sht_error"] = lastError;
            if (_consecutiveInvalidCount >= APP_SHT30_FORCE_REINIT_STREAK) {
                _ready = false;
            }
        }
        doc["sht_invalid_streak"] = _consecutiveInvalidCount;
    }

    String out;
    serializeJson(doc, out);
    return out;
}
