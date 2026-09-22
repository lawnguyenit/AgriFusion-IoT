#include "Sht30Probe.h"

#include <Arduino.h>
#include <Adafruit_SHT31.h>
#include <Wire.h>

#include "Config.h"
#include "Sht30Service.h"

namespace {

constexpr uint8_t kPrimaryAddress = SHT30_I2C_ADDR;
constexpr uint8_t kAlternateAddress = APP_SHT30_TEST_ALT_ADDR;
constexpr uint16_t kSoftResetCommand = 0x30A2;
constexpr uint16_t kMeasureHighRepeatCommand = 0x2400;
constexpr size_t kSht30FrameBytes = 6U;

struct MeasurementCommandVariant {
    const char *name;
    uint16_t command;
};

constexpr MeasurementCommandVariant kMeasurementCommandVariants[] = {
    {"high_no_stretch", 0x2400},
    {"high_clock_stretch", 0x2C06},
    {"medium_no_stretch", 0x240B},
    {"low_no_stretch", 0x2416},
};

Sht30Service gPrimaryService(SHT30_SDA_PIN,
                             SHT30_SCL_PIN,
                             kPrimaryAddress,
                             APP_SHT30_RETRY_INIT_MS);
Sht30Service gAlternateService(SHT30_SDA_PIN,
                               SHT30_SCL_PIN,
                               kAlternateAddress,
                               APP_SHT30_RETRY_INIT_MS);
Adafruit_SHT31 gAdafruitCrossCheck;

uint32_t gLastProbeMs = 0;
uint32_t gProbeSeq = 0;

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

bool sendCommand(uint8_t address, uint16_t command, uint8_t &i2cError) {
    Wire.beginTransmission(address);
    Wire.write(static_cast<uint8_t>(command >> 8U));
    Wire.write(static_cast<uint8_t>(command & 0xFFU));
    i2cError = Wire.endTransmission();
    return i2cError == 0;
}

bool readRawMeasurement(const char *label,
                        uint8_t address,
                        uint32_t sequence,
                        uint16_t measurementCommand = kMeasureHighRepeatCommand,
                        const char *commandMode = "high_no_stretch") {
    const uint32_t startedMs = millis();
    AddressProbe addressProbe = pingAddress(address);
    if (!addressProbe.acknowledged) {
        CUS_DBGF("[SHT30][RAW] seq=%lu label=%s addr=0x%02X ACK=0 i2c_error=%u(%s)\n",
                 static_cast<unsigned long>(sequence),
                 label ? label : "na",
                 address,
                 static_cast<unsigned>(addressProbe.error),
                 i2cErrorName(addressProbe.error));
        return false;
    }

    uint8_t i2cError = 0xFF;
    bool resetOk = sendCommand(address, kSoftResetCommand, i2cError);
    delay(APP_SHT30_SOFT_RESET_WAIT_MS);
    if (!resetOk) {
        CUS_DBGF("[SHT30][RAW] seq=%lu label=%s addr=0x%02X reset=FAIL i2c_error=%u(%s)\n",
                 static_cast<unsigned long>(sequence),
                 label ? label : "na",
                 address,
                 static_cast<unsigned>(i2cError),
                 i2cErrorName(i2cError));
        return false;
    }

    bool commandOk = sendCommand(address, measurementCommand, i2cError);
    delay(APP_SHT30_MEASUREMENT_WAIT_MS);
    if (!commandOk) {
        CUS_DBGF("[SHT30][RAW] seq=%lu label=%s addr=0x%02X mode=%s cmd=0x%04X measure_cmd=FAIL i2c_error=%u(%s)\n",
                 static_cast<unsigned long>(sequence),
                 label ? label : "na",
                 address,
                 commandMode ? commandMode : "na",
                 measurementCommand,
                 static_cast<unsigned>(i2cError),
                 i2cErrorName(i2cError));
        return false;
    }

    uint8_t frame[kSht30FrameBytes] = {};
    size_t received = Wire.requestFrom(static_cast<uint8_t>(address),
                                       static_cast<size_t>(kSht30FrameBytes),
                                       true);
    size_t copied = 0;
    while (Wire.available() && copied < kSht30FrameBytes) {
        frame[copied++] = static_cast<uint8_t>(Wire.read());
    }

    bool frameLengthOk = received == kSht30FrameBytes && copied == kSht30FrameBytes;
    bool tempCrcOk = frameLengthOk && frame[2] == crc8(frame, 2U);
    bool humidityCrcOk = frameLengthOk && frame[5] == crc8(frame + 3U, 2U);
    bool crcOk = tempCrcOk && humidityCrcOk;

    uint16_t rawTemperature = 0;
    uint16_t rawHumidity = 0;
    float temperatureC = NAN;
    float humidityPct = NAN;
    if (frameLengthOk) {
        rawTemperature = static_cast<uint16_t>((static_cast<uint16_t>(frame[0]) << 8U) | frame[1]);
        rawHumidity = static_cast<uint16_t>((static_cast<uint16_t>(frame[3]) << 8U) | frame[4]);
        temperatureC = -45.0f + (175.0f * static_cast<float>(rawTemperature) / 65535.0f);
        humidityPct = 100.0f * static_cast<float>(rawHumidity) / 65535.0f;
    }

    const char *measurementState = !frameLengthOk
                                       ? "frame_invalid"
                                       : !crcOk
                                             ? "crc_invalid"
                                             : (rawTemperature == 0 && rawHumidity == 0)
                                                   ? "zero_raw_measurement"
                                                   : "decoded";

    CUS_DBGF("[SHT30][RAW] seq=%lu label=%s addr=0x%02X mode=%s cmd=0x%04X reset=1 measure=1 wait_reset_ms=%lu wait_measure_ms=%lu received=%u/%u frame=%d crc=%d temp_crc=%d hum_crc=%d state=%s bytes=%02X %02X %02X %02X %02X %02X raw_temp=0x%04X raw_hum=0x%04X temp=%.2f hum=%.2f elapsed=%lu\n",
             static_cast<unsigned long>(sequence),
             label ? label : "na",
             address,
             commandMode ? commandMode : "na",
             measurementCommand,
             static_cast<unsigned long>(APP_SHT30_SOFT_RESET_WAIT_MS),
             static_cast<unsigned long>(APP_SHT30_MEASUREMENT_WAIT_MS),
             static_cast<unsigned>(copied),
             static_cast<unsigned>(kSht30FrameBytes),
             frameLengthOk ? 1 : 0,
             crcOk ? 1 : 0,
             tempCrcOk ? 1 : 0,
             humidityCrcOk ? 1 : 0,
             measurementState,
             frame[0],
             frame[1],
             frame[2],
             frame[3],
             frame[4],
             frame[5],
             rawTemperature,
             rawHumidity,
             temperatureC,
             humidityPct,
             static_cast<unsigned long>(millis() - startedMs));
    return crcOk;
}

uint8_t scanBus() {
    CUS_DBGF("[SHT30][BUS] scan start SDA=%d SCL=%d hz=%lu range=0x03..0x77\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             static_cast<unsigned long>(APP_SHT30_WIRE_CLOCK_HZ));

    uint8_t found = 0;
    for (uint8_t address = 0x03; address <= 0x77; ++address) {
        AddressProbe result = pingAddress(address);
        if (result.acknowledged) {
            ++found;
            CUS_DBGF("[SHT30][BUS] ACK addr=0x%02X\n", address);
        }
    }

    CUS_DBGF("[SHT30][BUS] scan end found=%u primary=0x%02X alternate=0x%02X\n",
             static_cast<unsigned>(found),
             kPrimaryAddress,
             kAlternateAddress);
    return found;
}

String buildServicePayload(Sht30Service &service, const char *sensorId) {
    return service.buildJsonPayload("sht30_air",
                                   sensorId,
                                   APP_EDGE_SYSTEM_SHT,
                                   APP_EDGE_SYSTEM_ID_SHT,
                                   "sht30",
                                   SHT30_READ_MAX_ATTEMPTS,
                                   SHT30_RETRY_DELAY_MS,
                                   SHT30_MAX_WAIT_MS);
}

bool runForcedInitBurst(const char *label,
                        Sht30Service &service,
                        uint8_t address,
                        const char *sensorId) {
    CUS_DBGF("[SHT30][INIT_BURST] label=%s attempts=%u gap_ms=%lu force_every_attempt=1 addr=0x%02X\n",
             label ? label : "na",
             static_cast<unsigned>(APP_SHT30_TEST_BOOT_PROBES),
             static_cast<unsigned long>(APP_SHT30_TEST_BOOT_DELAY_MS),
             address);

    bool ready = false;
    for (uint8_t attempt = 1; attempt <= static_cast<uint8_t>(APP_SHT30_TEST_BOOT_PROBES); ++attempt) {
        uint32_t startedMs = millis();
        AddressProbe bus = pingAddress(address);
        bool initOk = service.tryInit(true);
        String payload = buildServicePayload(service, sensorId);
        CUS_DBGF("[SHT30][INIT_BURST] label=%s attempt=%u/%u bus_ack=%d bus_error=%u(%s) init=%d ready=%d elapsed=%lu payload=%s\n",
                 label ? label : "na",
                 static_cast<unsigned>(attempt),
                 static_cast<unsigned>(APP_SHT30_TEST_BOOT_PROBES),
                 bus.acknowledged ? 1 : 0,
                 static_cast<unsigned>(bus.error),
                 i2cErrorName(bus.error),
                 initOk ? 1 : 0,
                 service.ready() ? 1 : 0,
                 static_cast<unsigned long>(millis() - startedMs),
                 payload.c_str());

        if (initOk && service.ready()) {
            ready = true;
            CUS_DBGF("[SHT30][INIT_BURST] label=%s SUCCESS at attempt=%u\n",
                     label ? label : "na",
                     static_cast<unsigned>(attempt));
            break;
        }

        if (attempt < static_cast<uint8_t>(APP_SHT30_TEST_BOOT_PROBES)) {
            delay(APP_SHT30_TEST_BOOT_DELAY_MS);
        }
    }

    if (!ready) {
        CUS_DBGF("[SHT30][INIT_BURST] label=%s END result=not_ready\n", label ? label : "na");
    }
    return ready;
}

void runRawReadBurst(const char *label, uint8_t address) {
    CUS_DBGF("[SHT30][RAW_BURST] label=%s count=%u gap_ms=%lu addr=0x%02X\n",
             label ? label : "na",
             static_cast<unsigned>(APP_SHT30_TEST_RAW_READ_COUNT),
             static_cast<unsigned long>(APP_SHT30_TEST_RAW_READ_DELAY_MS),
             address);

    uint8_t successCount = 0;
    for (uint8_t sample = 1; sample <= static_cast<uint8_t>(APP_SHT30_TEST_RAW_READ_COUNT); ++sample) {
        if (readRawMeasurement(label, address, sample)) {
            ++successCount;
        }
        if (sample < static_cast<uint8_t>(APP_SHT30_TEST_RAW_READ_COUNT)) {
            delay(APP_SHT30_TEST_RAW_READ_DELAY_MS);
        }
    }

    CUS_DBGF("[SHT30][RAW_BURST] label=%s END crc_valid=%u/%u\n",
             label ? label : "na",
             static_cast<unsigned>(successCount),
             static_cast<unsigned>(APP_SHT30_TEST_RAW_READ_COUNT));
}

void runMeasurementCommandMatrix(uint8_t address) {
    CUS_DBGF("[SHT30][COMMAND_MATRIX] start addr=0x%02X variants=%u wait_ms=%lu\n",
             address,
             static_cast<unsigned>(sizeof(kMeasurementCommandVariants) /
                                   sizeof(kMeasurementCommandVariants[0])),
             static_cast<unsigned long>(APP_SHT30_MEASUREMENT_WAIT_MS));

    uint32_t sequence = 1U;
    for (const MeasurementCommandVariant &variant : kMeasurementCommandVariants) {
        readRawMeasurement("command_matrix",
                           address,
                           sequence++,
                           variant.command,
                           variant.name);
    }

    CUS_DBGLN("[SHT30][COMMAND_MATRIX] end");
}

void runAdafruitCrossCheck(uint8_t address) {
    CUS_DBGF("[SHT30][ADA_XCHECK] start addr=0x%02X\n", address);

    bool beginOk = gAdafruitCrossCheck.begin(address);
    float temperatureC = NAN;
    float humidityPct = NAN;
    bool readOk = beginOk && gAdafruitCrossCheck.readBoth(&temperatureC, &humidityPct);

    CUS_DBGF("[SHT30][ADA_XCHECK] addr=0x%02X begin=%d read_ok=%d temp=%.2f hum=%.2f\n",
             address,
             beginOk ? 1 : 0,
             readOk ? 1 : 0,
             temperatureC,
             humidityPct);
    CUS_DBGLN("[SHT30][ADA_XCHECK] end");
}

void runDiagnosticCycle(const char *reason) {
    ++gProbeSeq;
    CUS_DBGF("\n[SHT30][CYCLE] ===== START seq=%lu reason=%s =====\n",
             static_cast<unsigned long>(gProbeSeq),
             reason ? reason : "na");

    prepareBus();
#if APP_SHT30_TEST_SCAN_FULL_BUS
    scanBus();
#else
    CUS_DBGF("[SHT30][BUS] full_scan=0 primary=0x%02X alternate=0x%02X\n",
             kPrimaryAddress,
             kAlternateAddress);
#endif

    AddressProbe primary = pingAddress(kPrimaryAddress);
    AddressProbe alternate = pingAddress(kAlternateAddress);
    CUS_DBGF("[SHT30][BUS] candidate primary=0x%02X ack=%d error=%u(%s) alternate=0x%02X ack=%d error=%u(%s)\n",
             kPrimaryAddress,
             primary.acknowledged ? 1 : 0,
             static_cast<unsigned>(primary.error),
             i2cErrorName(primary.error),
             kAlternateAddress,
             alternate.acknowledged ? 1 : 0,
             static_cast<unsigned>(alternate.error),
             i2cErrorName(alternate.error));

    if (primary.acknowledged) {
        readRawMeasurement("primary_before_init", kPrimaryAddress, 0U);
    }
    if (alternate.acknowledged) {
        readRawMeasurement("alternate_before_init", kAlternateAddress, 0U);
    }

    bool primaryReady = runForcedInitBurst("primary", gPrimaryService, kPrimaryAddress, APP_SENSOR_ID_SHT30);
    if (primaryReady) {
        String payload = buildServicePayload(gPrimaryService, APP_SENSOR_ID_SHT30);
        CUS_DBGF("[SHT30][SERVICE] primary_post_init payload=%s\n", payload.c_str());
    }
    AddressProbe primaryAfter = pingAddress(kPrimaryAddress);
    CUS_DBGF("[SHT30][BUS] post_init primary=0x%02X ack=%d error=%u(%s)\n",
             kPrimaryAddress,
             primaryAfter.acknowledged ? 1 : 0,
             static_cast<unsigned>(primaryAfter.error),
             i2cErrorName(primaryAfter.error));
    if (primaryAfter.acknowledged) {
        runRawReadBurst("primary_after_init", kPrimaryAddress);
        runMeasurementCommandMatrix(kPrimaryAddress);
        runAdafruitCrossCheck(kPrimaryAddress);
    }

    bool alternateReady = false;
    AddressProbe alternateAfter = pingAddress(kAlternateAddress);
    bool alternateSeen = alternate.acknowledged || alternateAfter.acknowledged;
    CUS_DBGF("[SHT30][BUS] post_init alternate=0x%02X ack=%d error=%u(%s)\n",
             kAlternateAddress,
             alternateAfter.acknowledged ? 1 : 0,
             static_cast<unsigned>(alternateAfter.error),
             i2cErrorName(alternateAfter.error));
    if (alternateSeen) {
        alternateReady = runForcedInitBurst("alternate", gAlternateService, kAlternateAddress, "sht30_air_alt_addr");
        if (alternateReady) {
            String payload = buildServicePayload(gAlternateService, "sht30_air_alt_addr");
            CUS_DBGF("[SHT30][SERVICE] alternate_post_init payload=%s\n", payload.c_str());
        }
        AddressProbe alternateFinal = pingAddress(kAlternateAddress);
        if (alternateFinal.acknowledged) {
            runRawReadBurst("alternate_after_init", kAlternateAddress);
        }
    } else {
        CUS_DBGF("[SHT30][ALT] addr=0x%02X not acknowledged; no alternate init attempted.\n",
                 kAlternateAddress);
    }

    CUS_DBGF("[SHT30][CYCLE] ===== END seq=%lu primary_ready=%d alternate_ready=%d =====\n",
             static_cast<unsigned long>(gProbeSeq),
             primaryReady ? 1 : 0,
             alternateReady ? 1 : 0);
}

}  // namespace

void sht30ProbeBegin() {
    CUS_DBGF("[SHT30][TEST] Dedicated SHT30 test; no SIM/Firebase. SDA=%d SCL=%d primary=0x%02X alternate=0x%02X wire_hz=%lu timeout_ms=%lu\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             kPrimaryAddress,
             kAlternateAddress,
             static_cast<unsigned long>(APP_SHT30_WIRE_CLOCK_HZ),
             static_cast<unsigned long>(APP_SHT30_WIRE_TIMEOUT_MS));
    CUS_DBGF("[SHT30][TEST] Strategy A=forced consecutive service init; Strategy B=I2C scan + raw command/CRC read.\n");
    CUS_DBGF("[SHT30][TEST] init_attempts=%u init_gap_ms=%lu raw_reads=%u raw_gap_ms=%lu interval_ms=%lu reset_wait_ms=%lu measurement_wait_ms=%lu\n",
             static_cast<unsigned>(APP_SHT30_TEST_BOOT_PROBES),
             static_cast<unsigned long>(APP_SHT30_TEST_BOOT_DELAY_MS),
             static_cast<unsigned>(APP_SHT30_TEST_RAW_READ_COUNT),
             static_cast<unsigned long>(APP_SHT30_TEST_RAW_READ_DELAY_MS),
             static_cast<unsigned long>(APP_SHT30_TEST_INTERVAL_MS),
             static_cast<unsigned long>(APP_SHT30_SOFT_RESET_WAIT_MS),
             static_cast<unsigned long>(APP_SHT30_MEASUREMENT_WAIT_MS));

    runDiagnosticCycle("boot");
    gLastProbeMs = millis();
}

void sht30ProbeLoop() {
    if (millis() - gLastProbeMs < APP_SHT30_TEST_INTERVAL_MS) {
        return;
    }

    gLastProbeMs = millis();
    runDiagnosticCycle("interval");
}
