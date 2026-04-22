#include "Sht30Probe.h"

#include <Arduino.h>

#include "Config.h"
#include "Sht30Service.h"

namespace {
Sht30Service gSht30Probe(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, APP_SHT30_RETRY_INIT_MS);
uint32_t gLastProbeMs = 0;
uint32_t gProbeSeq = 0;

void runProbe(const char *reason, bool forceInit) {
    ++gProbeSeq;
    bool busSeen = gSht30Probe.isAddressReachable(forceInit);
    bool initOk = gSht30Probe.tryInit(forceInit);
    String payload = gSht30Probe.buildJsonPayload("sht30_air",
                                                  "sht30_1",
                                                  APP_EDGE_SYSTEM_SHT,
                                                  APP_EDGE_SYSTEM_ID_SHT,
                                                  "sht30",
                                                  SHT30_READ_MAX_ATTEMPTS,
                                                  SHT30_RETRY_DELAY_MS,
                                                  SHT30_MAX_WAIT_MS);

    CUS_DBGF("[SHT30][TEST] seq=%lu reason=%s bus=%d init=%d ready=%d payload=%s\n",
             (unsigned long)gProbeSeq,
             reason ? reason : "na",
             busSeen ? 1 : 0,
             initOk ? 1 : 0,
             gSht30Probe.ready() ? 1 : 0,
             payload.c_str());
}
}  // namespace

void sht30ProbeBegin() {
    CUS_DBGF("[SHT30][TEST] Bat dau probe rieng, SDA=%d SCL=%d addr=0x%02X interval=%lu ms.\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             SHT30_I2C_ADDR,
             (unsigned long)APP_SHT30_TEST_INTERVAL_MS);

    for (uint32_t i = 0; i < (uint32_t)APP_SHT30_TEST_BOOT_PROBES; ++i) {
        runProbe("boot", i == 0);
        if (i + 1U < (uint32_t)APP_SHT30_TEST_BOOT_PROBES) {
            delay(APP_SHT30_TEST_BOOT_DELAY_MS);
        }
    }

    gLastProbeMs = millis();
}

void sht30ProbeLoop() {
    if (millis() - gLastProbeMs < APP_SHT30_TEST_INTERVAL_MS) {
        return;
    }

    gLastProbeMs = millis();
    runProbe("interval", false);
}
