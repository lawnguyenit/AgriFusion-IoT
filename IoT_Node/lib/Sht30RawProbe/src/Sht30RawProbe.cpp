#include "Sht30RawProbe.h"

#include <Arduino.h>
#include <Wire.h>

#include "Config.h"

namespace {
constexpr uint16_t kSoftResetCommand = 0x30A2;
constexpr uint16_t kHighRepeatabilityClockStretch = 0x2C06;
constexpr uint8_t kFrameLength = 6;
constexpr uint32_t kWireTimeoutMs = 50;
constexpr uint32_t kClockStretchPreReadMs = 1;

struct Measurement {
    uint8_t frame[kFrameLength] = {};
    uint8_t received = 0;
    uint8_t requested = 0;
    uint8_t commandError = 0xFF;
    bool commandAck = false;
    bool frameComplete = false;
    bool temperatureCrcOk = false;
    bool humidityCrcOk = false;
    uint16_t rawTemperature = 0;
    uint16_t rawHumidity = 0;
    float temperatureC = NAN;
    float humidityPct = NAN;
};

uint32_t gLastCycleMs = 0;
uint32_t gSequence = 0;
bool gBusStarted = false;

uint8_t crc8(const uint8_t *bytes, size_t length) {
    uint8_t crc = 0xFF;
    for (size_t index = 0; index < length; ++index) {
        crc ^= bytes[index];
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x80U) ? static_cast<uint8_t>((crc << 1U) ^ 0x31U)
                                : static_cast<uint8_t>(crc << 1U);
        }
    }
    return crc;
}

uint8_t sendCommand(uint16_t command) {
    Wire.beginTransmission(SHT30_I2C_ADDR);
    Wire.write(static_cast<uint8_t>(command >> 8U));
    Wire.write(static_cast<uint8_t>(command & 0xFFU));
    return Wire.endTransmission();
}

Measurement measure(uint16_t command, uint32_t waitBeforeReadMs) {
    Measurement result;
    result.commandError = sendCommand(command);
    result.commandAck = result.commandError == 0;
    if (!result.commandAck) {
        return result;
    }

    if (waitBeforeReadMs > 0) {
        delay(waitBeforeReadMs);
    }

    result.requested = static_cast<uint8_t>(Wire.requestFrom(
        static_cast<uint8_t>(SHT30_I2C_ADDR),
        static_cast<uint8_t>(kFrameLength),
        static_cast<uint8_t>(true)));
    while (Wire.available() && result.received < kFrameLength) {
        result.frame[result.received++] = static_cast<uint8_t>(Wire.read());
    }
    result.frameComplete = result.received == kFrameLength && result.requested == kFrameLength;
    if (!result.frameComplete) {
        return result;
    }

    result.temperatureCrcOk = result.frame[2] == crc8(result.frame, 2);
    result.humidityCrcOk = result.frame[5] == crc8(result.frame + 3, 2);
    result.rawTemperature = static_cast<uint16_t>(
        (static_cast<uint16_t>(result.frame[0]) << 8U) | result.frame[1]);
    result.rawHumidity = static_cast<uint16_t>(
        (static_cast<uint16_t>(result.frame[3]) << 8U) | result.frame[4]);
    result.temperatureC = -45.0f + 175.0f * result.rawTemperature / 65535.0f;
    result.humidityPct = 100.0f * result.rawHumidity / 65535.0f;
    return result;
}

void printMeasurement(uint32_t sequence, const char *mode, uint16_t command, const Measurement &m) {
    const bool crcOk = m.temperatureCrcOk && m.humidityCrcOk;
    CUS_DBGF("[SHT30][WIRE] seq=%lu mode=%s cmd=0x%04X ack=%d i2c_error=%u requested=%u received=%u complete=%d frame=%02X %02X %02X %02X %02X %02X crc_t=%d crc_rh=%d raw_t=0x%04X raw_rh=0x%04X temp_c=%.2f rh_pct=%.2f rh_zero=%d result=%s\n",
             static_cast<unsigned long>(sequence),
             mode,
             command,
             m.commandAck ? 1 : 0,
             static_cast<unsigned>(m.commandError),
             static_cast<unsigned>(m.requested),
             static_cast<unsigned>(m.received),
             m.frameComplete ? 1 : 0,
             static_cast<unsigned>(m.frame[0]),
             static_cast<unsigned>(m.frame[1]),
             static_cast<unsigned>(m.frame[2]),
             static_cast<unsigned>(m.frame[3]),
             static_cast<unsigned>(m.frame[4]),
             static_cast<unsigned>(m.frame[5]),
             m.temperatureCrcOk ? 1 : 0,
             m.humidityCrcOk ? 1 : 0,
             m.rawTemperature,
             m.rawHumidity,
             m.temperatureC,
             m.humidityPct,
             m.frameComplete && m.rawHumidity == 0 ? 1 : 0,
             !m.commandAck ? "command_fail"
                           : !m.frameComplete ? "frame_short"
                                              : !crcOk ? "crc_fail" : "protocol_ok");
}

void runCycle(const char *reason) {
    ++gSequence;
    Wire.beginTransmission(SHT30_I2C_ADDR);
    const uint8_t addressError = Wire.endTransmission();
    CUS_DBGF("[SHT30][WIRE] seq=%lu reason=%s sda=%d scl=%d addr=0x%02X address_ack=%d i2c_error=%u\n",
             static_cast<unsigned long>(gSequence),
             reason,
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             SHT30_I2C_ADDR,
             addressError == 0 ? 1 : 0,
             static_cast<unsigned>(addressError));
    if (addressError != 0) {
        return;
    }

    // Repeat the mode that returned plausible temperatures in the prior run.
    // Do not reset between samples or interleave another command mode.
    const Measurement withStretch = measure(kHighRepeatabilityClockStretch, kClockStretchPreReadMs);
    printMeasurement(gSequence, "high_clock_stretch", kHighRepeatabilityClockStretch, withStretch);
}
}  // namespace

void sht30RawProbeBegin() {
    Wire.begin(SHT30_SDA_PIN, SHT30_SCL_PIN, APP_SHT30_WIRE_CLOCK_HZ);
    Wire.setTimeOut(kWireTimeoutMs);
    gBusStarted = true;
    delay(APP_SHT30_POST_WIRE_BEGIN_DELAY_MS);

    CUS_DBGF("[SHT30][WIRE] standalone datasheet probe SDA=%d SCL=%d addr=0x%02X bus_hz=%lu interval_ms=%lu timeout_ms=%lu\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             SHT30_I2C_ADDR,
             static_cast<unsigned long>(APP_SHT30_WIRE_CLOCK_HZ),
             static_cast<unsigned long>(APP_SHT30_TEST_INTERVAL_MS),
             static_cast<unsigned long>(kWireTimeoutMs));

    const uint8_t resetError = sendCommand(kSoftResetCommand);
    delay(2);  // Datasheet maximum soft-reset time is 1.5 ms.
    CUS_DBGF("[SHT30][WIRE] startup_soft_reset=0x30A2 ack=%d i2c_error=%u\n",
             resetError == 0 ? 1 : 0,
             static_cast<unsigned>(resetError));
    runCycle("boot");
    gLastCycleMs = millis();
}

void sht30RawProbeLoop() {
    if (!gBusStarted || millis() - gLastCycleMs < APP_SHT30_TEST_INTERVAL_MS) {
        return;
    }
    runCycle("periodic");
    gLastCycleMs = millis();
}
