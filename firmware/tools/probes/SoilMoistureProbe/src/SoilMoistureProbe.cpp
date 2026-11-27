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

void runDiagnosticCycle(const char *reason) {
    ++gCycleNo;
    CUS_DBGF("\n[MOISTURE_V1_2][CYCLE] ===== START seq=%lu reason=%s =====\n",
             static_cast<unsigned long>(gCycleNo),
             reason ? reason : "unknown");

    SoilMoistureReading data;
    gSensor.read(data);
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

    CUS_DBGF("[MOISTURE_V1_2][CYCLE] ===== END seq=%lu =====\n",
             static_cast<unsigned long>(gCycleNo));
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
    CUS_DBGLN("[MOISTURE_V1_2][TEST] Move the probe through air, ordinary garden soil at the installed depth, and wet soil; retain raw/mV for later field recalibration.");

    runDiagnosticCycle("boot");
    gLastCycleMs = millis();
}

void soilMoistureProbeLoop() {
    const uint32_t now = millis();
    if (now - gLastCycleMs >= SOIL_MOISTURE_TEST_INTERVAL_MS) {
        runDiagnosticCycle("interval");
        gLastCycleMs = now;
    }
}
