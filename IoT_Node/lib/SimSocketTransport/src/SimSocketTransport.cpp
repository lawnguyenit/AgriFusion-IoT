#include "SimSocketTransport.h"

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "Config.h"
#include "SimA7680C.h"

namespace {
constexpr uint32_t RAW_AT_TIMEOUT_MS = 1500;

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

int parseCipOpenCode(const String &response) {
    int prefix = response.indexOf("+CIPOPEN:");
    if (prefix < 0) {
        return -1;
    }

    int firstComma = response.indexOf(',', prefix);
    if (firstComma < 0) {
        return -1;
    }

    String value;
    for (int i = firstComma + 1; i < response.length(); ++i) {
        char c = response[i];
        if (c >= '0' && c <= '9') {
            value += c;
        } else if (value.length()) {
            break;
        }
    }

    return value.length() ? value.toInt() : -1;
}

String cipOpenCodeText(int code) {
    if (code < 0) {
        return "cipopen_no_code";
    }
    if (code == 0) {
        return "cipopen_ok";
    }
    return String("cipopen_code_") + String(code);
}

String compactResponse(const String &response) {
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

String runRawAtWaitPatterns(const String &cmd,
                            uint32_t timeoutMs,
                            const char *const *patterns,
                            size_t patternCount) {
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

        if (responseHasAny(response, patterns, patternCount)) {
            break;
        }
        yieldToScheduler();
    }

    response = stripEchoedCommand(response, cmd);
    response.trim();
    return response.length() ? response : String("<no response>");
}

String collectLateSocketUrc(uint32_t timeoutMs) {
    String response;
    uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        while (SerialAT.available()) {
            response += static_cast<char>(SerialAT.read());
        }
        if (responseContains(response, "+CIPOPEN:") ||
            responseContains(response, "ERROR") ||
            responseContains(response, "CLOSE OK")) {
            break;
        }
        yieldToScheduler();
    }
    response.trim();
    return response;
}

String runRawAt(const String &cmd, uint32_t timeoutMs = RAW_AT_TIMEOUT_MS) {
    static const char *const patterns[] = {"OK", "ERROR", ">"};
    return runRawAtWaitPatterns(cmd, timeoutMs, patterns, sizeof(patterns) / sizeof(patterns[0]));
}

bool waitForPrompt(const String &cmd, uint32_t timeoutMs, String &response) {
    static const char *const patterns[] = {">", "ERROR"};
    response = runRawAtWaitPatterns(cmd, timeoutMs, patterns, sizeof(patterns) / sizeof(patterns[0]));
    return responseContains(response, ">");
}

bool sendPayload(const String &payload, uint32_t timeoutMs, String &response) {
    drainSerialAT();
    SerialAT.print(payload);
    SerialAT.flush();

    static const char *const patterns[] = {"OK", "ERROR", "SEND FAIL", "CLOSE OK", "+CIPSEND:"};
    uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        while (SerialAT.available()) {
            response += static_cast<char>(SerialAT.read());
        }
        if (responseHasAny(response, patterns, sizeof(patterns) / sizeof(patterns[0]))) {
            break;
        }
        yieldToScheduler();
    }

    response.trim();
    return !responseContains(response, "ERROR") && !responseContains(response, "FAIL");
}

bool ensureNetOpen(String &response) {
    String lastResponse;

    for (uint32_t attempt = 0; attempt < SIM_TEST_NETOPEN_RETRY_COUNT; ++attempt) {
        String queryResp = runRawAt("+NETOPEN?", 3000);
        if (responseContains(queryResp, "+NETOPEN: 1")) {
            response = compactResponse(queryResp);
            return true;
        }

        runRawAt("+NETCLOSE", 5000);
        yieldToScheduler(SIM_TEST_NETOPEN_RETRY_DELAY_MS);

        String openResp = runRawAt("+NETOPEN", 5000);
        queryResp = runRawAt("+NETOPEN?", 3000);
        lastResponse = compactResponse(openResp) + " || " + compactResponse(queryResp);
        if (responseContains(queryResp, "+NETOPEN: 1")) {
            response = lastResponse;
            return true;
        }

        yieldToScheduler(SIM_TEST_NETOPEN_RETRY_DELAY_MS);
    }

    response = lastResponse.length() ? lastResponse : compactResponse(runRawAt("+NETOPEN?", 3000));
    return false;
}

int parseAvailableFromCiprxget4(const String &response) {
    int prefix = response.indexOf("+CIPRXGET:");
    if (prefix < 0) {
        return -1;
    }

    int firstComma = response.indexOf(',', prefix);
    if (firstComma < 0) {
        return -1;
    }
    int secondComma = response.indexOf(',', firstComma + 1);
    if (secondComma < 0) {
        return -1;
    }

    String value;
    for (int i = secondComma + 1; i < response.length(); ++i) {
        char c = response[i];
        if (c >= '0' && c <= '9') {
            value += c;
        } else if (value.length()) {
            break;
        }
    }
    return value.length() ? value.toInt() : -1;
}

String extractPayloadFromReadResponse(const String &response) {
    int headerPos = response.indexOf("+CIPRXGET:");
    if (headerPos < 0) {
        return "";
    }

    int lineEnd = response.indexOf('\n', headerPos);
    if (lineEnd < 0 || lineEnd + 1 >= response.length()) {
        return "";
    }

    String payload = response.substring(lineEnd + 1);
    int okPos = payload.lastIndexOf("\r\nOK");
    if (okPos >= 0) {
        payload = payload.substring(0, okPos);
    }
    payload.trim();
    return payload;
}

void appendTrace(String &target, const String &value) {
    if (!value.length()) {
        return;
    }
    if (target.length()) {
        target += " || ";
    }
    target += compactResponse(value);
}
}  // namespace

bool openRawSimTcpSocket(const char *host,
                         uint16_t port,
                         uint32_t timeoutMs,
                         RawSimSocketOpenResult &result,
                         uint8_t socketId) {
    result = RawSimSocketOpenResult{};

    if (!host || !strlen(host)) {
        result.detail = "empty_host";
        return false;
    }

    closeRawSimSocket(socketId, result.closeResponse);

    String netResp;
    if (!ensureNetOpen(netResp)) {
        result.detail = "netopen_fail";
        result.netOpenResponse = netResp;
        result.openResponse = netResp;
        closeRawSimSocket(socketId, result.closeResponse);
        return false;
    }

    result.netOpenOk = true;
    result.netOpenResponse = netResp;

    String cmd = String("+CIPOPEN=") + String(socketId) + ",\"TCP\",\"" + host + "\"," + String(port);
    static const char *const patterns[] = {
        "+CIPOPEN:",
        "ERROR",
        "CLOSE OK"
    };
    String openResp = runRawAtWaitPatterns(cmd, timeoutMs, patterns, sizeof(patterns) / sizeof(patterns[0]));
    if (!responseContains(openResp, "+CIPOPEN:") &&
        (responseContains(openResp, "OK") || openResp == "<no response>")) {
        String lateResp = collectLateSocketUrc(1500);
        if (lateResp.length()) {
            if (openResp == "<no response>") {
                openResp = lateResp;
            } else {
                openResp += "\n";
                openResp += lateResp;
            }
        }
    }
    result.cipOpenCode = parseCipOpenCode(openResp);

    if (result.cipOpenCode == 0) {
        result.socketOpenOk = true;
        result.detail = cipOpenCodeText(result.cipOpenCode);
        result.openResponse = compactResponse(openResp);
        return true;
    }

    result.openResponse = compactResponse(netResp) + " || " + compactResponse(openResp);
    if (result.cipOpenCode > 0) {
        result.detail = cipOpenCodeText(result.cipOpenCode);
    } else if (responseContains(openResp, "ERROR")) {
        result.detail = "cipopen_error";
    } else if (responseContains(openResp, "CLOSE OK")) {
        result.detail = "cipopen_close_ok";
    } else if (openResp == "<no response>") {
        result.detail = "cipopen_timeout";
    } else {
        result.detail = "cipopen_no_urc";
    }

    closeRawSimSocket(socketId, result.closeResponse);
    return false;
}

bool sendRawSimSocketLenMode(uint8_t socketId,
                             const String &payload,
                             uint32_t timeoutMs,
                             RawSimSocketSendResult &result) {
    result = RawSimSocketSendResult{};
    result.mode = "len";

    String promptResp;
    if (!waitForPrompt(String("+CIPSEND=") + String(socketId) + "," + String(payload.length()), timeoutMs, promptResp)) {
        result.promptResponse = compactResponse(promptResp);
        result.detail = "prompt_fail";
        return false;
    }

    result.promptOk = true;
    result.promptResponse = compactResponse(promptResp);
    result.sendOk = sendPayload(payload, timeoutMs, result.sendResponse);
    result.sendResponse = compactResponse(result.sendResponse);
    result.detail = result.sendOk ? "send_ok" : "send_fail";
    return result.sendOk;
}

bool sendRawSimSocketCtrlZMode(uint8_t socketId,
                               const String &payload,
                               uint32_t timeoutMs,
                               RawSimSocketSendResult &result) {
    result = RawSimSocketSendResult{};
    result.mode = "ctrlz";

    String promptResp;
    if (!waitForPrompt(String("+CIPSEND=") + String(socketId), timeoutMs, promptResp)) {
        result.promptResponse = compactResponse(promptResp);
        result.detail = "prompt_fail";
        return false;
    }

    result.promptOk = true;
    result.promptResponse = compactResponse(promptResp);

    drainSerialAT();
    SerialAT.print(payload);
    SerialAT.write(0x1A);
    SerialAT.flush();

    String sendResp;
    static const char *const patterns[] = {"OK", "ERROR", "SEND FAIL", "CLOSE OK", "+CIPSEND:", "+CIPERROR:"};
    uint32_t start = millis();
    while (millis() - start < timeoutMs) {
        while (SerialAT.available()) {
            sendResp += static_cast<char>(SerialAT.read());
        }
        if (responseHasAny(sendResp, patterns, sizeof(patterns) / sizeof(patterns[0]))) {
            break;
        }
        yieldToScheduler();
    }

    result.sendResponse = compactResponse(sendResp);
    result.sendOk = !responseContains(sendResp, "ERROR") &&
                    !responseContains(sendResp, "FAIL") &&
                    !responseContains(sendResp, "+CIPERROR:");
    result.detail = result.sendOk ? "send_ok" : "send_fail";
    return result.sendOk;
}

bool enableRawSimManualReceive(String &response) {
    response = compactResponse(runRawAt("+CIPRXGET=1", 3000));
    return responseContains(response, "OK");
}

bool pollRawSimSocketAvailable(uint8_t socketId,
                               uint32_t timeoutMs,
                               RawSimSocketReadResult &result) {
    result = RawSimSocketReadResult{};
    String availableResp = runRawAt(String("+CIPRXGET=4,") + String(socketId), timeoutMs);
    result.availableResponse = compactResponse(availableResp);

    int available = parseAvailableFromCiprxget4(availableResp);
    result.availableBytes = available > 0 ? static_cast<size_t>(available) : 0;
    result.ok = available >= 0;
    result.detail = available > 0 ? "bytes_available" : (available == 0 ? "no_bytes" : "parse_fail");
    return result.ok;
}

bool readRawSimSocket(uint8_t socketId,
                      size_t maxBytes,
                      uint32_t timeoutMs,
                      RawSimSocketReadResult &result) {
    result = RawSimSocketReadResult{};
    if (!maxBytes) {
        result.detail = "max_bytes_zero";
        return false;
    }

    String readResp = runRawAt(String("+CIPRXGET=2,") + String(socketId) + "," + String((unsigned long)maxBytes), timeoutMs);
    result.readResponse = compactResponse(readResp);
    result.payload = extractPayloadFromReadResponse(readResp);
    result.availableBytes = result.payload.length();
    result.ok = result.payload.length() > 0;
    result.detail = result.ok ? "read_ok" : "read_empty";
    return result.ok;
}

bool closeRawSimSocket(uint8_t socketId, String &response) {
    drainSerialAT();
    response = compactResponse(runRawAt(String("+CIPCLOSE=") + String(socketId), 3000));
    return responseContains(response, "OK") || responseContains(response, "ERROR");
}

RawSimSocketTransactionResult runRawSimSocketTransaction(const RawSimSocketTransactionConfig &config) {
    RawSimSocketTransactionResult result;
    if (!config.host || !strlen(config.host)) {
        result.stage = "raw_tx_empty_host";
        result.detail = "empty_host";
        return result;
    }
    if (!config.payload.length()) {
        result.stage = "raw_tx_empty_payload";
        result.detail = "empty_payload";
        return result;
    }

    const uint32_t attempts = config.retries > 0 ? config.retries : 1;
    const size_t readChunkBytes = config.readChunkBytes > 0 ? config.readChunkBytes : 512;
    const size_t maxPayloadBytes = config.maxPayloadBytes > 0 ? config.maxPayloadBytes : readChunkBytes;

    for (uint32_t attempt = 0; attempt < attempts; ++attempt) {
        closeRawSimSocket(config.socketId, result.closeResponse);

        RawSimSocketOpenResult openResult;
        result.socketOpenOk = openRawSimTcpSocket(config.host,
                                                  config.port,
                                                  config.timeoutMs,
                                                  openResult,
                                                  config.socketId);
        result.netOpenOk = openResult.netOpenOk;
        result.cipOpenCode = openResult.cipOpenCode;
        result.netOpenResponse = openResult.netOpenResponse;
        result.openResponse = openResult.openResponse;
        result.closeResponse = openResult.closeResponse;
        result.detail = openResult.detail;
        if (!result.socketOpenOk) {
            result.stage = "raw_tx_open_fail";
            if (attempt + 1 < attempts) {
                yieldToScheduler(SIM_TEST_NETOPEN_RETRY_DELAY_MS);
                continue;
            }
            closeRawSimSocket(config.socketId, result.closeResponse);
            return result;
        }

        RawSimSocketSendResult sendResult;
        bool sendOk = config.useLenMode
                          ? sendRawSimSocketLenMode(config.socketId, config.payload, config.timeoutMs, sendResult)
                          : sendRawSimSocketCtrlZMode(config.socketId, config.payload, config.timeoutMs, sendResult);
        result.promptResponse = sendResult.promptResponse;
        result.sendResponse = sendResult.sendResponse;
        result.sendOk = sendOk;
        if (!sendOk) {
            result.stage = "raw_tx_send_fail";
            result.detail = sendResult.detail;
            if (attempt + 1 < attempts) {
                closeRawSimSocket(config.socketId, result.closeResponse);
                yieldToScheduler(SIM_TEST_NETOPEN_RETRY_DELAY_MS);
                continue;
            }
            closeRawSimSocket(config.socketId, result.closeResponse);
            return result;
        }

        if (config.enableManualRx) {
            String rxModeResponse;
            result.rxModeOk = enableRawSimManualReceive(rxModeResponse);
            result.availableResponse = compactResponse(rxModeResponse);
            if (!result.rxModeOk) {
                result.stage = "raw_tx_rx_mode_fail";
                result.detail = result.availableResponse;
                if (attempt + 1 < attempts) {
                    closeRawSimSocket(config.socketId, result.closeResponse);
                    yieldToScheduler(SIM_TEST_NETOPEN_RETRY_DELAY_MS);
                    continue;
                }
                closeRawSimSocket(config.socketId, result.closeResponse);
                return result;
            }
        } else {
            result.rxModeOk = true;
        }

        bool sawPayload = false;
        uint32_t start = millis();
        uint32_t lastPayloadMs = start;
        while (millis() - start < config.timeoutMs) {
            RawSimSocketReadResult availableResult;
            pollRawSimSocketAvailable(config.socketId, 3000, availableResult);
            result.availableBytes = availableResult.availableBytes;
            result.availableResponse = availableResult.availableResponse;

            if (responseContains(result.availableResponse, "operation not supported") && config.enableManualRx) {
                String rxModeResponse;
                bool rxReenabled = enableRawSimManualReceive(rxModeResponse);
                result.rxModeOk = result.rxModeOk || rxReenabled;
                appendTrace(result.availableResponse, String("retry_rx_mode=") + compactResponse(rxModeResponse));
                yieldToScheduler(100);
                continue;
            }

            if (availableResult.availableBytes > 0) {
                sawPayload = true;
                lastPayloadMs = millis();

                size_t remainingBudget = maxPayloadBytes - result.payload.length();
                if (remainingBudget == 0) {
                    result.payloadOk = result.payload.length() > 0;
                    result.payloadBytes = result.payload.length();
                    result.stage = "raw_tx_payload_limit";
                    result.detail = "payload_limit_reached";
                    closeRawSimSocket(config.socketId, result.closeResponse);
                    return result;
                }

                size_t readSize = availableResult.availableBytes;
                if (readSize > readChunkBytes) {
                    readSize = readChunkBytes;
                }
                if (readSize > remainingBudget) {
                    readSize = remainingBudget;
                }

                RawSimSocketReadResult readResult;
                readRawSimSocket(config.socketId, readSize, 4000, readResult);
                result.readResponse = readResult.readResponse;
                if (readResult.ok) {
                    result.payload += readResult.payload;
                    result.payloadBytes = result.payload.length();
                    result.payloadOk = result.payload.length() > 0;
                } else {
                    result.detail = readResult.detail;
                }
                continue;
            }

            if (sawPayload && millis() - lastPayloadMs >= config.idleReadWindowMs) {
                break;
            }
            yieldToScheduler(100);
        }

        closeRawSimSocket(config.socketId, result.closeResponse);
        result.payloadBytes = result.payload.length();
        result.payloadOk = result.payload.length() > 0;
        if (result.payloadOk) {
            result.stage = "raw_tx_ok";
            result.detail = String("payload_bytes=") + String((unsigned long)result.payload.length());
            return result;
        }

        result.stage = "raw_tx_read_timeout";
        result.detail = sawPayload ? "payload_read_failed" : "no_payload_after_send";
        if (attempt + 1 < attempts) {
            yieldToScheduler(SIM_TEST_NETOPEN_RETRY_DELAY_MS);
            continue;
        }
    }

    return result;
}

RawSimHttpProbeResult runRawSimHttpProbe(const char *host,
                                         uint16_t port,
                                         const char *path,
                                         const char *hostHeader,
                                         uint32_t timeoutMs) {
    RawSimHttpProbeResult result;
    if (!host || !strlen(host)) {
        result.stage = "raw_http_empty_host";
        result.detail = "empty_host";
        return result;
    }

    const char *effectivePath = (path && strlen(path)) ? path : "/";
    const char *effectiveHostHeader = (hostHeader && strlen(hostHeader)) ? hostHeader : host;

    RawSimSocketTransactionConfig config;
    config.host = host;
    config.port = port;
    config.payload = String("GET ") + effectivePath +
                     " HTTP/1.0\r\nHost: " + effectiveHostHeader +
                     "\r\nConnection: close\r\n\r\n";
    config.socketId = 0;
    config.timeoutMs = timeoutMs;
    config.retries = SIM_TEST_RAW_HTTP_RETRY_COUNT;
    config.readChunkBytes = 512;
    config.maxPayloadBytes = 1024;
    config.idleReadWindowMs = 800;
    config.useLenMode = true;
    config.enableManualRx = true;

    RawSimSocketTransactionResult tx = runRawSimSocketTransaction(config);
    result.netOpenOk = tx.netOpenOk;
    result.socketOpenOk = tx.socketOpenOk;
    result.sendOk = tx.sendOk;
    result.readOk = tx.payloadOk;
    result.cipOpenCode = tx.cipOpenCode;
    result.availableBytes = tx.availableBytes;
    result.detail = tx.detail;
    result.netOpenResponse = tx.netOpenResponse;
    result.openResponse = tx.openResponse;
    result.promptResponse = tx.promptResponse;
    result.sendResponse = tx.sendResponse;
    result.availableResponse = tx.availableResponse;
    result.readResponse = tx.readResponse;
    result.closeResponse = tx.closeResponse;
    result.header = tx.payload;
    result.headerOk = responseContains(result.header, "HTTP/1.");

    if (tx.stage == "raw_tx_open_fail") {
        result.stage = "raw_http_open_fail";
    } else if (tx.stage == "raw_tx_send_fail") {
        result.stage = "raw_http_send_prompt_fail";
    } else if (tx.stage == "raw_tx_rx_mode_fail") {
        result.stage = "raw_http_rx_mode_fail";
    } else if (tx.stage == "raw_tx_read_timeout") {
        result.stage = "raw_http_read_timeout";
    } else if (tx.payloadOk && result.headerOk) {
        result.stage = "raw_http_ok";
        result.detail = "http_header_ok";
    } else if (tx.payloadOk) {
        result.stage = "raw_http_payload_no_header";
        result.detail = compactResponse(tx.payload);
    } else {
        result.stage = tx.stage.length() ? tx.stage : "raw_http_unknown_fail";
    }

    return result;
}
