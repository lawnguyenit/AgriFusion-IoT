#include "SimA7680C.h"

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "Config.h"
#include "SimHttpClient.h"
#include "SimSocketTransport.h"

HardwareSerial SerialAT(2);

namespace {
static int gRestartCount = 0;
static const int MAX_RETRY = 5;
static uint32_t gLastReconnectAttemptMs = 0;
static uint32_t gLastRestartMs = 0;
static uint32_t gLastDiagMs = 0;
static uint32_t gLastIpRefreshMs = 0;
static const uint32_t DIAG_INTERVAL_MS = 30000;
static const uint32_t IP_REFRESH_INTERVAL_MS = 3000;
static const uint32_t RAW_AT_TIMEOUT_MS = 1200;
static const uint32_t RAW_AT_TIMEOUT_BRIEF_MS = 250;
static const uint32_t LONG_AT_TIMEOUT_MS = 15000;
static const uint32_t NETWORK_WAIT_SLICE_MS = 500;
static String gLastResolvedIp = "0.0.0.0";
static SemaphoreHandle_t gAtPortMutex = nullptr;

String runRawAt(const char *cmd, uint32_t timeoutMs = RAW_AT_TIMEOUT_MS);
String runRawAt(const String &cmd, uint32_t timeoutMs = RAW_AT_TIMEOUT_MS);
bool waitForAtReady(uint32_t timeoutMs, uint32_t retryDelayMs);
bool responseHasAny(const String &response, const char *const *patterns, size_t count);
String runRawAtWaitPatterns(const String &cmd,
                            uint32_t timeoutMs,
                            const char *const *patterns,
                            size_t patternCount);
bool configurePacketSessionProfile(const char *pdpType, bool forceReconnect, String *detail = nullptr);
bool configurePacketSessionWithRecovery(bool forceReconnect, String *detail = nullptr);
bool rawInternetProbe(RawSimHttpProbeResult &result);
bool waitForNetworkYielding(uint32_t timeoutMs);
bool isCellRegisteredAny();
bool isPacketAttached();
bool isPdpContextActive();
String compactAtResponse(const String &response);

void ensureAtPortMutex() {
    if (!gAtPortMutex) {
        gAtPortMutex = xSemaphoreCreateRecursiveMutex();
    }
}

void yieldToScheduler(uint32_t ms = 1) {
    vTaskDelay(pdMS_TO_TICKS(ms));
}

void drainSerialAT() {
    while (SerialAT.available()) {
        SerialAT.read();
    }
}

bool lineEndsWithToken(const String &response, const char *token) {
    String s = response;
    s.trim();
    if (s == token) {
        return true;
    }
    String suffix = String("\n") + token;
    return s.endsWith(suffix);
}

bool atResponseIsOk(const String &response) {
    return lineEndsWithToken(response, "OK") || lineEndsWithToken(response, "0");
}

bool atResponseIsError(const String &response) {
    return lineEndsWithToken(response, "ERROR") || lineEndsWithToken(response, "4");
}

bool atResponseIsFinal(const String &response) {
    return atResponseIsOk(response) || atResponseIsError(response);
}

bool isAsciiDigit(char c) {
    return c >= '0' && c <= '9';
}

String compactAtResponse(const String &response) {
    String out = response;
    out.replace("\r", " ");
    out.replace("\n", " | ");
    out.trim();
    if (!out.length()) {
        return "empty";
    }
    return out;
}

String stripEchoedCommand(const String &response, const String &cmd) {
    String out = response;
    String echoed = "AT" + cmd;
    if (out.startsWith(echoed + "\r\r\n")) {
        out.remove(0, echoed.length() + 3);
    } else if (out.startsWith(echoed + "\r\n")) {
        out.remove(0, echoed.length() + 2);
    } else if (out.startsWith(echoed + "\n")) {
        out.remove(0, echoed.length() + 1);
    } else if (out.startsWith(echoed)) {
        out.remove(0, echoed.length());
    }
    out.trim();
    return out;
}

bool responseContains(const String &response, const char *needle) {
    return needle && response.indexOf(needle) >= 0;
}

bool responseHasAny(const String &response, const char *const *patterns, size_t count) {
    if (!patterns) {
        return false;
    }
    for (size_t i = 0; i < count; ++i) {
        if (patterns[i] && response.indexOf(patterns[i]) >= 0) {
            return true;
        }
    }
    return false;
}

String runRawAtWaitPatterns(const String &cmd,
                            uint32_t timeoutMs,
                            const char *const *patterns,
                            size_t patternCount) {
    if (!simAcquireAtPort(timeoutMs + 1000UL)) {
        return "<lock timeout>";
    }

    drainSerialAT();
    SerialAT.print("AT");
    SerialAT.print(cmd);
    SerialAT.print("\r\n");

    String response;
    uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        while (SerialAT.available()) {
            response += static_cast<char>(SerialAT.read());
        }

        if (responseHasAny(response, patterns, patternCount) || atResponseIsFinal(response)) {
            break;
        }
        yieldToScheduler();
    }

    response = stripEchoedCommand(response, cmd);
    response.trim();
    String out = response.length() ? response : String("<no response>");
    simReleaseAtPort();
    return out;
}

String runRawAt(const char *cmd, uint32_t timeoutMs) {
    static const char *const patterns[] = {"OK", "ERROR", ">"};
    return runRawAtWaitPatterns(cmd, timeoutMs, patterns, sizeof(patterns) / sizeof(patterns[0]));
}

String runRawAt(const String &cmd, uint32_t timeoutMs) {
    return runRawAt(cmd.c_str(), timeoutMs);
}

bool runRawAtOk(const char *cmd, uint32_t timeoutMs = RAW_AT_TIMEOUT_MS) {
    return atResponseIsOk(runRawAt(cmd, timeoutMs));
}

bool runRawAtOk(const String &cmd, uint32_t timeoutMs = RAW_AT_TIMEOUT_MS) {
    return atResponseIsOk(runRawAt(cmd, timeoutMs));
}

String extractFirstIpv4(const String &text) {
    String candidate;
    for (size_t i = 0; i < text.length(); ++i) {
        char c = text[i];
        if (isAsciiDigit(c) || c == '.') {
            candidate += c;
        } else if (!candidate.isEmpty()) {
            int parts = 0;
            int start = 0;
            bool valid = true;
            while (start < candidate.length()) {
                int end = candidate.indexOf('.', start);
                if (end < 0) {
                    end = candidate.length();
                }
                if (end == start) {
                    valid = false;
                    break;
                }
                if (++parts > 4) {
                    valid = false;
                    break;
                }

                int value = 0;
                for (int j = start; j < end; ++j) {
                    char digit = candidate[j];
                    if (!isAsciiDigit(digit)) {
                        valid = false;
                        break;
                    }
                    value = (value * 10) + (digit - '0');
                    if (value > 255) {
                        valid = false;
                        break;
                    }
                }
                if (!valid) {
                    break;
                }
                start = end + 1;
            }
            if (valid && parts == 4) {
                return candidate;
            }
            candidate = "";
        }
    }

    return "";
}

bool isValidIpv4(const String &ip) {
    return extractFirstIpv4(ip) == ip;
}

String queryCgpaddrIpv4() {
    const char *const commands[] = {
        "+CGPADDR=1",
        "+CGPADDR?",
        "+CGCONTRDP=1",
        "+CGDCONT?"
    };

    for (size_t cmdIndex = 0; cmdIndex < sizeof(commands) / sizeof(commands[0]); ++cmdIndex) {
        for (int attempt = 0; attempt < 2; ++attempt) {
            uint32_t timeoutMs = attempt == 0 ? RAW_AT_TIMEOUT_MS : LONG_AT_TIMEOUT_MS;
            String response = runRawAt(commands[cmdIndex], timeoutMs);
            if (response != "<no response>" && response != "<lock timeout>") {
                String ip = extractFirstIpv4(response);
                if (isValidIpv4(ip) && ip != "0.0.0.0") {
                    return ip;
                }
            }
            yieldToScheduler(80);
        }
    }

    for (int attempt = 0; attempt < 3; ++attempt) {
        uint32_t timeoutMs = attempt == 0 ? RAW_AT_TIMEOUT_MS : LONG_AT_TIMEOUT_MS;
        String response = runRawAt("+CGPADDR=1", timeoutMs);
        if (response != "<no response>" && response != "<lock timeout>") {
            String ip = extractFirstIpv4(response);
            if (isValidIpv4(ip) && ip != "0.0.0.0") {
                return ip;
            }
        }
        yieldToScheduler(150);
    }
    return "";
}

String resolveLocalIp(bool forceRefresh = false) {
    uint32_t now = millis();
    if (!forceRefresh && (now - gLastIpRefreshMs < IP_REFRESH_INTERVAL_MS)) {
        return gLastResolvedIp;
    }

    String ip = queryCgpaddrIpv4();
    if (!isValidIpv4(ip)) {
        if (isValidIpv4(gLastResolvedIp) && gLastResolvedIp != "0.0.0.0") {
            gLastIpRefreshMs = now;
            return gLastResolvedIp;
        }
        ip = "0.0.0.0";
    }

    gLastResolvedIp = ip;
    gLastIpRefreshMs = now;
    return gLastResolvedIp;
}

String extractQuotedValue(const String &response) {
    int firstQuote = response.indexOf('"');
    if (firstQuote < 0) {
        return "";
    }
    int secondQuote = response.indexOf('"', firstQuote + 1);
    if (secondQuote < 0) {
        return "";
    }
    return response.substring(firstQuote + 1, secondQuote);
}

int parseFirstIntegerAfter(const String &response, const char *prefix) {
    int start = response.indexOf(prefix);
    if (start < 0) {
        return -1;
    }
    start += strlen(prefix);

    while (start < response.length() && !(response[start] == '-' || isAsciiDigit(response[start]))) {
        ++start;
    }
    if (start >= response.length()) {
        return -1;
    }

    String value;
    if (response[start] == '-') {
        value += response[start++];
    }
    while (start < response.length() && isAsciiDigit(response[start])) {
        value += response[start++];
    }
    return value.length() ? value.toInt() : -1;
}

int querySignalCsq() {
    return parseFirstIntegerAfter(runRawAt("+CSQ", RAW_AT_TIMEOUT_MS), "+CSQ:");
}

String queryOperatorName() {
    String response = runRawAt("+COPS?", RAW_AT_TIMEOUT_MS);
    String quoted = extractQuotedValue(response);
    if (quoted.length()) {
        return quoted;
    }
    return compactAtResponse(response);
}

String queryPinState() {
    String response = runRawAt("+CPIN?", RAW_AT_TIMEOUT_MS);
    int colon = response.indexOf(':');
    if (colon < 0) {
        return compactAtResponse(response);
    }
    int lineEnd = response.indexOf('\n', colon);
    String value = (lineEnd >= 0) ? response.substring(colon + 1, lineEnd) : response.substring(colon + 1);
    value.trim();
    return value;
}

bool simReadyRaw() {
    return queryPinState() == "READY";
}

bool responseIndicatesRegistered(const String &response, const char *prefix) {
    String p(prefix);
    return response.indexOf(p + " 0,1") >= 0 ||
           response.indexOf(p + " 0,5") >= 0 ||
           response.indexOf(p + " 1,1") >= 0 ||
           response.indexOf(p + " 1,5") >= 0 ||
           response.indexOf(p + " 2,1") >= 0 ||
           response.indexOf(p + " 2,5") >= 0;
}

bool regCreg() {
    return responseIndicatesRegistered(runRawAt("+CREG?", RAW_AT_TIMEOUT_MS), "+CREG:");
}

bool regCgreg() {
    return responseIndicatesRegistered(runRawAt("+CGREG?", RAW_AT_TIMEOUT_MS), "+CGREG:");
}

bool regCereg() {
    return responseIndicatesRegistered(runRawAt("+CEREG?", RAW_AT_TIMEOUT_MS), "+CEREG:");
}

bool isCellRegisteredAny() {
    return regCreg() || regCgreg() || regCereg();
}

bool isPacketAttached() {
    return responseContains(runRawAt("+CGATT?", RAW_AT_TIMEOUT_MS), "+CGATT: 1");
}

bool isPdpContextActive() {
    String response = runRawAt("+CGACT?", RAW_AT_TIMEOUT_MS);
    return responseContains(response, "+CGACT: 1,1");
}

bool rawInternetProbe(RawSimHttpProbeResult &result) {
    result = runRawSimHttpProbe(SIM_TEST_DNS_HOST,
                                SIM_TEST_DNS_PORT,
                                "/",
                                SIM_TEST_DNS_HOST,
                                SIM_TEST_SOCKET_TIMEOUT_MS);
    return result.headerOk;
}

bool packetSessionLooksUsable(const SimNetworkState &state) {
    return state.simReady &&
           state.networkRegistered &&
           state.packetAttached &&
           state.gprsConnected;
}

bool modemHttpSessionLooksUsable() {
    SimHttpClient http;
    SimHttpRequest request;
    request.method = SimHttpMethod::Get;
    request.url = APP_SIM_HTTP_PROBE_URL;
    request.readHeader = true;
    request.readBody = false;
    request.actionTimeoutMs = 30000;

    SimHttpResponse response;
    http.perform(request, response);
    return response.transportOk;
}

bool waitForNetworkYielding(uint32_t timeoutMs) {
    uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        if (isCellRegisteredAny()) {
            return true;
        }
        CUS_DBG(".");
        yieldToScheduler(NETWORK_WAIT_SLICE_MS);
    }
    return false;
}

bool configurePacketSessionProfile(const char *pdpType, bool forceReconnect, String *detail) {
    String steps;
    const char *profile = (pdpType && strlen(pdpType)) ? pdpType : SIM_PDP_TYPE;

    if (forceReconnect) {
        steps += "NETCLOSE;";
        runRawAt("+NETCLOSE", 5000);
        steps += "CGACT0;";
        runRawAt("+CGACT=0,1", 5000);
        steps += "CGATT0;";
        runRawAt("+CGATT=0", 5000);
        yieldToScheduler(200);
    }

    String cgdcont = String("+CGDCONT=1,\"") + profile + "\",\"" + SIM_APN + "\"";
    if (!runRawAtOk(cgdcont, 5000)) {
        if (detail) {
            *detail = String("CGDCONT_FAIL profile=") + profile;
        }
        return false;
    }
    steps += "CGDCONT;";

    String cgact = runRawAt("+CGACT=1,1", LONG_AT_TIMEOUT_MS);
    if (!atResponseIsOk(cgact) && !responseContains(cgact, "+CGACT:")) {
        if (detail) {
            *detail = String("CGACT_FAIL profile=") + profile;
        }
        return false;
    }
    steps += "CGACT1;";

    if (!isPacketAttached() && !runRawAtOk("+CGATT=1", LONG_AT_TIMEOUT_MS)) {
        if (detail) {
            *detail = String("CGATT_FAIL profile=") + profile;
        }
        return false;
    }
    steps += "CGATT1;";

    if (!runRawAtOk("+CIPRXGET=1", 3000)) {
        if (detail) {
            *detail = String("CIPRXGET_FAIL profile=") + profile;
        }
        return false;
    }
    steps += "CIPRXGET1;";

    String ip = resolveLocalIp(true);
    if (isValidIpv4(ip) && ip != "0.0.0.0") {
        steps += "CGPADDR;";
    } else {
        steps += "CGPADDR_UNCERTAIN;";
    }

    if (!runRawAtOk("+CDNSCFG=\"8.8.8.8\",\"1.1.1.1\"", 3000)) {
        if (detail) {
            *detail = String("CDNSCFG_FAIL profile=") + profile;
        }
        return false;
    }
    steps += "CDNSCFG;";

    if (detail) {
        *detail = String("profile=") + profile + " steps=" + steps;
    }
    return true;
}

bool configurePacketSessionWithRecovery(bool forceReconnect, String *detail) {
    struct ProfileTry {
        const char *pdpType;
        const char *label;
    };

    ProfileTry profiles[2] = {
        {SIM_PDP_TYPE, "base"},
        {"IPV4V6", "ipv4v6"}
    };

    String summary;
    const int count = SIM_TEST_TRY_IPV4V6_PROFILE ? 2 : 1;
    for (int i = 0; i < count; ++i) {
        if (i > 0 && String(profiles[i].pdpType) == String(profiles[0].pdpType)) {
            continue;
        }

        String oneDetail;
        bool ok = configurePacketSessionProfile(profiles[i].pdpType, forceReconnect && i == 0, &oneDetail);
        if (summary.length()) {
            summary += " | ";
        }
        summary += profiles[i].label;
        summary += ":";
        summary += ok ? "ok," : "fail,";
        summary += oneDetail;

        if (ok) {
            if (detail) {
                *detail = summary;
            }
            return true;
        }

        if (forceReconnect) {
            runRawAt("+NETCLOSE", 5000);
            runRawAt("+CGACT=0,1", 5000);
            runRawAt("+CGATT=0", 5000);
            yieldToScheduler(200);
        }
    }

    if (detail) {
        *detail = summary;
    }
    return false;
}

bool softRestartModem() {
    CUS_DBGLN("[SIM] Gui lenh soft reset modem...");
    runRawAt("+CRESET", 5000);
    gLastResolvedIp = "0.0.0.0";
    yieldToScheduler(3000);
    return waitForAtReady(SIM_AT_RESPONSE_TIMEOUT_MS, SIM_AT_READY_RETRY_DELAY_MS);
}

void printAtQuery(const char *label, const char *cmd, uint32_t timeoutMs) {
#if SIM_VERBOSE_AT_QUERY_LOG
    CUS_DBGF("[SIM][AT] %s => %s\n", label, runRawAt(cmd, timeoutMs).c_str());
    yieldToScheduler();
#else
    (void)label;
    (void)cmd;
    (void)timeoutMs;
#endif
}

bool waitForAtReady(uint32_t timeoutMs, uint32_t retryDelayMs) {
    uint32_t start = millis();
    uint32_t probe = 0;

    while (millis() - start < timeoutMs) {
        ++probe;
        String response = runRawAt("", RAW_AT_TIMEOUT_BRIEF_MS);
        bool ok = atResponseIsOk(response);
        CUS_DBGF("[SIM][AT] probe %lu (elapsed=%lu/%lu ms) => %s\n",
                 (unsigned long)probe,
                 (unsigned long)(millis() - start),
                 (unsigned long)timeoutMs,
                 response.c_str());
        if (ok) {
            return true;
        }
        vTaskDelay(pdMS_TO_TICKS(retryDelayMs));
    }
    return false;
}

bool normalizeAtMode() {
    String v1 = runRawAt("V1", 800);
    String e0 = runRawAt("E0", 800);
    bool ok = atResponseIsOk(v1) || atResponseIsOk(e0);
    CUS_DBGF("[SIM][AT] ATV1 => %s\n", v1.c_str());
    CUS_DBGF("[SIM][AT] ATE0 => %s\n", e0.c_str());
    return ok;
}

const char *simStatusText(bool simReady) {
    return simReady ? "READY" : "NOT_READY";
}

bool testInternetSocket() {
    RawSimHttpProbeResult probe;
    CUS_DBG("[SIM] Test raw HTTP toi neverssl.com:80...");
    bool ok = rawInternetProbe(probe);
    CUS_DBGF(" -> %s (%s,%s)\n",
             ok ? "OK" : "FAIL",
             probe.stage.c_str(),
             probe.detail.c_str());
    return ok;
}

void printCellDiagnostic(const char *stage) {
    uint32_t now = millis();
    if (now - gLastDiagMs < DIAG_INTERVAL_MS) {
        return;
    }
    gLastDiagMs = now;

    int csq = querySignalCsq();
    CUS_DBGF("[SIM][DIAG] stage=%s sim=%s csq=%d reg(creg=%d cgreg=%d cereg=%d) attach=%d cgact=%d ip=%s\n",
             stage ? stage : "na",
             simStatusText(simReadyRaw()),
             csq,
             regCreg() ? 1 : 0,
             regCgreg() ? 1 : 0,
             regCereg() ? 1 : 0,
             isPacketAttached() ? 1 : 0,
             isPdpContextActive() ? 1 : 0,
             resolveLocalIp().c_str());
}

bool waitForNetwork(int timeoutSec) {
    return waitForNetworkYielding(static_cast<uint32_t>(timeoutSec) * 1000UL);
}
}  // namespace

void dumpSimState(const char *stage, bool force) {
    uint32_t now = millis();
    if (!force && (now - gLastDiagMs < DIAG_INTERVAL_MS)) {
        return;
    }
    gLastDiagMs = now;

    SimNetworkState state = simReadNetworkState(true);
    int csq = querySignalCsq();

    CUS_DBGLN("\n[SIM][STATE] ===== MODEM SNAPSHOT =====");
    CUS_DBGF("[SIM][STATE] stage=%s\n", stage ? stage : "na");
    CUS_DBGF("[SIM][STATE] sim=%s csq=%d dbm=%d net=%d gprs=%d attach=%d ip=%s\n",
             simStatusText(state.simReady),
             csq,
             state.signalDbm,
             state.networkRegistered ? 1 : 0,
             state.gprsConnected ? 1 : 0,
             state.packetAttached ? 1 : 0,
             state.localIp.c_str());
    CUS_DBGF("[SIM][STATE] operator=%s\n", state.operatorName.c_str());

#if SIM_VERBOSE_AT_QUERY_LOG
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
        printAtQuery("AT+CGACT?", "+CGACT?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+COPS?", "+COPS?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CGNAPN", "+CGNAPN", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CGPADDR=1", "+CGPADDR=1", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+NETOPEN?", "+NETOPEN?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CFUN?", "+CFUN?", RAW_AT_TIMEOUT_MS);
        printAtQuery("AT+CCLK?", "+CCLK?", RAW_AT_TIMEOUT_MS);
    }
#endif

    CUS_DBGLN("[SIM][STATE] ===========================");
}

bool setupSIM() {
    SerialAT.begin(SIM_BAUDRATE, SERIAL_8N1, SIM_RX_PIN, SIM_TX_PIN);
    SerialAT.setTimeout(50);
    gLastResolvedIp = "0.0.0.0";

    CUS_DBGLN("\n[SIM] --- BAT DAU KHOI DONG ---");
    if (SIM_BOOT_WAIT_MS > 0) {
        CUS_DBGF("[SIM] Cho modem on dinh sau cap nguon %lu ms\n", (unsigned long)SIM_BOOT_WAIT_MS);
        yieldToScheduler(SIM_BOOT_WAIT_MS);
    }
    CUS_DBGF("[SIM] Cho modem phan hoi toi da %lu ms\n", (unsigned long)SIM_AT_RESPONSE_TIMEOUT_MS);

    CUS_DBG("[SIM] Kiem tra AT handshake...");
    if (!waitForAtReady(SIM_AT_RESPONSE_TIMEOUT_MS, SIM_AT_READY_RETRY_DELAY_MS)) {
        CUS_DBGLN(" -> FAIL");
        CUS_DBGF("[SIM] -> KHONG CO TIN HIEU: khong co phan hoi tren UART trong %lu ms.\n",
                 (unsigned long)SIM_AT_RESPONSE_TIMEOUT_MS);
        dumpSimState("init_fail", true);
        return false;
    }
    CUS_DBGLN(" -> OK");

    CUS_DBG("[SIM] Dong bo UART/AT mode...");
    if (!normalizeAtMode()) {
        CUS_DBGLN(" -> FAIL");
        dumpSimState("normalize_fail", true);
        return false;
    }
    runRawAt("+CMEE=2", 1500);
    if (!simReadyRaw()) {
        CUS_DBGLN(" -> SIM chua READY.");
        dumpSimState("sim_not_ready", true);
        return false;
    }
    CUS_DBGLN(" -> OK");
    dumpSimState("after_sync", true);

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

    CUS_DBG("[SIM] Dang kich hoat packet data (");
    CUS_DBG(SIM_APN);
    CUS_DBG(")...");
    String recoveryDetail;
    if (!configurePacketSessionWithRecovery(false, &recoveryDetail)) {
        SimNetworkState fallbackState = simReadNetworkState(true);
        if (packetSessionLooksUsable(fallbackState)) {
            CUS_DBGLN(" -> Packet session da len du verdict config fail, chap nhan che do degraded.");
            CUS_DBGF("[SIM] Recovery: %s\n", recoveryDetail.c_str());
            dumpSimState("gprs_degraded_after_config_fail", true);
            gRestartCount = 0;
            checkInfo();
            return true;
        }

        if (modemHttpSessionLooksUsable()) {
            CUS_DBGLN(" -> HTTP engine cua modem van ra ngoai duoc, chap nhan che do degraded.");
            CUS_DBGF("[SIM] Recovery: %s\n", recoveryDetail.c_str());
            dumpSimState("gprs_degraded_http_ok", true);
            gRestartCount = 0;
            checkInfo();
            return true;
        }

        CUS_DBGLN(" -> LOI: GPRS Failed!");
        CUS_DBGF("[SIM] Recovery: %s\n", recoveryDetail.c_str());
        printCellDiagnostic("setup_gprs_fail");
        dumpSimState("gprs_connect_fail", true);
        return false;
    }
    CUS_DBGLN(" -> Internet OK");
    CUS_DBGF("[SIM] Recovery: %s\n", recoveryDetail.c_str());
    dumpSimState("gprs_connected", true);

    if (APP_RAW_TRUTH_PROBE_MODE) {
        if (!testInternetSocket()) {
            CUS_DBGLN("[SIM] Packet data da len nhung raw HTTP van that bai, tiep tuc o che do degraded de retry sau.");
            dumpSimState("internet_test_fail", true);
        }
    } else {
        CUS_DBGLN("[SIM] Bo qua raw TCP/CIPOPEN trong flow chinh; A7682S se dung HTTP engine de danh gia transport.");
    }

    gRestartCount = 0;
    checkInfo();
    return true;
}

bool checkNetwork() {
    SimNetworkState state = simReadNetworkState(true);
    if (packetSessionLooksUsable(state)) {
        gRestartCount = 0;
        if (state.localIp == "0.0.0.0") {
            CUS_DBGF("[SIM] Packet data dang ton tai nhung IP query chua on dinh, tiep tuc giu session. op=%s dbm=%d\n",
                     state.operatorName.c_str(),
                     state.signalDbm);
        }
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

        String recoveryDetail;
        CUS_DBG(" -> Co song -> Reconnecting packet data...");
        if (configurePacketSessionWithRecovery(true, &recoveryDetail)) {
            SimNetworkState recoveredState = simReadNetworkState(true);
            if (packetSessionLooksUsable(recoveredState)) {
                CUS_DBGLN(" -> OK!");
                CUS_DBGF("[SIM] Recovery: %s\n", recoveryDetail.c_str());
                dumpSimState("reconnect_ok", true);
                gRestartCount = 0;
                return true;
            }
            CUS_DBGLN(" -> Lenh reconnect xong nhung packet session van chua usable!");
        } else {
            CUS_DBGLN(" -> That bai!");
            CUS_DBGF("[SIM] Recovery: %s\n", recoveryDetail.c_str());
        }
        dumpSimState("reconnect_fail", true);

        if (gRestartCount == MAX_RETRY) {
            if (now - gLastRestartMs < SIM_RESTART_COOLDOWN_MS) {
                CUS_DBGLN("\n[SIM] Tam hoan restart modem (cooldown).");
                dumpSimState("restart_cooldown", true);
                return false;
            }
            CUS_DBGLN("\n[SIM] Qua nhieu lan that bai -> KHOI DONG LAI MODEM...");
            if (softRestartModem()) {
                gLastRestartMs = now;
                dumpSimState("after_restart", true);
            }
            gRestartCount = 0;
            yieldToScheduler(3000);
        }
    }

    return false;
}

void checkInfo() {
#if DEBUG_MODE
    SimNetworkState state = simReadNetworkState(true);
    CUS_DBGLN("\n=== THONG TIN SIM ===");
    if (waitForAtReady(1000, 100)) {
        CUS_DBGF("Operator: %s\n", state.operatorName.c_str());
        CUS_DBGF("Signal:   %d CSQ / %d dBm\n", querySignalCsq(), state.signalDbm);
        CUS_DBGF("IP:       %s\n", state.localIp.c_str());
#if SIM_VERBOSE_AT_QUERY_LOG
        dumpSimState("check_info", true);
#endif
    } else {
        CUS_DBGLN("Modem khong phan hoi!");
    }
    CUS_DBGLN("=====================");
#endif
}

SimNetworkState simReadNetworkState(bool forceRefreshIp) {
    SimNetworkState state{};
    state.simReady = simReadyRaw();
    state.networkRegistered = isCellRegisteredAny();
    state.packetAttached = isPacketAttached();
    state.localIp = resolveLocalIp(forceRefreshIp);
    state.operatorName = queryOperatorName();
    state.signalDbm = simSignalDbm();
    state.gprsConnected = state.packetAttached && isPdpContextActive();

    if (!isValidIpv4(state.localIp)) {
        state.localIp = "0.0.0.0";
    }

    if (!state.packetAttached) {
        state.localIp = state.packetAttached ? state.localIp : "0.0.0.0";
    }

    return state;
}

SimConnectivityReport runSimConnectivityProbe(bool forceRefreshIp,
                                              const RawSimHttpProbeResult *probeOverride) {
    SimConnectivityReport report{};
    String atProbe = runRawAt("", RAW_AT_TIMEOUT_BRIEF_MS);

    report.uartReady = atResponseIsOk(atProbe);
    if (!report.uartReady) {
        report.stage = "uart_fail";
        report.detail = atProbe;
        return report;
    }

    SimNetworkState state = simReadNetworkState(forceRefreshIp);
    report.simReady = state.simReady;
    report.networkRegistered = state.networkRegistered;
    report.packetAttached = state.packetAttached;
    report.gprsConnected = state.gprsConnected;
    report.hasUsableIp = (state.localIp != "0.0.0.0");
    report.signalDbm = state.signalDbm;
    report.signalCsq = querySignalCsq();
    report.localIp = state.localIp;
    report.operatorName = state.operatorName;
    report.pdpContext = compactAtResponse(runRawAt("+CGDCONT?", RAW_AT_TIMEOUT_MS));
    report.pdpActive = compactAtResponse(runRawAt("+CGACT?", RAW_AT_TIMEOUT_MS));
    report.dnsConfig = compactAtResponse(runRawAt("+CDNSCFG?", RAW_AT_TIMEOUT_MS));
    report.netOpen = compactAtResponse(runRawAt("+NETOPEN?", RAW_AT_TIMEOUT_MS));
    report.cipOpenCode = -1;

    if (!report.simReady) {
        report.stage = "sim_not_ready";
        report.detail = "CPIN not ready";
        return report;
    }
    if (!report.networkRegistered) {
        report.stage = "network_not_registered";
        report.detail = "CREG/CGREG/CEREG not registered";
        return report;
    }
    if (!report.packetAttached) {
        report.stage = "packet_not_attached";
        report.detail = "CGATT not attached";
        return report;
    }
    if (!report.gprsConnected) {
        report.stage = "gprs_not_connected";
        report.detail = "CGACT/CGATT indicates packet session not usable";
        return report;
    }

    RawSimHttpProbeResult rawHttp;
    if (probeOverride) {
        rawHttp = *probeOverride;
    } else {
        rawInternetProbe(rawHttp);
    }

    report.rawAtDirectSocketOk = rawHttp.socketOpenOk;
    report.rawHttpOk = rawHttp.headerOk;
    report.internetUsable = rawHttp.headerOk;
    report.cipOpenCode = rawHttp.cipOpenCode;
    report.netOpenDetail = rawHttp.netOpenResponse;
    report.rawSocketOpen = rawHttp.openResponse;
    report.rawPromptResponse = rawHttp.promptResponse;
    report.rawSendResponse = compactAtResponse(rawHttp.sendResponse);
    report.rawAvailableResponse = rawHttp.availableResponse;
    report.rawReadResponse = compactAtResponse(rawHttp.readResponse);
    report.rawHttpStage = rawHttp.stage;
    report.rawHttpDetail = rawHttp.detail;
    report.rawHttpHeader = rawHttp.header;

    if (report.rawHttpOk) {
        report.stage = report.hasUsableIp ? "raw_transport_ready" : "raw_transport_ready_ip_unknown";
        report.detail = String("raw_http=") + rawHttp.stage + "," + rawHttp.detail;
        return report;
    }

    if (!report.rawAtDirectSocketOk) {
        report.stage = "raw_socket_open_fail";
        report.detail = rawHttp.stage + " | " + rawHttp.detail;
        return report;
    }

    report.stage = report.hasUsableIp ? "raw_http_fail" : "raw_http_fail_ip_unknown";
    report.detail = rawHttp.stage + " | " + rawHttp.detail;
    return report;
}

void printSimConnectivityReport(const SimConnectivityReport &report) {
    CUS_DBGF("[SIM][PROBE] stage=%s detail=%s uart=%d sim=%d reg=%d attach=%d gprs=%d ip=%d rawat_direct=%d raw_http=%d internet=%d csq=%d dbm=%d cipopen=%d ip_addr=%s op=%s\n",
             report.stage.c_str(),
             report.detail.c_str(),
             report.uartReady ? 1 : 0,
             report.simReady ? 1 : 0,
             report.networkRegistered ? 1 : 0,
             report.packetAttached ? 1 : 0,
             report.gprsConnected ? 1 : 0,
             report.hasUsableIp ? 1 : 0,
             report.rawAtDirectSocketOk ? 1 : 0,
             report.rawHttpOk ? 1 : 0,
             report.internetUsable ? 1 : 0,
             report.signalCsq,
             report.signalDbm,
             report.cipOpenCode,
             report.localIp.c_str(),
             report.operatorName.c_str());

    if (!report.uartReady) {
        return;
    }

    if (report.rawHttpStage.length()) {
        CUS_DBGF("[SIM][PROBE] raw_http_stage=%s detail=%s\n",
                 report.rawHttpStage.c_str(),
                 report.rawHttpDetail.c_str());
    }
#if SIM_VERBOSE_PROBE_DETAIL
    CUS_DBGF("[SIM][PROBE] pdp=%s\n", report.pdpContext.c_str());
    CUS_DBGF("[SIM][PROBE] cgact=%s\n", report.pdpActive.c_str());
    CUS_DBGF("[SIM][PROBE] dns=%s\n", report.dnsConfig.c_str());
    CUS_DBGF("[SIM][PROBE] netopen=%s\n", report.netOpen.c_str());
    if (report.netOpenDetail.length()) {
        CUS_DBGF("[SIM][PROBE] netopen_detail=%s\n", report.netOpenDetail.c_str());
    }
    if (report.rawSocketOpen.length()) {
        CUS_DBGF("[SIM][PROBE] raw_socket=%s\n", report.rawSocketOpen.c_str());
    }
    if (report.rawPromptResponse.length()) {
        CUS_DBGF("[SIM][PROBE] raw_prompt=%s\n", report.rawPromptResponse.c_str());
    }
    if (report.rawSendResponse.length()) {
        CUS_DBGF("[SIM][PROBE] raw_send=%s\n", report.rawSendResponse.c_str());
    }
    if (report.rawAvailableResponse.length()) {
        CUS_DBGF("[SIM][PROBE] raw_available=%s\n", report.rawAvailableResponse.c_str());
    }
    if (report.rawReadResponse.length()) {
        CUS_DBGF("[SIM][PROBE] raw_read=%s\n", report.rawReadResponse.c_str());
    }
    if (report.rawHttpHeader.length()) {
        CUS_DBGF("[SIM][PROBE] raw_http_header=%s\n", report.rawHttpHeader.c_str());
    }
#endif
}

void printSimForensicAtSnapshot() {
    CUS_DBGLN("[SIM][FORENSIC] ---- AT SNAPSHOT ----");
    CUS_DBGF("[SIM][FORENSIC] CPIN=%s\n", compactAtResponse(runRawAt("+CPIN?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CSQ=%s\n", compactAtResponse(runRawAt("+CSQ", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CREG=%s\n", compactAtResponse(runRawAt("+CREG?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CGREG=%s\n", compactAtResponse(runRawAt("+CGREG?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CEREG=%s\n", compactAtResponse(runRawAt("+CEREG?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CGDCONT=%s\n", compactAtResponse(runRawAt("+CGDCONT?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CGACT=%s\n", compactAtResponse(runRawAt("+CGACT?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CGATT=%s\n", compactAtResponse(runRawAt("+CGATT?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CDNSCFG=%s\n", compactAtResponse(runRawAt("+CDNSCFG?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] NETOPEN=%s\n", compactAtResponse(runRawAt("+NETOPEN?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CIPRXGET=%s\n", compactAtResponse(runRawAt("+CIPRXGET?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CIPCLOSE?=%s\n", compactAtResponse(runRawAt("+CIPCLOSE?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGF("[SIM][FORENSIC] CCLK=%s\n", compactAtResponse(runRawAt("+CCLK?", RAW_AT_TIMEOUT_MS)).c_str());
    CUS_DBGLN("[SIM][FORENSIC] ---------------------");
}

bool simHasUsableIP() {
    return simReadNetworkState().localIp != "0.0.0.0";
}

int simSignalDbm() {
    int csq = querySignalCsq();
    if (csq <= 0 || csq == 99) {
        return 0;
    }
    return -113 + (2 * csq);
}

String simLocalIP() {
    return simReadNetworkState().localIp;
}

int simStatusCode() {
    SimNetworkState state = simReadNetworkState();
    if (state.gprsConnected && state.localIp != "0.0.0.0") {
        return 3;
    }
    if (state.packetAttached) {
        return 2;
    }
    if (state.networkRegistered) {
        return 1;
    }
    return 0;
}

String simReadNetworkTimeRaw() {
    return extractQuotedValue(runRawAt("+CCLK?", RAW_AT_TIMEOUT_MS));
}

bool simAcquireAtPort(uint32_t timeoutMs) {
    ensureAtPortMutex();
    if (!gAtPortMutex) {
        return false;
    }
    return xSemaphoreTakeRecursive(gAtPortMutex, pdMS_TO_TICKS(timeoutMs)) == pdTRUE;
}

void simReleaseAtPort() {
    if (gAtPortMutex) {
        xSemaphoreGiveRecursive(gAtPortMutex);
    }
}
