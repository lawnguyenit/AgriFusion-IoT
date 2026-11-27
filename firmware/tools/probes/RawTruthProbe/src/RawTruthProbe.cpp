#include "RawTruthProbe.h"

#include <Arduino.h>

#include "Config.h"
#include "SimA7680C.h"
#include "TransportStability.h"

namespace {
uint32_t gLastProbeMs = 0;

void powerSequence() {
    if (SIM_SUPPLY_EN_PIN >= 0) {
        pinMode(SIM_SUPPLY_EN_PIN, OUTPUT);
        digitalWrite(SIM_SUPPLY_EN_PIN, SIM_SUPPLY_EN_ACTIVE_HIGH ? HIGH : LOW);
        delay(500);
    }

    if (SIM_PWRKEY_PIN >= 0) {
        pinMode(SIM_PWRKEY_PIN, OUTPUT);
        digitalWrite(SIM_PWRKEY_PIN, SIM_PWRKEY_ACTIVE_HIGH ? HIGH : LOW);
        delay(SIM_PWRKEY_HOLD_MS);
        digitalWrite(SIM_PWRKEY_PIN, SIM_PWRKEY_ACTIVE_HIGH ? LOW : HIGH);
        delay(3000);
    }
}

void runTruthProbe() {
    CUS_DBGLN("\n================ RAW TRUTH PROBE ================");
    TransportCycleReport report = runTransportCycle();
    printTransportCycleReport(report);
}
}  // namespace

void rawTruthProbeBegin() {
    CUS_DBGLN("");
    CUS_DBGLN("=== RAW TRANSPORT HARNESS ===");
    CUS_DBGF("[BOOT] interval=%lu ms apn=%s dns=%s:%u\n",
             (unsigned long)APP_RAW_TRUTH_PROBE_INTERVAL_MS,
             SIM_APN,
             SIM_TEST_DNS_HOST,
             (unsigned)SIM_TEST_DNS_PORT);

    powerSequence();
    bool simOk = setupSIM();
    CUS_DBGF("[BOOT] setupSIM=%d\n", simOk ? 1 : 0);
    gLastProbeMs = millis();
    runTruthProbe();
}

void rawTruthProbeLoop() {
    uint32_t now = millis();
    if (now - gLastProbeMs < APP_RAW_TRUTH_PROBE_INTERVAL_MS && gLastProbeMs != 0) {
        return;
    }
    gLastProbeMs = now;
    runTruthProbe();
}
