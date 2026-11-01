#include "SoilMoistureProbe.h"

#include <Arduino.h>

#include "Config.h"
#include "SoilMoistureService.h"

namespace {

SoilMoistureService gSensor(SOIL_MOISTURE_ADC_PIN,
                            SOIL_MOISTURE_AIR_ADC,
                            SOIL_MOISTURE_WATER_ADC,
                            SOIL_MOISTURE_SAMPLE_COUNT,
                            SOIL_MOISTURE_SAMPLE_GAP_MS);
uint32_t gLastCycleMs = 0U;
uint32_t gCycleNo = 0U;
SoilMoistureReading gAirBaseline;
bool gHaveAirBaseline = false;

void printHelp() {
    CUS_DBGLN("[MOISTURE_V1_2][TEST] Start with probe in air; boot reading is the baseline. Send 'a' to recapture air baseline; '?' prints this help.");
    CUS_DBGLN("[MOISTURE_V1_2][TEST] Then immerse only the sensing blade and watch raw/voltage delta; common v1.2 reference expects both to fall in water and rise after removal.");
    CUS_DBGLN("[MOISTURE_V1_2][TEST] ADC logs cannot separate sensor failure from AOUT/GND/wiring faults; use a multimeter if no clear change appears.");
}

void runDiagnosticCycle(const char *reason, bool captureAirBaseline = false) {
    ++gCycleNo;
    CUS_DBGF("\n[MOISTURE_V1_2][CYCLE] ===== START seq=%lu reason=%s =====\n",
             static_cast<unsigned long>(gCycleNo),
             reason ? reason : "unknown");

    SoilMoistureReading data;
    gSensor.read(data);
    if (captureAirBaseline && data.readOk) {
        gAirBaseline = data;
        gHaveAirBaseline = true;
        CUS_DBGF("[MOISTURE_V1_2][BASELINE] air captured raw=%d raw_min=%d raw_max=%d voltage_mv=%lu\n",
                 gAirBaseline.raw,
                 gAirBaseline.rawMin,
                 gAirBaseline.rawMax,
                 static_cast<unsigned long>(gAirBaseline.voltageMv));
    }

    CUS_DBGF("[MOISTURE_V1_2][READ] adc_gpio=%u raw=%d raw_min=%d raw_max=%d "
             "voltage_mv=%lu calibrated=%d calibration_status=%s profile=%s dry_adc=%d wet_adc=%d ",
             static_cast<unsigned>(SOIL_MOISTURE_ADC_PIN),
             data.raw,
             data.rawMin,
             data.rawMax,
             static_cast<unsigned long>(data.voltageMv),
             data.calibrationValid ? 1 : 0,
             data.calibrationIsDefault ? "provisional_default" : "field_calibrated",
             data.calibrationProfile.c_str(),
             SOIL_MOISTURE_AIR_ADC,
             SOIL_MOISTURE_WATER_ADC);

    if (data.calibrationValid) {
        CUS_DBGF("percent=%d state=%s error=%s\n", data.percent, data.state.c_str(), data.error.c_str());
    } else {
        CUS_DBGF("percent=NA state=%s error=%s\n", data.state.c_str(), data.error.c_str());
    }

    if (gHaveAirBaseline && data.readOk) {
        const int rawDelta = data.raw - gAirBaseline.raw;
        const long voltageDelta = static_cast<long>(data.voltageMv) -
                                  static_cast<long>(gAirBaseline.voltageMv);
        const char *windowRelation = data.rawMax < gAirBaseline.rawMin
                                         ? "below_air_window"
                                         : (data.rawMin > gAirBaseline.rawMax
                                                ? "above_air_window"
                                                : "overlaps_air_window");
        CUS_DBGF("[MOISTURE_V1_2][COMPARE] air_raw=%d air_mv=%lu delta_raw=%d delta_mv=%ld raw_window_relation=%s\n",
                 gAirBaseline.raw,
                 static_cast<unsigned long>(gAirBaseline.voltageMv),
                 rawDelta,
                 voltageDelta,
                 windowRelation);
    }

    CUS_DBGF("[MOISTURE_V1_2][CYCLE] ===== END seq=%lu =====\n",
             static_cast<unsigned long>(gCycleNo));
}

bool handleSerialCommand() {
    bool sampledAirBaseline = false;
    while (DEBUG_PORT.available() > 0) {
        const char command = static_cast<char>(DEBUG_PORT.read());
        if (command == 'a' || command == 'A') {
            runDiagnosticCycle("manual_air_baseline", true);
            gLastCycleMs = millis();
            sampledAirBaseline = true;
        } else if (command == '?') {
            printHelp();
        }
    }
    return sampledAirBaseline;
}

}  // namespace

void soilMoistureProbeBegin() {
    gSensor.begin();
    CUS_DBGF("[MOISTURE_V1_2][TEST] Capacitive analog diagnostic; ADC_GPIO=%u "
             "interval_ms=%lu samples=%u sample_gap_ms=%u air_adc=%d water_adc=%d\n",
             static_cast<unsigned>(SOIL_MOISTURE_ADC_PIN),
             static_cast<unsigned long>(SOIL_MOISTURE_TEST_INTERVAL_MS),
             static_cast<unsigned>(SOIL_MOISTURE_SAMPLE_COUNT),
             static_cast<unsigned>(SOIL_MOISTURE_SAMPLE_GAP_MS),
             SOIL_MOISTURE_AIR_ADC,
             SOIL_MOISTURE_WATER_ADC);
    CUS_DBGLN("[MOISTURE_V1_2][TEST] Wiring assumption: VCC=3V3, GND=GND, AOUT=ADC_GPIO; keep AOUT <= 3V3.");
    CUS_DBGF("[MOISTURE_V1_2][TEST] Profile=%s dry_adc=%d wet_adc=%d target_depth_cm=%.1f; percentage is a provisional relative index, not VWC.\n",
             SOIL_MOISTURE_CALIBRATION_PROFILE,
             SOIL_MOISTURE_AIR_ADC,
             SOIL_MOISTURE_WATER_ADC,
             static_cast<double>(SOIL_MOISTURE_CALIBRATION_TARGET_DEPTH_CM));
    printHelp();

    runDiagnosticCycle("boot_air_baseline", true);
    gLastCycleMs = millis();
}

void soilMoistureProbeLoop() {
    if (handleSerialCommand()) {
        return;
    }

    const uint32_t now = millis();
    if (now - gLastCycleMs >= SOIL_MOISTURE_TEST_INTERVAL_MS) {
        runDiagnosticCycle("interval");
        gLastCycleMs = now;
    }
}
