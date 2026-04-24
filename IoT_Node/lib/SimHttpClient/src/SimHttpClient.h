#ifndef SIM_HTTP_CLIENT_H
#define SIM_HTTP_CLIENT_H

#include <Arduino.h>

enum class SimHttpMethod : uint8_t {
    Get = 0,
    Post = 1,
    Head = 2,
    Delete = 3,
    Put = 4,
    Patch = 5,
};

struct SimHttpRequest {
    SimHttpMethod method = SimHttpMethod::Get;
    String url;
    String body;
    String contentType = "application/json";
    uint32_t connectTimeoutSec = 30;
    uint32_t recvTimeoutSec = 30;
    uint32_t actionTimeoutMs = 120000;
    size_t readChunkBytes = 512;
    bool readHeader = false;
    bool readBody = true;
};

struct SimHttpResponse {
    bool ok = false;
    bool transportOk = false;
    bool responseReceived = false;
    bool httpOk = false;
    bool actionAccepted = false;
    int method = -1;
    int statusCode = -1;
    int dataLen = 0;
    String stage;
    String detail;
    String initResponse;
    String urlResponse;
    String contentResponse;
    String dataPromptResponse;
    String dataUploadResponse;
    String actionResponse;
    String headerResponse;
    String bodyResponse;
    String termResponse;
    String header;
    String body;
};

class SimHttpClient {
public:
    bool perform(const SimHttpRequest &request, SimHttpResponse &response);
};

#endif
