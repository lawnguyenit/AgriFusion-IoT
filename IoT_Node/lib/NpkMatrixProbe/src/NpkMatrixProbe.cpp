#include "NpkMatrixProbe.h"

#include <Arduino.h>

#include "Config.h"
#include "NpkMatrixTest.h"

namespace {
HardwareSerial gNpkSerial(1);
NpkMatrixTest gMatrix(gNpkSerial);
}

void npkMatrixProbeBegin() {
    CUS_DBGF("[NPK][TEST] Dedicated read-only NPK Modbus matrix; UART=Serial1 baud=%lu format=8N1 RX=%d TX=%d slave=%u\n",
             static_cast<unsigned long>(NPK_BAUDRATE),
             NPK_RX_PIN,
             NPK_TX_PIN,
             NPK_MODBUS_SLAVE_ID);
    CUS_DBGLN("[NPK][TEST] One-shot boot diagnostic; no Modbus registers are written.");
    gMatrix.run();
}
