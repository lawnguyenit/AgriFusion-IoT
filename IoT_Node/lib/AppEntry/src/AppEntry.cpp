#include "AppEntry.h"

#include <Arduino.h>

#include "Config.h"

#if APP_SIM_UART_LOOPBACK_TEST_MODE
#include "SimUartLoopbackProbe.h"
#elif APP_SIM_NODE2_TEST_MODE
#include "SimNode2Probe.h"
#elif APP_NPK_MATRIX_TEST_MODE
#include "NpkMatrixProbe.h"
#elif APP_ALL_SENSORS_TEST_MODE
#include "AllSensorsProbe.h"
#elif APP_SOIL_MOISTURE_TEST_MODE
#include "SoilMoistureProbe.h"
#elif APP_SHT30_TEST_MODE
#include "Sht30Probe.h"
#elif APP_DS18B20_TEST_MODE
#include "Ds18b20Probe.h"
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

#if APP_SIM_UART_LOOPBACK_TEST_MODE
    simUartLoopbackProbeBegin();
#elif APP_SIM_NODE2_TEST_MODE
    simNode2ProbeBegin();
#elif APP_NPK_MATRIX_TEST_MODE
    npkMatrixProbeBegin();
#elif APP_ALL_SENSORS_TEST_MODE
    allSensorsProbeBegin();
#elif APP_SOIL_MOISTURE_TEST_MODE
    soilMoistureProbeBegin();
#elif APP_SHT30_TEST_MODE
    sht30ProbeBegin();
#elif APP_DS18B20_TEST_MODE
    ds18b20ProbeBegin();
#elif APP_RAW_TRUTH_PROBE_MODE || APP_SIM_PURE_TEST_MODE
    rawTruthProbeBegin();
#else
    gAppRuntime.begin();
#endif
}

void appEntryLoop() {
#if APP_SIM_UART_LOOPBACK_TEST_MODE
    simUartLoopbackProbeLoop();
#elif APP_SIM_NODE2_TEST_MODE
    simNode2ProbeLoop();
#elif APP_NPK_MATRIX_TEST_MODE
    vTaskDelete(nullptr);
#elif APP_ALL_SENSORS_TEST_MODE
    allSensorsProbeLoop();
    delay(20);
#elif APP_SOIL_MOISTURE_TEST_MODE
    soilMoistureProbeLoop();
    delay(50);
#elif APP_SHT30_TEST_MODE
    sht30ProbeLoop();
    delay(50);
#elif APP_DS18B20_TEST_MODE
    ds18b20ProbeLoop();
    delay(50);
#elif APP_RAW_TRUTH_PROBE_MODE || APP_SIM_PURE_TEST_MODE
    rawTruthProbeLoop();
    delay(50);
#else
    vTaskDelete(nullptr);
#endif
}
