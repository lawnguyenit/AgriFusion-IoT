// Entry point for env:probe_npk_matrix (NEW in the refactor, not yet built or flashed).
// The old 600-line sketch that drove NpkMatrixTest lived in IoT_Node/main.cpp (#if 0);
// it is recoverable from branch snapshot/pre-refactor-2026-11. This minimal entry only
// runs the read-only Modbus matrix once and then idles.
#include <Arduino.h>

#include "Config.h"
#include "NpkMatrixTest.h"

namespace {
HardwareSerial gNpkSerial(1);
NpkMatrixTest gNpkMatrix(gNpkSerial);
}  // namespace

void setup() {
    DEBUG_PORT.begin(DEBUG_BAUDRATE);
    delay(300);
    gNpkMatrix.run();
}

void loop() {
    delay(1000);
}
