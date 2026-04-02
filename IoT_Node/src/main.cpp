#include <Arduino.h>

#include "Config.h"
#include "SimA7680C.h"

namespace {
constexpr uint32_t STATUS_PRINT_INTERVAL_MS = 10000;
constexpr uint32_t BOOT_RETRY_INTERVAL_MS = 15000;

bool gSimReady = false;
uint32_t gLastStatusPrintMs = 0;
uint32_t gLastBootRetryMs = 0;

void printBanner() {
    CUS_DBGLN();
    CUS_DBGLN("=== ESP32 SIM LINK TEST ===");
    CUS_DBGF("SIM UART: TX=%d RX=%d BAUD=%d\n", SIM_TX_PIN, SIM_RX_PIN, SIM_BAUDRATE);
    CUS_DBGF("APN: %s\n", SIM_APN);
    CUS_DBGLN("Muc tieu: kiem tra ESP giao tiep duoc voi modem va modem len duoc mang.");
}

void printStatusSnapshot(const char* stage, bool forceDump) {
    CUS_DBGLN();
    CUS_DBGF("[APP] stage=%s\n", stage ? stage : "na");
    CUS_DBGF("[APP] sim_ready=%d signal_dbm=%d ip=%s status_code=%d\n",
             gSimReady ? 1 : 0,
             simSignalDbm(),
             simLocalIP().c_str(),
             simStatusCode());
    dumpSimState(stage, forceDump);
}

bool bootSim() {
    CUS_DBGLN();
    CUS_DBGLN("[APP] Dang khoi tao SIM...");
    bool ok = setupSIM();
    gSimReady = ok;

    if (ok) {
        CUS_DBGLN("[APP] SIM test PASS: ESP da noi chuyen duoc voi modem.");
        printStatusSnapshot("boot_ok", true);
    } else {
        CUS_DBGLN("[APP] SIM test FAIL: chua khoi tao duoc modem hoac chua len mang.");
    }

    return ok;
}
}  // namespace

void setup() {
#if DEBUG_MODE
    Serial.begin(115200);
    delay(1200);
#endif

    printBanner();
    bootSim();
}

void loop() {
    uint32_t now = millis();

    if (!gSimReady) {
        if (now - gLastBootRetryMs >= BOOT_RETRY_INTERVAL_MS) {
            gLastBootRetryMs = now;
            CUS_DBGLN();
            CUS_DBGLN("[APP] Thu khoi tao SIM lai...");
            bootSim();
        }

        delay(200);
        return;
    }

    bool connected = checkNetwork();
    if (!connected) {
        CUS_DBGLN();
        CUS_DBGLN("[APP] SIM dang mat GPRS hoac dang trong qua trinh reconnect.");
    }

    if (now - gLastStatusPrintMs >= STATUS_PRINT_INTERVAL_MS) {
        gLastStatusPrintMs = now;
        printStatusSnapshot(connected ? "loop_ok" : "loop_retry", false);
    }

    delay(500);
}
