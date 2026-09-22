#include "Sht30Service.h"

#include <ArduinoJson.h>
#include <Wire.h>

#include "Config.h"

namespace {
constexpr uint16_t kSoftResetCommand = 0x30A2;
constexpr uint16_t kMeasureHighRepeatCommand = 0x2400;
constexpr uint8_t kMeasurementFrameBytes = 6U;

uint8_t crc8(const uint8_t *data, size_t length) {
    uint8_t crc = 0xFF;
    for (size_t index = 0; index < length; ++index) {
        crc ^= data[index];
        for (uint8_t bit = 0; bit < 8U; ++bit) {
            crc = (crc & 0x80U) ? static_cast<uint8_t>((crc << 1U) ^ 0x31U)
                                : static_cast<uint8_t>(crc << 1U);
        }
    }
    return crc;
}

bool measurementIsInRange(float temperatureC, float humidityPct) {
    return !isnan(temperatureC) && !isnan(humidityPct) &&
           temperatureC >= -20.0f && temperatureC <= 80.0f &&
           humidityPct >= 0.0f && humidityPct <= 100.0f;
}
}

Sht30Service::Sht30Service(uint8_t sdaPin, uint8_t sclPin, uint8_t address, uint32_t retryInitMs)
    : _sdaPin(sdaPin), _sclPin(sclPin), _address(address), _retryInitMs(retryInitMs) {}

void Sht30Service::clearMeasurementDiagnostics() {
    _lastMeasurementTransportOk = false;
    _lastMeasurementAttempted = false;
    _lastFrameOk = false;
    _lastTemperatureCrcOk = false;
    _lastHumidityCrcOk = false;
    _lastReceivedBytes = 0;
    _lastRawTemperature = 0;
    _lastRawHumidity = 0;
    _lastMeasurementI2cError = 0xFF;
    _lastMeasurementError = "not_attempted";
}

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
    _lastI2cError = Wire.endTransmission();
    return _lastI2cError == 0;
}

bool Sht30Service::sendCommand(uint16_t command, uint8_t &i2cError) {
    Wire.beginTransmission(_address);
    Wire.write(static_cast<uint8_t>(command >> 8U));
    Wire.write(static_cast<uint8_t>(command & 0xFFU));
    i2cError = Wire.endTransmission();
    _lastMeasurementI2cError = i2cError;
    return i2cError == 0;
}

bool Sht30Service::readRawMeasurement(float *temperatureOut, float *humidityOut) {
    if (temperatureOut) {
        *temperatureOut = NAN;
    }
    if (humidityOut) {
        *humidityOut = NAN;
    }
    clearMeasurementDiagnostics();
    _lastMeasurementAttempted = true;

    uint8_t i2cError = 0xFF;
    if (!sendCommand(kMeasureHighRepeatCommand, i2cError)) {
        _lastMeasurementError = "measurement_command_failed";
        CUS_DBGF("[SHT30][RAW][SERVICE] addr=0x%02X cmd=0x%04X command=FAIL i2c_error=%u\n",
                 _address,
                 kMeasureHighRepeatCommand,
                 static_cast<unsigned>(i2cError));
        return false;
    }

    delay(APP_SHT30_MEASUREMENT_WAIT_MS);

    uint8_t frame[kMeasurementFrameBytes] = {};
    size_t received = Wire.requestFrom(static_cast<uint8_t>(_address),
                                       static_cast<size_t>(kMeasurementFrameBytes),
                                       true);
    size_t copied = 0;
    while (Wire.available() && copied < kMeasurementFrameBytes) {
        frame[copied++] = static_cast<uint8_t>(Wire.read());
    }

    _lastReceivedBytes = static_cast<uint8_t>(copied);
    _lastFrameOk = received == kMeasurementFrameBytes && copied == kMeasurementFrameBytes;
    _lastMeasurementTransportOk = _lastFrameOk;

    if (_lastFrameOk) {
        _lastRawTemperature = static_cast<uint16_t>((static_cast<uint16_t>(frame[0]) << 8U) | frame[1]);
        _lastRawHumidity = static_cast<uint16_t>((static_cast<uint16_t>(frame[3]) << 8U) | frame[4]);
        _lastTemperatureCrcOk = frame[2] == crc8(frame, 2U);
        _lastHumidityCrcOk = frame[5] == crc8(frame + 3U, 2U);
    }

    if (!_lastFrameOk) {
        _lastMeasurementTransportOk = false;
        _lastMeasurementError = "measurement_frame_short";
    } else if (!_lastTemperatureCrcOk || !_lastHumidityCrcOk) {
        _lastMeasurementTransportOk = false;
        _lastMeasurementError = "measurement_crc_failed";
    } else {
        if (temperatureOut) {
            *temperatureOut = -45.0f +
                              (175.0f * static_cast<float>(_lastRawTemperature) / 65535.0f);
        }
        if (humidityOut) {
            *humidityOut = 100.0f * static_cast<float>(_lastRawHumidity) / 65535.0f;
        }
        _lastMeasurementError = "ok";
    }

    CUS_DBGF("[SHT30][RAW][SERVICE] addr=0x%02X cmd=0x%04X received=%u/%u frame=%d crc=%d temp_crc=%d hum_crc=%d bytes=%02X %02X %02X %02X %02X %02X raw_temp=0x%04X raw_hum=0x%04X error=%s\n",
             _address,
             kMeasureHighRepeatCommand,
             static_cast<unsigned>(copied),
             static_cast<unsigned>(kMeasurementFrameBytes),
             _lastFrameOk ? 1 : 0,
             (_lastTemperatureCrcOk && _lastHumidityCrcOk) ? 1 : 0,
             _lastTemperatureCrcOk ? 1 : 0,
             _lastHumidityCrcOk ? 1 : 0,
             frame[0],
             frame[1],
             frame[2],
             frame[3],
             frame[4],
             frame[5],
             _lastRawTemperature,
             _lastRawHumidity,
             _lastMeasurementError.c_str());
    return _lastMeasurementTransportOk;
}

void Sht30Service::writeMeasurementDiagnostics(JsonDocument &doc) {
    doc["sht_measurement_transport_ok"] = _lastMeasurementTransportOk;
    doc["sht_frame_ok"] = _lastFrameOk;
    doc["sht_temp_crc_ok"] = _lastTemperatureCrcOk;
    doc["sht_hum_crc_ok"] = _lastHumidityCrcOk;
    doc["sht_received_bytes"] = _lastReceivedBytes;
    doc["sht_measurement_i2c_error"] = _lastMeasurementI2cError;
    doc["sht_measurement_error"] = _lastMeasurementError;
    doc["sht_raw_values_available"] = _lastFrameOk;
    if (_lastFrameOk) {
        doc["sht_raw_temp"] = _lastRawTemperature;
        doc["sht_raw_hum"] = _lastRawHumidity;
    } else {
        doc["sht_raw_temp"] = nullptr;
        doc["sht_raw_hum"] = nullptr;
    }
}

bool Sht30Service::tryInit(bool force) {
    uint32_t now = millis();
    if (!force && _lastInitAttemptMs != 0 && (now - _lastInitAttemptMs) < _retryInitMs) {
        return _ready;
    }
    _lastInitAttemptMs = now;
    _lastInitAttempts = 0;
    _lastInitProbeReadOk = false;
    _lastInitProbeTemperature = NAN;
    _lastInitProbeHumidity = NAN;
    _lastInitError = "starting";
    clearMeasurementDiagnostics();

    ensureWireReady(force);
    if (!isAddressReachable(false)) {
        _ready = false;
        _lastInitError = "bus_missing";
        CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X wire_hz=%lu wire_timeout=%lu post_begin=%lu => BUS_MISSING i2c_error=%u\n",
                 _sdaPin,
                 _sclPin,
                 _address,
                 (unsigned long)APP_SHT30_WIRE_CLOCK_HZ,
                 (unsigned long)APP_SHT30_WIRE_TIMEOUT_MS,
                 (unsigned long)APP_SHT30_POST_WIRE_BEGIN_DELAY_MS,
                 (unsigned)_lastI2cError);
        return false;
    }

    _ready = false;
    for (uint8_t attempt = 1; attempt <= (uint8_t)APP_SHT30_INIT_ATTEMPTS; ++attempt) {
        _lastInitAttempts = attempt;
        uint8_t resetError = 0xFF;
        bool resetOk = sendCommand(kSoftResetCommand, resetError);
        if (resetOk) {
            delay(APP_SHT30_SOFT_RESET_WAIT_MS);
        }

        float probeTemperature = NAN;
        float probeHumidity = NAN;
        bool probeReadOk = resetOk && readRawMeasurement(&probeTemperature, &probeHumidity);
        _lastInitProbeReadOk = probeReadOk;
        _lastInitProbeTemperature = probeTemperature;
        _lastInitProbeHumidity = probeHumidity;
        if (probeReadOk && measurementIsInRange(probeTemperature, probeHumidity)) {
            _ready = true;
            _consecutiveInvalidCount = 0;
            _lastInitError = "ok";
            CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X attempt=%u/%u => OK probe_temp=%.2f probe_hum=%.2f\n",
                     _sdaPin,
                     _sclPin,
                     _address,
                     attempt,
                     (unsigned)APP_SHT30_INIT_ATTEMPTS,
                     probeTemperature,
                     probeHumidity);
            return true;
        }

        _ready = false;
        if (!resetOk) {
            _lastInitError = "reset_failed";
        } else if (!probeReadOk) {
            _lastInitError = _lastMeasurementError;
        } else {
            _lastInitError = (_lastRawTemperature == 0 && _lastRawHumidity == 0)
                                 ? "measurement_invalid_zero_frame"
                                 : "measurement_invalid";
        }
        CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X attempt=%u/%u => MEASURE_FAIL read_ok=%d temp=%.2f hum=%.2f raw_temp=0x%04X raw_hum=0x%04X frame=%d crc=%d error=%s\n",
                 _sdaPin,
                 _sclPin,
                 _address,
                 attempt,
                 (unsigned)APP_SHT30_INIT_ATTEMPTS,
                 probeReadOk ? 1 : 0,
                 probeTemperature,
                 probeHumidity,
                 _lastRawTemperature,
                 _lastRawHumidity,
                 _lastFrameOk ? 1 : 0,
                 (_lastTemperatureCrcOk && _lastHumidityCrcOk) ? 1 : 0,
                 _lastInitError.c_str());

        if (attempt < (uint8_t)APP_SHT30_INIT_ATTEMPTS) {
            delay(APP_SHT30_INIT_RETRY_DELAY_MS);
        }
    }

    CUS_DBGF("[SHT30] init SDA=%d SCL=%d addr=0x%02X attempts=%u => FAIL error=%s ack=%d i2c_error=%u probe_read_ok=%d probe_temp=%.2f probe_hum=%.2f raw_temp=0x%04X raw_hum=0x%04X frame=%d crc=%d\n",
             _sdaPin,
             _sclPin,
             _address,
             (unsigned)APP_SHT30_INIT_ATTEMPTS,
             _lastInitError.c_str(),
             _lastI2cError == 0 ? 1 : 0,
             (unsigned)_lastI2cError,
             _lastInitProbeReadOk ? 1 : 0,
             _lastInitProbeTemperature,
             _lastInitProbeHumidity,
             _lastRawTemperature,
             _lastRawHumidity,
             _lastFrameOk ? 1 : 0,
             (_lastTemperatureCrcOk && _lastHumidityCrcOk) ? 1 : 0);
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
    char addressText[7];
    snprintf(addressText, sizeof(addressText), "0x%02X", _address);
    doc["sht_addr"] = addressText;
    doc["sht_sda"] = _sdaPin;
    doc["sht_scl"] = _sclPin;
    doc["sht_retry_limit"] = maxReadAttempts;
    doc["sht_retry_delay_ms"] = retryDelayMs;
    doc["sht_max_wait_ms"] = maxWaitMs;
    doc["sht_i2c_address_ack"] = _lastI2cError == 0;
    doc["sht_i2c_error"] = _lastI2cError;
    doc["sht_init_attempts"] = _lastInitAttempts;
    doc["sht_init_error"] = _lastInitError;
    doc["sht_init_probe_read_ok"] = _lastInitProbeReadOk;
    if (isnan(_lastInitProbeTemperature)) {
        doc["sht_init_probe_temp_c"] = nullptr;
    } else {
        doc["sht_init_probe_temp_c"] = _lastInitProbeTemperature;
    }
    if (isnan(_lastInitProbeHumidity)) {
        doc["sht_init_probe_hum_pct"] = nullptr;
    } else {
    doc["sht_init_probe_hum_pct"] = _lastInitProbeHumidity;
    }

    writeMeasurementDiagnostics(doc);

    if (!_ready) {
        // `read_ok` reports whether a complete measurement frame was read,
        // not whether the decoded values passed the semantic range check.
        // This preserves a CRC-valid -45/0 frame as an observable fault.
        const bool lastReadOk = _lastMeasurementAttempted
                                    ? _lastMeasurementTransportOk
                                    : _lastInitProbeReadOk;
        const bool valuesAvailable = _lastFrameOk &&
                                     _lastTemperatureCrcOk &&
                                     _lastHumidityCrcOk;
        float observedTemperature = NAN;
        float observedHumidity = NAN;
        if (valuesAvailable) {
            observedTemperature = -45.0f +
                                  (175.0f * static_cast<float>(_lastRawTemperature) / 65535.0f);
            observedHumidity = 100.0f *
                               static_cast<float>(_lastRawHumidity) / 65535.0f;
        }
        doc["sht_read_ok"] = lastReadOk;
        doc["sht_sample_valid"] = false;
        doc["sht_value_valid"] = false;
        doc["sht_values_available"] = valuesAvailable;
        doc["sht_error"] = _lastInitError.length() ? _lastInitError : "not_initialized";
        doc["sht_retry_count"] = 0;
        doc["sht_read_elapsed_ms"] = 0;
        doc["sht_invalid_streak"] = _consecutiveInvalidCount;
        if (valuesAvailable) {
            doc["sht_temp_c"] = observedTemperature;
            doc["sht_hum_pct"] = observedHumidity;
            doc["sht_observed_temp_c"] = observedTemperature;
            doc["sht_observed_hum_pct"] = observedHumidity;
        } else {
            doc["sht_temp_c"] = nullptr;
            doc["sht_hum_pct"] = nullptr;
            doc["sht_observed_temp_c"] = nullptr;
            doc["sht_observed_hum_pct"] = nullptr;
        }
        CUS_DBGF("[SHT30][READ] ready=0 read_ok=%d sample_valid=0 retry=0 elapsed=0 error=%s init_attempts=%u ack=%d i2c_error=%u last_frame=%d observed_temp=%.2f observed_hum=%.2f\n",
                 lastReadOk ? 1 : 0,
                 _lastInitError.length() ? _lastInitError.c_str() : "not_initialized",
                 (unsigned)_lastInitAttempts,
                 _lastI2cError == 0 ? 1 : 0,
                 (unsigned)_lastI2cError,
                 _lastFrameOk ? 1 : 0,
                 observedTemperature,
                 observedHumidity);
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
        String lastError = "nan_read";

        while (attempts < maxReadAttempts) {
            uint32_t elapsed = millis() - startMs;
            if (elapsed >= maxWaitMs) {
                lastError = "read_timeout_window";
                break;
            }

            attempts++;
            readOk = readRawMeasurement(&t, &h);
            if (!readOk) {
                lastError = _lastMeasurementError;
            } else if (t < TEMP_MIN_C || t > TEMP_MAX_C || h < HUM_MIN_PCT || h > HUM_MAX_PCT) {
                lastError = (_lastRawTemperature == 0 && _lastRawHumidity == 0)
                                 ? "measurement_invalid_zero_frame"
                                 : "out_of_range";
            } else {
                valid = true;
                lastError = "ok";
                break;
            }

            if (attempts < maxReadAttempts) {
                uint8_t resetError = 0xFF;
                if (sendCommand(kSoftResetCommand, resetError)) {
                    delay(APP_SHT30_SOFT_RESET_WAIT_MS);
                } else {
                    lastError = "reset_failed";
                }
                delay(APP_SHT30_RETRY_SETTLE_DELAY_MS);
            }
            uint32_t afterReadMs = millis() - startMs;
            if (attempts < maxReadAttempts && (afterReadMs + retryDelayMs) < maxWaitMs) {
                delay(retryDelayMs);
            }
        }

        doc["sht_read_ok"] = readOk;
        doc["sht_sample_valid"] = valid;
        doc["sht_value_valid"] = valid;
        doc["sht_values_available"] = readOk && !isnan(t) && !isnan(h);
        doc["sht_retry_count"] = attempts > 0 ? (attempts - 1) : 0;
        doc["sht_read_elapsed_ms"] = (millis() - startMs);

        if (readOk && !isnan(t) && !isnan(h)) {
            // Keep decoded transport observations even when semantic range
            // validation rejects them. Canonical values remain null; the
            // observed fields make a -45/0 frame auditable downstream.
            doc["sht_temp_c"] = t;
            doc["sht_hum_pct"] = h;
            doc["sht_observed_temp_c"] = t;
            doc["sht_observed_hum_pct"] = h;
        } else {
            doc["sht_temp_c"] = nullptr;
            doc["sht_hum_pct"] = nullptr;
            doc["sht_observed_temp_c"] = nullptr;
            doc["sht_observed_hum_pct"] = nullptr;
        }

        if (valid) {
            _consecutiveInvalidCount = 0;
            doc["sht_error"] = "ok";
        } else {
            _consecutiveInvalidCount++;
            doc["sht_error"] = lastError;
            if (_consecutiveInvalidCount >= APP_SHT30_FORCE_REINIT_STREAK) {
                _ready = false;
            }
        }
        doc["sht_invalid_streak"] = _consecutiveInvalidCount;

        CUS_DBGF("[SHT30][READ] ready=1 read_ok=%d sample_valid=%d retry=%u elapsed=%lu error=%s",
                 readOk ? 1 : 0,
                 valid ? 1 : 0,
                 attempts > 0 ? (unsigned)(attempts - 1) : 0U,
                 (unsigned long)(millis() - startMs),
                 lastError.c_str());
        if (readOk && !isnan(t) && !isnan(h)) {
            CUS_DBGF(" temp=%.2f hum=%.2f", t, h);
        }
        CUS_DBGF(" invalid_streak=%lu\n", (unsigned long)_consecutiveInvalidCount);

        writeMeasurementDiagnostics(doc);
    }

    String out;
    serializeJson(doc, out);
    return out;
}
