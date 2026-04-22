#ifndef RTDB_REST_CLIENT_H
#define RTDB_REST_CLIENT_H

#include <Arduino.h>

#include "SimHttpClient.h"

struct RtdbRestResponse {
    bool ok = false;
    bool transportOk = false;
    bool responseReceived = false;
    int statusCode = -1;
    String stage;
    String detail;
    String body;
    String header;
};

class RtdbRestClient {
public:
    RtdbRestClient(const char *databaseUrl, const char *legacyToken);

    bool configured() const;
    bool probe(RtdbRestResponse &response);
    bool putRawJson(const String &path, const String &jsonBody, RtdbRestResponse &response, bool silent = true);
    bool patchRawJson(const String &path, const String &jsonBody, RtdbRestResponse &response, bool silent = true);
    bool deletePath(const String &path, RtdbRestResponse &response);

private:
    String _databaseUrl;
    String _legacyToken;
    SimHttpClient _http;

    String buildUrl(const String &path, const String &extraQuery = "") const;
    bool performJsonWrite(SimHttpMethod method,
                          const String &path,
                          const String &jsonBody,
                          RtdbRestResponse &response,
                          bool silent);
};

RtdbRestClient &rtdbRestClient();

#endif
