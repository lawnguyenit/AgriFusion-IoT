#include "Sht30Probe.h"

#include <Arduino.h>
#include <Wire.h>

#include "Config.h"

namespace {

constexpr uint8_t kPrimaryAddress = SHT30_I2C_ADDR;
constexpr uint8_t kAlternateAddress = APP_SHT30_TEST_ALT_ADDR;
constexpr uint16_t kMeasureHighRepeatCommand = 0x2400;
constexpr size_t kSht30FrameBytes = 6U;

uint32_t gLastMeasurementLogMs = 0;
uint32_t gMeasurementSeq = 0;

struct AddressProbe {
    bool acknowledged = false;
    uint8_t error = 0xFF;
};

void prepareBus() {
    Wire.begin(SHT30_SDA_PIN, SHT30_SCL_PIN, APP_SHT30_WIRE_CLOCK_HZ);
    Wire.setTimeOut(APP_SHT30_WIRE_TIMEOUT_MS);
    delay(APP_SHT30_POST_WIRE_BEGIN_DELAY_MS);
}

AddressProbe pingAddress(uint8_t address) {
    Wire.beginTransmission(address);
    AddressProbe result;
    result.error = Wire.endTransmission();
    result.acknowledged = result.error == 0;
    return result;
}

const char *i2cErrorName(uint8_t error) {
    switch (error) {
        case 0:
            return "ok";
        case 1:
            return "data_too_long";
        case 2:
            return "address_nack";
        case 3:
            return "data_nack";
        case 4:
            return "other_error";
        case 5:
            return "timeout";
        default:
            return "unknown";
    }
}

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

bool sendMeasurementCommand(uint8_t address, uint8_t &i2cError) {
    Wire.beginTransmission(address);
    Wire.write(static_cast<uint8_t>(kMeasureHighRepeatCommand >> 8U));
    Wire.write(static_cast<uint8_t>(kMeasureHighRepeatCommand & 0xFFU));
    i2cError = Wire.endTransmission();
    return i2cError == 0;
}

void scanBusOnce() {
    uint8_t found = 0;
    for (uint8_t address = 0x03; address <= 0x77; ++address) {
        AddressProbe result = pingAddress(address);
        if (result.acknowledged) {
            ++found;
            CUS_DBGF("[SHT30][SCAN] ACK addr=0x%02X\n", address);
        }
    }

    CUS_DBGF("[SHT30][SCAN] done found=%u target=0x%02X alternate=0x%02X\n",
             static_cast<unsigned>(found),
             kPrimaryAddress,
             kAlternateAddress);
}

void printNoDevice(uint32_t sequence, AddressProbe primary, AddressProbe alternate) {
    CUS_DBGF("[SHT30][MEASURE] seq=%lu ACK=0 primary_error=%u(%s) alternate_error=%u(%s)\n",
             static_cast<unsigned long>(sequence),
             static_cast<unsigned>(primary.error),
             i2cErrorName(primary.error),
             static_cast<unsigned>(alternate.error),
             i2cErrorName(alternate.error));
}

void readMeasurement(uint32_t sequence, uint8_t address) {
    const uint32_t startedMs = millis();
    uint8_t i2cError = 0xFF;
    if (!sendMeasurementCommand(address, i2cError)) {
        CUS_DBGF("[SHT30][MEASURE] seq=%lu addr=0x%02X ACK=1 command=FAIL error=%u(%s)\n",
                 static_cast<unsigned long>(sequence),
                 address,
                 static_cast<unsigned>(i2cError),
                 i2cErrorName(i2cError));
        return;
    }

    delay(APP_SHT30_MEASUREMENT_WAIT_MS);
    uint8_t frame[kSht30FrameBytes] = {};
    size_t received = Wire.requestFrom(static_cast<uint8_t>(address),
                                       static_cast<size_t>(kSht30FrameBytes),
                                       true);
    size_t copied = 0;
    while (Wire.available() && copied < kSht30FrameBytes) {
        frame[copied++] = static_cast<uint8_t>(Wire.read());
    }

    const bool frameOk = received == kSht30FrameBytes && copied == kSht30FrameBytes;
    const bool temperatureCrcOk = frameOk && frame[2] == crc8(frame, 2U);
    const bool humidityCrcOk = frameOk && frame[5] == crc8(frame + 3U, 2U);
    const bool crcOk = temperatureCrcOk && humidityCrcOk;
    uint16_t rawTemperature = 0;
    uint16_t rawHumidity = 0;
    float temperatureC = NAN;
    float humidityPct = NAN;

    if (frameOk) {
        rawTemperature = static_cast<uint16_t>((static_cast<uint16_t>(frame[0]) << 8U) | frame[1]);
        rawHumidity = static_cast<uint16_t>((static_cast<uint16_t>(frame[3]) << 8U) | frame[4]);
        temperatureC = -45.0f + (175.0f * static_cast<float>(rawTemperature) / 65535.0f);
        humidityPct = 100.0f * static_cast<float>(rawHumidity) / 65535.0f;
    }

    const char *state = !frameOk ? "frame_invalid"
                        : !crcOk ? "crc_invalid"
                        : (rawTemperature == 0 && rawHumidity == 0) ? "zero_raw_measurement"
                                                                    : "ok";
    CUS_DBGF("[SHT30][MEASURE] seq=%lu addr=0x%02X ACK=1 frame=%d crc=%d temp_crc=%d hum_crc=%d state=%s raw_temp=0x%04X raw_hum=0x%04X temp=%.2f hum=%.2f elapsed_ms=%lu\n",
             static_cast<unsigned long>(sequence),
             address,
             frameOk ? 1 : 0,
             crcOk ? 1 : 0,
             temperatureCrcOk ? 1 : 0,
             humidityCrcOk ? 1 : 0,
             state,
             rawTemperature,
             rawHumidity,
             temperatureC,
             humidityPct,
             static_cast<unsigned long>(millis() - startedMs));
}

void runOneMeasurement() {
    const uint32_t sequence = ++gMeasurementSeq;
    const AddressProbe primary = pingAddress(kPrimaryAddress);
    if (primary.acknowledged) {
        readMeasurement(sequence, kPrimaryAddress);
        return;
    }

    const AddressProbe alternate = pingAddress(kAlternateAddress);
    if (alternate.acknowledged) {
        readMeasurement(sequence, kAlternateAddress);
        return;
    }

    printNoDevice(sequence, primary, alternate);
}

}  // namespace

void sht30ProbeBegin() {
    CUS_DBGF("[SHT30][TEST] Dedicated SHT30 diagnostic; SDA=%d SCL=%d addr=0x%02X alternate=0x%02X interval_ms=%lu\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             kPrimaryAddress,
             kAlternateAddress,
             static_cast<unsigned long>(APP_SHT30_TEST_INTERVAL_MS));
    CUS_DBGF("[SHT30][TEST] One bus scan at boot; one raw measurement result per interval.\n");

    prepareBus();
    scanBusOnce();
    runOneMeasurement();
    gLastMeasurementLogMs = millis();
}

void sht30ProbeLoop() {
    if (millis() - gLastMeasurementLogMs < APP_SHT30_TEST_INTERVAL_MS) {
        return;
    }

    runOneMeasurement();
    // Start the one-second spacing after the result line has been printed.
    gLastMeasurementLogMs = millis();
}
