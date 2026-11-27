#include "Ds18b20Probe.h"

#include <Arduino.h>

#include "Config.h"
#include "Ds18b20Service.h"

namespace {
constexpr uint8_t kScratchpadBytes = 9U;

Ds18b20Service gService(DS18B20_DATA_PIN, DS18B20_RETRY_INIT_MS);
uint32_t gLastCycleMs = 0U;
uint32_t gCycleNo = 0U;

void printAddress(const uint8_t *address) {
    for (uint8_t index = 0U; index < 8U; ++index) {
        CUS_DBGF("%02X%s", address[index], index == 7U ? "" : " ");
    }
}

void printReading(const Ds18b20Reading &reading) {
    CUS_DBGF("[DS18B20][READ] scratchpad_crc=%d raw=0x%04X temp=%.2fC resolution=%u-bit range_ok=%d bytes=",
             reading.scratchpadCrcOk ? 1 : 0,
             static_cast<unsigned>(static_cast<uint16_t>(reading.rawTemperature)),
             static_cast<double>(reading.temperatureC),
             static_cast<unsigned>(reading.resolutionBits),
             reading.rangeOk ? 1 : 0);
    for (uint8_t index = 0U; index < kScratchpadBytes; ++index) {
        CUS_DBGF("%02X%s", reading.scratchpad[index], index == 8U ? "" : " ");
    }
    CUS_DBGLN("");
}

void runDiagnosticCycle(const char *reason) {
    ++gCycleNo;
    CUS_DBGF("\n[DS18B20][CYCLE] ===== START seq=%lu reason=%s =====\n",
             static_cast<unsigned long>(gCycleNo),
             reason ? reason : "unknown");

    gService.tryInit(true);
    const Ds18b20BusStatus &bus = gService.busStatus();
    CUS_DBGF("[DS18B20][BUS] idle_high=%d presence_before_search=%d precharge_us=%u\n",
             bus.idleHigh ? 1 : 0,
             bus.presenceDetected ? 1 : 0,
             static_cast<unsigned>(DS18B20_BUS_PRECHARGE_US));

    for (uint8_t index = 0U; index < gService.deviceCount(); ++index) {
        const uint8_t *address = gService.deviceAddress(index);
        CUS_DBGF("[DS18B20][ROM] address=");
        printAddress(address);
        CUS_DBGF(" family=0x%02X family_ok=1 crc_ok=1\n", address[0]);
    }

    CUS_DBGF("[DS18B20][BUS] data_gpio=%d devices=%u max_devices=%u internal_pullup=%d external_pullup=0 strong_pullup=%d\n",
             DS18B20_DATA_PIN,
             static_cast<unsigned>(gService.deviceCount()),
             static_cast<unsigned>(DS18B20_MAX_DEVICES),
             DS18B20_USE_INTERNAL_PULLUP ? 1 : 0,
             DS18B20_USE_STRONG_PULLUP ? 1 : 0);

    if (gService.deviceCount() == 0U) {
        CUS_DBGLN("[DS18B20][CYCLE] no_valid_ds18b20_found");
        if (bus.presenceDetected && DS18B20_SINGLE_DROP_FALLBACK) {
            CUS_DBGLN("[DS18B20][CYCLE] presence_detected; trying_single_drop_skip_rom");
            Ds18b20Reading reading;
            const bool readOk = gService.readSingleDrop(reading);
            printReading(reading);
            CUS_DBGF("[DS18B20][RESULT] device=single_drop_skip_rom read_ok=%d temp=%.2fC\n",
                     readOk ? 1 : 0,
                     static_cast<double>(reading.temperatureC));
        } else {
            CUS_DBGLN("[DS18B20][CYCLE] no_presence_detected; check DQ, VDD, GND, and pull-up.");
        }
    }

    for (uint8_t index = 0U; index < gService.deviceCount(); ++index) {
        Ds18b20Reading reading;
        const bool readOk = gService.readDevice(index, reading);
        printReading(reading);
        CUS_DBGF("[DS18B20][RESULT] device=%u read_ok=%d temp=%.2fC\n",
                 static_cast<unsigned>(index + 1U),
                 readOk ? 1 : 0,
                 static_cast<double>(reading.temperatureC));
    }

    CUS_DBGF("[DS18B20][CYCLE] ===== END seq=%lu =====\n",
             static_cast<unsigned long>(gCycleNo));
}
}  // namespace

void ds18b20ProbeBegin() {
    CUS_DBGF("[DS18B20][TEST] OneWire diagnostic; GPIO=%d interval_ms=%lu conversion_wait_ms=%lu precharge_us=%u internal_pullup=%d strong_pullup=%d skip_rom_fallback=%d\n",
             DS18B20_DATA_PIN,
             static_cast<unsigned long>(DS18B20_TEST_INTERVAL_MS),
             static_cast<unsigned long>(DS18B20_CONVERSION_WAIT_MS),
             static_cast<unsigned>(DS18B20_BUS_PRECHARGE_US),
             DS18B20_USE_INTERNAL_PULLUP ? 1 : 0,
             DS18B20_USE_STRONG_PULLUP ? 1 : 0,
             DS18B20_SINGLE_DROP_FALLBACK ? 1 : 0);
    CUS_DBGLN("[DS18B20][TEST] Hardware recommendation: 3-wire mode VDD=3V3, GND=GND, DQ=GPIO21, plus a 4.7k pull-up when available.");
    CUS_DBGLN("[DS18B20][TEST] Current no-resistor run uses the ESP32 internal pull-up and GPIO strong pull-up as an experimental fallback.");

    runDiagnosticCycle("boot");
    gLastCycleMs = millis();
}

void ds18b20ProbeLoop() {
    if (millis() - gLastCycleMs < DS18B20_TEST_INTERVAL_MS) {
        return;
    }

    gLastCycleMs = millis();
    runDiagnosticCycle("interval");
}
