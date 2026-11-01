#include "SimUartLoopbackProbe.h"

#include <Arduino.h>

#include "Config.h"
#include "SimA7680C.h"

namespace {

constexpr char kLoopbackPattern[] = "UART2_GPIO17_TO_GPIO16\r\n";
constexpr size_t kLoopbackPatternLength = sizeof(kLoopbackPattern) - 1;
constexpr uint32_t kReceiveTimeoutMs = 250;
constexpr uint32_t kTestIntervalMs = 1000;

uint32_t gNextTestAtMs = 0;
uint32_t gTestNumber = 0;

void runLoopbackTest() {
    ++gTestNumber;

    while (SerialAT.available() > 0) {
        SerialAT.read();
    }

    SerialAT.write(reinterpret_cast<const uint8_t *>(kLoopbackPattern),
                   kLoopbackPatternLength);
    SerialAT.flush();

    uint8_t received[kLoopbackPatternLength] = {};
    size_t receivedLength = 0;
    const uint32_t startedAt = millis();
    while (receivedLength < kLoopbackPatternLength &&
           millis() - startedAt < kReceiveTimeoutMs) {
        while (SerialAT.available() > 0 && receivedLength < kLoopbackPatternLength) {
            received[receivedLength++] = static_cast<uint8_t>(SerialAT.read());
        }
        yield();
    }

    bool matches = receivedLength == kLoopbackPatternLength;
    for (size_t i = 0; matches && i < kLoopbackPatternLength; ++i) {
        matches = received[i] == static_cast<uint8_t>(kLoopbackPattern[i]);
    }

    CUS_DBGF("[SIM][UART_LOOPBACK] test=%lu pass=%d tx=%u rx=%u expected=%u timeout_ms=%lu\n",
             static_cast<unsigned long>(gTestNumber),
             matches ? 1 : 0,
             static_cast<unsigned>(kLoopbackPatternLength),
             static_cast<unsigned>(receivedLength),
             static_cast<unsigned>(kLoopbackPatternLength),
             static_cast<unsigned long>(kReceiveTimeoutMs));
    if (!matches && receivedLength > 0) {
        CUS_DBG("[SIM][UART_LOOPBACK] received_hex=");
        for (size_t i = 0; i < receivedLength; ++i) {
            CUS_DBGF("%02X", received[i]);
            if (i + 1 < receivedLength) CUS_DBG(" ");
        }
        CUS_DBGLN("");
    }

    gNextTestAtMs = millis() + kTestIntervalMs;
}

}  // namespace

void simUartLoopbackProbeBegin() {
    CUS_DBGLN("\n=== ESP32-S3 UART2 LOOPBACK TEST ===");
    CUS_DBGF("[SIM][UART_LOOPBACK] bridge ESP GPIO%u TX directly to ESP GPIO%u RX; disconnect modem and level shifter\n",
             static_cast<unsigned>(SIM_TX_PIN),
             static_cast<unsigned>(SIM_RX_PIN));
    CUS_DBGF("[SIM][UART_LOOPBACK] baud=%lu format=8N1 pattern_bytes=%u repeat_ms=%lu\n",
             static_cast<unsigned long>(SIM_BAUDRATE),
             static_cast<unsigned>(kLoopbackPatternLength),
             static_cast<unsigned long>(kTestIntervalMs));

    SerialAT.begin(SIM_BAUDRATE, SERIAL_8N1, SIM_RX_PIN, SIM_TX_PIN);
    runLoopbackTest();
}

void simUartLoopbackProbeLoop() {
    if (static_cast<int32_t>(millis() - gNextTestAtMs) < 0) {
        delay(20);
        return;
    }
    runLoopbackTest();
}
