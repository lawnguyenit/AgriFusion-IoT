#include "AppEntry.h"

#include <Arduino.h>

#include "Config.h"

#if APP_SHT30_TEST_MODE
#include "Sht30Probe.h"
#elif APP_RAW_TRUTH_PROBE_MODE || APP_SIM_PURE_TEST_MODE
#include "RawTruthProbe.h"
#else
#include "AppRuntime.h"

namespace {
AppRuntime gAppRuntime;
}
#endif

void appEntrySetup() {
#if DEBUG_MODE
    DEBUG_PORT.begin(DEBUG_BAUDRATE);
    delay(300);
#endif

#if APP_SHT30_TEST_MODE
    sht30ProbeBegin();
#elif APP_RAW_TRUTH_PROBE_MODE || APP_SIM_PURE_TEST_MODE
    rawTruthProbeBegin();
#else
    gAppRuntime.begin();
#endif
}

void appEntryLoop() {
#if APP_SHT30_TEST_MODE
    sht30ProbeLoop();
    delay(50);
#elif APP_RAW_TRUTH_PROBE_MODE || APP_SIM_PURE_TEST_MODE
    rawTruthProbeLoop();
    delay(50);
#else
    vTaskDelete(nullptr);
#endif
}
