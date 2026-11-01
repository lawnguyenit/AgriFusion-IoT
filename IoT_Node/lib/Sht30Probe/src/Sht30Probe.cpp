#include "Sht30Probe.h"

#include <Arduino.h>
#include <ArduinoJson.h>

#include "Config.h"
#include "Sht30Service.h"

namespace {
Sht30Service gSht30Probe(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, APP_SHT30_RETRY_INIT_MS);
uint32_t gLastProbeMs = 0;
uint32_t gProbeSeq = 0;
bool gForceInitNextProbe = true;

bool runProbe(const char *reason, bool forceInit) {
    ++gProbeSeq;
    bool initOk = gSht30Probe.tryInit(forceInit);
    bool busSeen = gSht30Probe.isAddressReachable(false);
    String payload = gSht30Probe.buildJsonPayload("sht30_air",
                                                  "sht30_1",
                                                  APP_EDGE_SYSTEM_SHT,
                                                  APP_EDGE_SYSTEM_ID_SHT,
                                                  "sht30",
                                                  SHT30_READ_MAX_ATTEMPTS,
                                                  SHT30_RETRY_DELAY_MS,
                                                  SHT30_MAX_WAIT_MS);

    JsonDocument result;
    DeserializationError parseError = deserializeJson(result, payload);
    bool sampleValid = !parseError && (result["sht_sample_valid"] | false);
    bool passed = busSeen && initOk && sampleValid;
    gForceInitNextProbe = !passed;

    CUS_DBGF("[SHT30][TEST] seq=%lu reason=%s result=%s bus=%d init=%d ready=%d sample_valid=%d payload=%s\n",
             (unsigned long)gProbeSeq,
             reason ? reason : "na",
             passed ? "PASS" : "FAIL",
             busSeen ? 1 : 0,
             initOk ? 1 : 0,
             gSht30Probe.ready() ? 1 : 0,
             sampleValid ? 1 : 0,
             payload.c_str());
    if (!passed) {
        CUS_DBGF("[SHT30][TEST] Se thu lai sau %lu ms; buoc tiep theo se khoi tao lai I2C/SHT30.\n",
                 (unsigned long)APP_SHT30_TEST_INTERVAL_MS);
    }
    return passed;
}
}  // namespace

void sht30ProbeBegin() {
    CUS_DBGF("[SHT30][TEST] Bat dau probe rieng vo han, SDA=%d SCL=%d addr=0x%02X retry_interval=%lu ms.\n",
             SHT30_SDA_PIN,
             SHT30_SCL_PIN,
             SHT30_I2C_ADDR,
             (unsigned long)APP_SHT30_TEST_INTERVAL_MS);

    runProbe("boot", true);
    gLastProbeMs = millis();
}

void sht30ProbeLoop() {
    if (millis() - gLastProbeMs < APP_SHT30_TEST_INTERVAL_MS) {
        return;
    }

    bool forceInit = gForceInitNextProbe;
    runProbe(forceInit ? "retry_after_fail" : "periodic", forceInit);
    gLastProbeMs = millis();
}
