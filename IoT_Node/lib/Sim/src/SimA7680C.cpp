#include "SimA7680C.h"

#include "Config.h"
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

HardwareSerial SerialAT(2);
TinyGsm modem(SerialAT);
TinyGsmClient client(modem);

namespace {
static int gRestartCount = 0;
static const int MAX_RETRY = 5;
static uint32_t gLastReconnectAttemptMs = 0;
static uint32_t gLastRestartMs = 0;
static uint32_t gLastDiagMs = 0;
static const uint32_t DIAG_INTERVAL_MS = 30000;
static const uint32_t REG_AT_TIMEOUT_MS = 350;
static const uint32_t RAW_AT_TIMEOUT_MS = 1200;
static const uint32_t RAW_AT_TIMEOUT_BRIEF_MS = 250;

void yieldToScheduler(uint32_t ms = 1) {
    vTaskDelay(pdMS_TO_TICKS(ms));
}

void drainSerialAT() {
    while (SerialAT.available()) {
        SerialAT.read();
    }
}

String runRawAt(const char *cmd, uint32_t timeoutMs = RAW_AT_TIMEOUT_MS) {
    drainSerialAT();
    SerialAT.print("AT");
    SerialAT.print(cmd);
    SerialAT.print("\r\n");

    String response;
    uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        while (SerialAT.available()) {
            char c = (char)SerialAT.read();
            response += c;
        }

        if (response.indexOf("\r\nOK\r\n") >= 0 || response.indexOf("\r\nERROR\r\n") >= 0) {
            break;
        }
        yieldToScheduler();
    }

    response.trim();
    return response.length() ? response : String("<no response>");
}

void printAtQuery(const char *label, const char *cmd, uint32_t timeoutMs) {
    CUS_DBGF("[SIM][AT] %s => %s\n", label, runRawAt(cmd, timeoutMs).c_str());
    yieldToScheduler();
}

bool waitForAtReady(uint32_t attempts, uint32_t retryDelayMs) {
    for (uint32_t i = 0; i < attempts; ++i) {
        String response = runRawAt("", RAW_AT_TIMEOUT_BRIEF_MS);
        bool ok = response.indexOf("OK") >= 0;
        CUS_DBGF("[SIM][AT] probe %lu/%lu => %s\n",
                 (unsigned long)(i + 1),
                 (unsigned long)attempts,
                 response.c_str());
        if (ok) {
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(retryDelayMs));
    }
    return false;
}

const char *simStatusText(SimStatus sim) {
    if (sim == SIM_READY) return "READY";
    if (sim == SIM_LOCKED) return "LOCKED";
    if (sim == SIM_ERROR) return "ERROR";
    if (sim == SIM_ANTITHEFT_LOCKED) return "ANTITHEFT_LOCKED";
    return "unknown";
}

bool regCreg() {
    modem.sendAT("+CREG?");
    int8_t r = modem.waitResponse(REG_AT_TIMEOUT_MS,
                                  "+CREG: 0,1", "+CREG: 0,5",
                                  "+CREG: 1,1", "+CREG: 1,5",
                                  "+CREG: 2,1", "+CREG: 2,5");
    return r >= 1 && r <= 6;
}

bool regCgreg() {
    modem.sendAT("+CGREG?");
    int8_t r = modem.waitResponse(REG_AT_TIMEOUT_MS,
                                  "+CGREG: 0,1", "+CGREG: 0,5",
                                  "+CGREG: 1,1", "+CGREG: 1,5",
                                  "+CGREG: 2,1", "+CGREG: 2,5");
    return r >= 1 && r <= 6;
}

bool regCereg() {
    modem.sendAT("+CEREG?");
    int8_t r = modem.waitResponse(REG_AT_TIMEOUT_MS,
                                  "+CEREG: 0,1", "+CEREG: 0,5",
                                  "+CEREG: 1,1", "+CEREG: 1,5",
                                  "+CEREG: 2,1", "+CEREG: 2,5");
    return r >= 1 && r <= 6;
}

bool isCellRegisteredAny() {
    if (modem.isNetworkConnected()) {
        return true;
    }
    return regCreg() || regCgreg() || regCereg();
}

bool isPacketAttached() {
    modem.sendAT("+CGATT?");
    int8_t r = modem.waitResponse(REG_AT_TIMEOUT_MS, "+CGATT: 1", "+CGATT: 0");
    return r == 1;
}

void printCellDiagnostic(const char *stage) {
    uint32_t now = millis();
    if (now - gLastDiagMs < DIAG_INTERVAL_MS) {
        return;
    }
    gLastDiagMs = now;

    auto sim = modem.getSimStatus();
    int csq = modem.getSignalQuality();
    CUS_DBGF("[SIM][DIAG] stage=%s sim=%s csq=%d reg(creg=%d cgreg=%d cereg=%d) attach=%d ip=%s\n",
             stage ? stage : "na",
             simStatusText(sim),
             csq,
             regCreg() ? 1 : 0,
             regCgreg() ? 1 : 0,
             regCereg() ? 1 : 0,
             isPacketAttached() ? 1 : 0,
             modem.getLocalIP().c_str());
}

bool waitForNetwork(int timeoutSec) {
    for (int i = 0; i < timeoutSec * 2; i++) {
        if (isCellRegisteredAny()) {
            return true;
        }
        CUS_DBG(".");
        delay(500);
    }
    return false;
}
}  // namespace

void dumpSimState(const char *stage, bool force) {
    uint32_t now = millis();
    if (!force && (now - gLastDiagMs < DIAG_INTERVAL_MS)) {
        return;
    }
    gLastDiagMs = now;

    SimStatus sim = modem.getSimStatus();
    int csq = modem.getSignalQuality();
    bool net = modem.isNetworkConnected();
    bool gprs = modem.isGprsConnected();
    bool attached = isPacketAttached();

    CUS_DBGLN("\n[SIM][STATE] ===== MODEM SNAPSHOT =====");
    CUS_DBGF("[SIM][STATE] stage=%s\n", stage ? stage : "na");
    CUS_DBGF("[SIM][STATE] sim=%s csq=%d dbm=%d net=%d gprs=%d attach=%d ip=%s\n",
             simStatusText(sim),
             csq,
             simSignalDbm(),
             net ? 1 : 0,
             gprs ? 1 : 0,
             attached ? 1 : 0,
             modem.getLocalIP().c_str());
    CUS_DBGF("[SIM][STATE] operator=%s\n", modem.getOperator().c_str());

    bool brief = (stage && strcmp(stage, "init_fail") == 0);
    if (brief) {
        printAtQuery("AT", "", RAW_AT_TIMEOUT_BRIEF_MS);
        printAtQuery("AT+CPIN?", "+CPIN?", RAW_AT_TIMEOUT_BRIEF_MS);
        printAtQuery("AT+CSQ", "+CSQ", RAW_AT_TIMEOUT_BRIEF_MS);
    } else {
        printAtQuery("AT", "", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CPIN?", "+CPIN?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CSQ", "+CSQ", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CREG?", "+CREG?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CGREG?", "+CGREG?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CEREG?", "+CEREG?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CGATT?", "+CGATT?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+COPS?", "+COPS?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CGNAPN", "+CGNAPN", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CGPADDR=1", "+CGPADDR=1", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CFUN?", "+CFUN?", RAW_AT_TIMEOUT_MS);
    }

    CUS_DBGLN("[SIM][STATE] ===========================");
}

bool setupSIM() {
    SerialAT.begin(SIM_BAUDRATE, SERIAL_8N1, SIM_RX_PIN, SIM_TX_PIN);
    SerialAT.setTimeout(50);
    vTaskDelay(pdMS_TO_TICKS(SIM_BOOT_WAIT_MS));

    CUS_DBGLN("\n[SIM] --- BAT DAU KHOI DONG ---");
    CUS_DBGF("[SIM] Cho modem boot %lu ms\n", (unsigned long)SIM_BOOT_WAIT_MS);

    CUS_DBG("[SIM] Kiem tra AT handshake...");
    if (!waitForAtReady(SIM_AT_READY_RETRY_COUNT, SIM_AT_READY_RETRY_DELAY_MS)) {
        CUS_DBGLN(" -> FAIL");
        CUS_DBGLN("[SIM] -> LOI: Modem khong san sang tren UART.");
        dumpSimState("init_fail", true);
        return false;
    }
    CUS_DBGLN(" -> OK");

    CUS_DBG("[SIM] Init Modem...");
    if (!modem.init()) {
        CUS_DBGLN(" -> FAIL");
        CUS_DBGLN("[SIM] Thu init lai sau AT handshake...");
        if (!waitForAtReady(4, SIM_AT_READY_RETRY_DELAY_MS)) {
            CUS_DBGLN("[SIM] -> LOI: UART co luc mat dong bo sau boot.");
            dumpSimState("init_fail", true);
            return false;
        }

        if (!modem.init()) {
            CUS_DBGLN("[SIM] -> LOI: TinyGSM init fail du da co AT.");
            dumpSimState("init_fail", true);
            return false;
        }
    }
    CUS_DBGLN(" -> OK");
    dumpSimState("after_init", true);

    CUS_DBG("[SIM] Dang tim song");
    if (!waitForNetwork(25)) {
        CUS_DBGLN("\n[SIM] -> LOI: Mat song dien thoai!");
        printCellDiagnostic("setup_no_signal");
        dumpSimState("network_search_timeout", true);
        return false;
    }
    CUS_DBGLN(" -> Co song roi!");
    printCellDiagnostic("setup_registered");
    dumpSimState("registered", true);

    CUS_DBG("[SIM] Dang ket noi 4G (");
    CUS_DBG(SIM_APN);
    CUS_DBG(")...");
    if (!modem.gprsConnect(SIM_APN, SIM_APN_USER, SIM_APN_PASS)) {
        CUS_DBGLN(" -> LOI: GPRS Failed!");
        printCellDiagnostic("setup_gprs_fail");
        dumpSimState("gprs_connect_fail", true);
        return false;
    }
    CUS_DBGLN(" -> Internet OK");
    dumpSimState("gprs_connected", true);

    gRestartCount = 0;
    checkInfo();
    return true;
}

bool checkNetwork() {
    if (modem.isGprsConnected()) {
        gRestartCount = 0;
        return true;
    }

    uint32_t now = millis();
    if (now - gLastReconnectAttemptMs < SIM_RECONNECT_INTERVAL_MS) {
        return false;
    }
    gLastReconnectAttemptMs = now;

    CUS_DBGLN("\n[SIM] MAT KET NOI INTERNET!");
    dumpSimState("network_lost", false);
    if (gRestartCount < MAX_RETRY) {
        gRestartCount++;
        CUS_DBGF("[SIM] Dang thu ket noi lai (Lan %d/%d)", gRestartCount, MAX_RETRY);

        if (!isCellRegisteredAny()) {
            CUS_DBGLN(" -> Chua dang ky mang (skip reconnect lan nay).");
            dumpSimState("not_registered", true);
            return false;
        }

        if (isCellRegisteredAny()) {
            CUS_DBG(" -> Co song -> Reconnecting GPRS...");
            if (modem.gprsConnect(SIM_APN, SIM_APN_USER, SIM_APN_PASS)) {
                CUS_DBGLN(" -> OK!");
                dumpSimState("reconnect_ok", true);
                gRestartCount = 0;
                return true;
            }
            CUS_DBGLN(" -> That bai!");
            dumpSimState("reconnect_fail", true);
        }

        if (gRestartCount == MAX_RETRY) {
            if (now - gLastRestartMs < SIM_RESTART_COOLDOWN_MS) {
                CUS_DBGLN("\n[SIM] Tam hoan restart modem (cooldown).");
                dumpSimState("restart_cooldown", true);
                return false;
            }
            CUS_DBGLN("\n[SIM] Qua nhieu lan that bai -> KHOI DONG LAI MODEM...");
            if (modem.restart()) {
                gLastRestartMs = now;
                dumpSimState("after_restart", true);
            }
            gRestartCount = 0;
            delay(3000);
        }
    }

    return false;
}

void checkInfo() {
#if DEBUG_MODE
    CUS_DBGLN("\n=== THONG TIN SIM ===");
    if (modem.testAT()) {
        CUS_DBGF("Operator: %s\n", modem.getOperator().c_str());
        CUS_DBGF("Signal:   %d %%\n", modem.getSignalQuality());
        CUS_DBGF("IP:       %s\n", modem.getLocalIP().c_str());
        dumpSimState("check_info", true);
    } else {
        CUS_DBGLN("Modem khong phan hoi!");
    }
    CUS_DBGLN("=====================");
#endif
}

int simSignalDbm() {
    int csq = modem.getSignalQuality();
    if (csq <= 0 || csq == 99) {
        return 0;
    }
    // 3GPP CSQ to dBm.
    return -113 + (2 * csq);
}

String simLocalIP() {
    return modem.getLocalIP();
}

int simStatusCode() {
    return modem.isGprsConnected() ? 3 : 0;
}
