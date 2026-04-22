#include "SimHttpClient.h"

#include "Config.h"
#include "SimA7680C.h"

namespace {
constexpr uint32_t HTTP_AT_TIMEOUT_MS = 4000;

void yieldToScheduler(uint32_t ms = 1) {
    delay(ms);
}

void drainSerialAT() {
    while (SerialAT.available()) {
        SerialAT.read();
    }
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

String compactResponse(const String &response) {
    String out = response;
    out.replace("\r", " ");
    out.replace("\n", " | ");
    out.trim();
    return out.length() ? out : String("empty");
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

String runHttpAtWaitPatterns(const String &cmd,
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

String runHttpAt(const String &cmd, uint32_t timeoutMs = HTTP_AT_TIMEOUT_MS) {
    static const char *const patterns[] = {"OK", "ERROR", "DOWNLOAD"};
    return runHttpAtWaitPatterns(cmd, timeoutMs, patterns, sizeof(patterns) / sizeof(patterns[0]));
}

bool uploadHttpData(const String &body, uint32_t timeoutMs, String &response) {
    drainSerialAT();
    SerialAT.print(body);
    SerialAT.flush();

    static const char *const patterns[] = {"OK", "ERROR"};
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
    return responseContains(response, "OK") && !responseContains(response, "ERROR");
}

bool parseHttpAction(const String &response, int &method, int &statusCode, int &dataLen) {
    int prefix = response.indexOf("+HTTPACTION:");
    if (prefix < 0) {
        return false;
    }

    String tail = response.substring(prefix + 12);
    tail.trim();
    int c1 = tail.indexOf(',');
    if (c1 < 0) {
        return false;
    }
    int c2 = tail.indexOf(',', c1 + 1);
    if (c2 < 0) {
        return false;
    }

    method = tail.substring(0, c1).toInt();
    statusCode = tail.substring(c1 + 1, c2).toInt();

    String rest = tail.substring(c2 + 1);
    int slash = rest.indexOf('/');
    if (slash >= 0) {
        rest = rest.substring(0, slash);
    }
    rest.trim();
    dataLen = rest.toInt();
    return true;
}

String readHttpBodyChunk(size_t offset, size_t size) {
    String cmd = String("+HTTPREAD=") + String((unsigned long)offset) + "," + String((unsigned long)size);
    return runHttpAt(cmd, 20000);
}

String extractHttpReadPayload(const String &response) {
    int headerPos = response.indexOf("+HTTPREAD:");
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
}  // namespace

bool SimHttpClient::perform(const SimHttpRequest &request, SimHttpResponse &response) {
    response = SimHttpResponse{};
    if (!request.url.length()) {
        response.stage = "http_empty_url";
        response.detail = "empty_url";
        return false;
    }

    runHttpAt("+HTTPTERM", 5000);
    response.initResponse = compactResponse(runHttpAt("+HTTPINIT", 120000));
    if (!responseContains(response.initResponse, "OK")) {
        response.stage = "http_init_fail";
        response.detail = response.initResponse;
        return false;
    }

    runHttpAt("+HTTPPARA=\"CID\",1", 5000);
    runHttpAt(String("+HTTPPARA=\"CONNECTTO\",") + String(request.connectTimeoutSec), 5000);
    runHttpAt(String("+HTTPPARA=\"RECVTO\",") + String(request.recvTimeoutSec), 5000);

    response.urlResponse = compactResponse(runHttpAt(String("+HTTPPARA=\"URL\",\"") + request.url + "\"", 10000));
    if (!responseContains(response.urlResponse, "OK")) {
        response.stage = "http_url_fail";
        response.detail = response.urlResponse;
        response.termResponse = compactResponse(runHttpAt("+HTTPTERM", 5000));
        return false;
    }

    if (request.body.length()) {
        response.contentResponse = compactResponse(runHttpAt(String("+HTTPPARA=\"CONTENT\",\"") + request.contentType + "\"", 5000));
        String prompt = runHttpAtWaitPatterns(String("+HTTPDATA=") + String((unsigned long)request.body.length()) + ",120",
                                              10000,
                                              (const char *const[]){"DOWNLOAD", "ERROR"},
                                              2);
        response.dataPromptResponse = compactResponse(prompt);
        if (!responseContains(prompt, "DOWNLOAD")) {
            response.stage = "http_data_prompt_fail";
            response.detail = response.dataPromptResponse;
            response.termResponse = compactResponse(runHttpAt("+HTTPTERM", 5000));
            return false;
        }

        String uploadResponse;
        bool uploaded = uploadHttpData(request.body, 20000, uploadResponse);
        response.dataUploadResponse = compactResponse(uploadResponse);
        if (!uploaded) {
            response.stage = "http_data_upload_fail";
            response.detail = response.dataUploadResponse;
            response.termResponse = compactResponse(runHttpAt("+HTTPTERM", 5000));
            return false;
        }
    }

    String action = runHttpAtWaitPatterns(String("+HTTPACTION=") + String((int)request.method),
                                          request.actionTimeoutMs,
                                          (const char *const[]) {"+HTTPACTION:", "ERROR"},
                                          2);
    response.actionResponse = compactResponse(action);
    response.actionAccepted = parseHttpAction(action, response.method, response.statusCode, response.dataLen);
    if (!response.actionAccepted) {
        response.stage = "http_action_fail";
        response.detail = response.actionResponse;
        response.termResponse = compactResponse(runHttpAt("+HTTPTERM", 5000));
        return false;
    }

    if (request.readHeader) {
        String headerResponse = runHttpAt("+HTTPHEAD", 20000);
        response.headerResponse = compactResponse(headerResponse);
        int headerPos = headerResponse.indexOf("+HTTPHEAD:");
        if (headerPos >= 0) {
            int lineEnd = headerResponse.indexOf('\n', headerPos);
            if (lineEnd >= 0 && lineEnd + 1 < headerResponse.length()) {
                String header = headerResponse.substring(lineEnd + 1);
                int okPos = header.lastIndexOf("\r\nOK");
                if (okPos >= 0) {
                    header = header.substring(0, okPos);
                }
                header.trim();
                response.header = header;
            }
        }
    }

    if (request.readBody && response.dataLen > 0) {
        size_t offset = 0;
        size_t chunk = request.readChunkBytes > 0 ? request.readChunkBytes : 512;
        while (offset < (size_t)response.dataLen) {
            size_t toRead = ((size_t)response.dataLen - offset) > chunk ? chunk : ((size_t)response.dataLen - offset);
            String rawChunk = readHttpBodyChunk(offset, toRead);
            response.bodyResponse += compactResponse(rawChunk);
            String payload = extractHttpReadPayload(rawChunk);
            response.body += payload;
            if (!payload.length()) {
                break;
            }
            offset += payload.length();
            if (payload.length() < toRead) {
                break;
            }
        }
    }

    response.termResponse = compactResponse(runHttpAt("+HTTPTERM", 5000));
    response.ok = response.statusCode >= 200 && response.statusCode < 300;
    response.stage = response.ok ? "http_ok" : "http_status_fail";
    if (!response.ok) {
        response.detail = String("status=") + String(response.statusCode) + " len=" + String(response.dataLen);
    } else {
        response.detail = String("status=") + String(response.statusCode) + " len=" + String(response.dataLen);
    }
    return response.ok;
}
