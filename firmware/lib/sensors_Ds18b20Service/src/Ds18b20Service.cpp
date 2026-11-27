#include "Ds18b20Service.h"

#include <ArduinoJson.h>
#include <cstring>

namespace {
constexpr uint8_t kDs18b20FamilyCode = 0x28U;
constexpr uint8_t kScratchpadBytes = 9U;
constexpr float kMinimumTemperatureC = -55.0f;
constexpr float kMaximumTemperatureC = 125.0f;
}

Ds18b20Service::Ds18b20Service(uint8_t dataPin, uint32_t retryInitMs)
    : _oneWire(dataPin), _dataPin(dataPin), _retryInitMs(retryInitMs) {}

void Ds18b20Service::prepareBus() {
    // Retained for the verified no-resistor bench setup. A normal installation
    // should still use an external pull-up on DQ.
    pinMode(_dataPin, OUTPUT);
    digitalWrite(_dataPin, HIGH);
    delayMicroseconds(DS18B20_BUS_PRECHARGE_US);
#if DS18B20_USE_INTERNAL_PULLUP
    pinMode(_dataPin, INPUT_PULLUP);
#else
    pinMode(_dataPin, INPUT);
#endif
}

bool Ds18b20Service::tryInit(bool force) {
    const uint32_t now = millis();
    if (!force && _ready) {
        return true;
    }
    if (!force && _lastInitAttemptMs != 0U &&
        (now - _lastInitAttemptMs) < _retryInitMs) {
        return false;
    }

    _lastInitAttemptMs = now;
    _ready = false;
    _singleDropFallbackReady = false;
    _busStatus = {};
    memset(_addresses, 0, sizeof(_addresses));
    _lastInitError = "starting";

    prepareBus();
    _busStatus.idleHigh = digitalRead(_dataPin) == HIGH;
    _busStatus.presenceDetected = _oneWire.reset();
    _oneWire.reset_search();

    uint8_t candidate[8] = {};
    while (_oneWire.search(candidate)) {
        const bool familyOk = candidate[0] == kDs18b20FamilyCode;
        const bool crcOk = OneWire::crc8(candidate, 7U) == candidate[7];
        if (familyOk && crcOk && _busStatus.deviceCount < DS18B20_MAX_DEVICES) {
            memcpy(_addresses[_busStatus.deviceCount], candidate, sizeof(candidate));
            ++_busStatus.deviceCount;
        }
    }

    _busStatus.romFound = _busStatus.deviceCount > 0U;
    _singleDropFallbackReady = _busStatus.deviceCount == 0U &&
                               _busStatus.presenceDetected &&
                               DS18B20_SINGLE_DROP_FALLBACK;
    _ready = _busStatus.romFound || _singleDropFallbackReady;
    _lastInitError = _ready
                         ? "ok"
                         : (_busStatus.presenceDetected ? "rom_not_found" : "bus_missing");

    CUS_DBGF("[DS18B20][SERVICE] init gpio=%u idle_high=%d presence=%d devices=%u fallback=%d error=%s\n",
             static_cast<unsigned>(_dataPin),
             _busStatus.idleHigh ? 1 : 0,
             _busStatus.presenceDetected ? 1 : 0,
             static_cast<unsigned>(_busStatus.deviceCount),
             _singleDropFallbackReady ? 1 : 0,
             _lastInitError.c_str());
    return _ready;
}

bool Ds18b20Service::ready() const {
    return _ready;
}

const Ds18b20BusStatus &Ds18b20Service::busStatus() const {
    return _busStatus;
}

uint8_t Ds18b20Service::deviceCount() const {
    return _busStatus.deviceCount;
}

const uint8_t *Ds18b20Service::deviceAddress(uint8_t index) const {
    if (index >= _busStatus.deviceCount) {
        return nullptr;
    }
    return _addresses[index];
}

bool Ds18b20Service::readPrimary(Ds18b20Reading &reading) {
    if (!_ready) {
        reading = {};
        return false;
    }

    return _busStatus.deviceCount > 0U
               ? readDevice(0U, reading)
               : readSingleDrop(reading);
}

bool Ds18b20Service::readTemperature(const uint8_t *address,
                                     bool selectRom,
                                     Ds18b20Reading &reading) {
    reading = {};
    prepareBus();
    if (!_oneWire.reset()) {
        return false;
    }
    reading.presenceDetected = true;

    if (selectRom) {
        _oneWire.select(address);
    } else {
        _oneWire.skip();
    }
    _oneWire.write(0x44U, DS18B20_USE_STRONG_PULLUP ? 1U : 0U);
    delay(DS18B20_CONVERSION_WAIT_MS);
    _oneWire.depower();

    prepareBus();
    if (!_oneWire.reset()) {
        return false;
    }

    if (selectRom) {
        _oneWire.select(address);
    } else {
        _oneWire.skip();
    }
    _oneWire.write(0xBEU);
    for (uint8_t index = 0U; index < kScratchpadBytes; ++index) {
        reading.scratchpad[index] = _oneWire.read();
    }
    _oneWire.depower();

    reading.scratchpadCrcOk = OneWire::crc8(reading.scratchpad, 8U) ==
                              reading.scratchpad[8];
    reading.rawTemperature = static_cast<int16_t>(
        static_cast<uint16_t>(reading.scratchpad[0]) |
        (static_cast<uint16_t>(reading.scratchpad[1]) << 8U));
    reading.temperatureC = static_cast<float>(reading.rawTemperature) / 16.0f;
    reading.rangeOk = !isnan(reading.temperatureC) &&
                      reading.temperatureC >= kMinimumTemperatureC &&
                      reading.temperatureC <= kMaximumTemperatureC;
    reading.resolutionBits = static_cast<uint8_t>(
        9U + ((reading.scratchpad[4] >> 5U) & 0x03U));
    reading.readOk = reading.scratchpadCrcOk && reading.rangeOk;
    return reading.readOk;
}

bool Ds18b20Service::readDevice(uint8_t index, Ds18b20Reading &reading) {
    const uint8_t *address = deviceAddress(index);
    if (!_ready || !address) {
        reading = {};
        return false;
    }
    return readTemperature(address, true, reading);
}

bool Ds18b20Service::readSingleDrop(Ds18b20Reading &reading) {
    if (!_ready || !_singleDropFallbackReady) {
        reading = {};
        return false;
    }
    return readTemperature(nullptr, false, reading);
}

const char *Ds18b20Service::resolutionName(uint8_t bits) {
    switch (bits) {
        case 9U:
            return "9-bit";
        case 10U:
            return "10-bit";
        case 11U:
            return "11-bit";
        default:
            return "12-bit";
    }
}

String Ds18b20Service::buildJsonPayload(const char *sensorType,
                                        const char *sensorId,
                                        const char *edgeSystem,
                                        const char *edgeSystemId,
                                        const char *edgeStream,
                                        uint8_t maxReadAttempts,
                                        uint32_t retryDelayMs,
                                        uint32_t maxWaitMs) {
    JsonDocument doc;
    doc["sensor_type"] = sensorType ? sensorType : "temperature_ds18b20";
    doc["sensor_id"] = sensorId ? sensorId : "ds18b20_01";
    doc["edge_system"] = edgeSystem ? edgeSystem : "temperature_edge";
    doc["edge_system_id"] = edgeSystemId ? edgeSystemId : "edge_ds18b20";
    doc["edge_stream"] = edgeStream ? edgeStream : "ds18b20";
    doc["ds_data_gpio"] = _dataPin;
    doc["ds_device_count"] = _busStatus.deviceCount;
    doc["ds_idle_high"] = _busStatus.idleHigh;
    doc["ds_presence_detected"] = _busStatus.presenceDetected;
    doc["ds_rom_crc_ok"] = _busStatus.romFound;
    doc["ds_internal_pullup"] = DS18B20_USE_INTERNAL_PULLUP != 0;
    doc["ds_external_pullup"] = false;
    doc["ds_strong_pullup"] = DS18B20_USE_STRONG_PULLUP != 0;

    bool readOk = false;
    uint8_t attempts = 0U;
    const uint32_t startMs = millis();
    Ds18b20Reading lastReading;
    String error = _ready ? "read_not_attempted" : _lastInitError;

    if (_ready && maxReadAttempts > 0U) {
        while (attempts < maxReadAttempts) {
            if (millis() - startMs >= maxWaitMs) {
                error = "read_timeout_window";
                break;
            }

            ++attempts;
            if (_busStatus.deviceCount > 0U) {
                readDevice(0U, lastReading);
            } else {
                readSingleDrop(lastReading);
            }
            readOk = lastReading.readOk;
            if (readOk) {
                error = "ok";
                break;
            }

            if (!lastReading.presenceDetected) {
                error = "presence_missing";
            } else if (!lastReading.scratchpadCrcOk) {
                error = "scratchpad_crc_failed";
            } else if (!lastReading.rangeOk) {
                error = "out_of_range";
            } else {
                error = "read_failed";
            }

            if (attempts < maxReadAttempts) {
                delay(retryDelayMs);
            }
        }
    }

    doc["ds_read_ok"] = readOk;
    doc["ds_sample_valid"] = readOk;
    doc["ds_error"] = error;
    doc["ds_retry_count"] = attempts > 0U ? attempts - 1U : 0U;
    doc["ds_read_elapsed_ms"] = millis() - startMs;
    doc["ds_scratchpad_crc_ok"] = attempts > 0U && lastReading.scratchpadCrcOk;
    doc["ds_range_ok"] = attempts > 0U && lastReading.rangeOk;
    doc["ds_resolution_bits"] = attempts > 0U ? lastReading.resolutionBits : 0U;
    doc["ds_resolution"] = attempts > 0U ? resolutionName(lastReading.resolutionBits) : "unknown";

    if (attempts > 0U) {
        doc["ds_raw_temp"] = lastReading.rawTemperature;
        doc["ds_temp_c"] = readOk ? lastReading.temperatureC : NAN;
        char scratchpadHex[19] = {};
        for (uint8_t index = 0U; index < kScratchpadBytes; ++index) {
            snprintf(scratchpadHex + (index * 2U),
                     sizeof(scratchpadHex) - (index * 2U),
                     "%02X",
                     lastReading.scratchpad[index]);
        }
        doc["ds_scratchpad_hex"] = scratchpadHex;
    } else {
        doc["ds_raw_temp"] = nullptr;
        doc["ds_temp_c"] = nullptr;
        doc["ds_scratchpad_hex"] = nullptr;
    }

    if (_busStatus.deviceCount > 0U) {
        char romHex[17] = {};
        const uint8_t *address = _addresses[0];
        for (uint8_t index = 0U; index < 8U; ++index) {
            snprintf(romHex + (index * 2U),
                     sizeof(romHex) - (index * 2U),
                     "%02X",
                     address[index]);
        }
        doc["ds_rom"] = romHex;
    } else {
        doc["ds_rom"] = nullptr;
    }

    CUS_DBGF("[DS18B20][SERVICE] read_ok=%d sample_valid=%d temp=%.2fC error=%s attempts=%u elapsed=%lu ms\n",
             readOk ? 1 : 0,
             readOk ? 1 : 0,
             attempts > 0U ? static_cast<double>(lastReading.temperatureC) : NAN,
             error.c_str(),
             static_cast<unsigned>(attempts),
             static_cast<unsigned long>(millis() - startMs));

    String out;
    serializeJson(doc, out);
    return out;
}
