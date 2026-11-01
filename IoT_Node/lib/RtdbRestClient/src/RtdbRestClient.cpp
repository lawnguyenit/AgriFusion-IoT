#include "RtdbRestClient.h"

#include "Config.h"

namespace {
String normalizePath(const String &path) {
    if (!path.length() || path == "/") {
        return "";
    }
    return path.startsWith("/") ? path : String("/") + path;
}

String classifyHttpFailureStage(const SimHttpResponse &http) {
    if (!http.transportOk) {
        return "rtdb_transport_fail";
    }
    if (http.statusCode == 401 || http.statusCode == 403) {
        return "rtdb_auth_fail";
    }
    if (http.statusCode == 404) {
        return "rtdb_endpoint_fail";
    }
    return "rtdb_http_fail";
}
}  // namespace

RtdbRestClient::RtdbRestClient(const char *databaseUrl, const char *legacyToken)
    : _databaseUrl(databaseUrl ? databaseUrl : ""),
      _legacyToken(legacyToken ? legacyToken : "") {}

bool RtdbRestClient::configured() const {
    return _databaseUrl.startsWith("http") && _legacyToken.length() > 0;
}

String RtdbRestClient::buildUrl(const String &path, const String &extraQuery) const {
    String normalizedPath = normalizePath(path);
    String url = _databaseUrl + normalizedPath;
    if (!url.endsWith(".json")) {
        url += ".json";
    }

    String query = "auth=" + _legacyToken;
    if (extraQuery.length()) {
        query += "&";
        query += extraQuery;
    }

    url += "?";
    url += query;
    return url;
}

bool RtdbRestClient::probe(RtdbRestResponse &response) {
    response = RtdbRestResponse{};
    if (!configured()) {
        response.stage = "rtdb_not_configured";
        response.detail = "missing_database_url_or_legacy_token";
        return false;
    }

    SimHttpRequest req;
    req.method = SimHttpMethod::Get;
    req.url = buildUrl(APP_RTDB_PATH_NODE_INFO);
    req.readHeader = true;
    req.readBody = true;

    SimHttpResponse http;
    bool ok = _http.perform(req, http);
    response.transportOk = http.transportOk;
    response.responseReceived = http.responseReceived;
    response.ok = ok;
    response.statusCode = http.statusCode;
    response.stage = ok ? "rtdb_probe_ok" : classifyHttpFailureStage(http);
    response.detail = http.stage + " | " + http.detail;
    response.body = http.body;
    response.header = http.header;
    return ok;
}

bool RtdbRestClient::performJsonWrite(SimHttpMethod method,
                                      const String &path,
                                      const String &jsonBody,
                                      RtdbRestResponse &response,
                                      bool silent) {
    response = RtdbRestResponse{};
    if (!configured()) {
        response.stage = "rtdb_not_configured";
        response.detail = "missing_database_url_or_legacy_token";
        return false;
    }

    SimHttpRequest req;
    req.method = method;
    req.url = buildUrl(path, silent ? "print=silent" : "");
    req.body = jsonBody;
    req.contentType = "application/json";
    req.readHeader = true;
    req.readBody = !silent;

    SimHttpResponse http;
    bool ok = _http.perform(req, http);
    response.transportOk = http.transportOk;
    response.responseReceived = http.responseReceived;
    response.ok = ok;
    response.statusCode = http.statusCode;
    response.stage = ok ? "rtdb_write_ok" : classifyHttpFailureStage(http);
    response.detail = http.stage + " | " + http.detail;
    response.body = http.body;
    response.header = http.header;
    return ok;
}

bool RtdbRestClient::putRawJson(const String &path,
                                const String &jsonBody,
                                RtdbRestResponse &response,
                                bool silent) {
    return performJsonWrite(SimHttpMethod::Put, path, jsonBody, response, silent);
}

bool RtdbRestClient::patchRawJson(const String &path,
                                  const String &jsonBody,
                                  RtdbRestResponse &response,
                                  bool silent) {
    return performJsonWrite(SimHttpMethod::Patch, path, jsonBody, response, silent);
}

bool RtdbRestClient::deletePath(const String &path, RtdbRestResponse &response) {
    response = RtdbRestResponse{};
    if (!configured()) {
        response.stage = "rtdb_not_configured";
        response.detail = "missing_database_url_or_legacy_token";
        return false;
    }

    SimHttpRequest req;
    req.method = SimHttpMethod::Delete;
    req.url = buildUrl(path, "print=silent");
    req.readHeader = true;
    req.readBody = false;

    SimHttpResponse http;
    bool ok = _http.perform(req, http);
    response.transportOk = http.transportOk;
    response.responseReceived = http.responseReceived;
    response.ok = ok;
    response.statusCode = http.statusCode;
    response.stage = ok ? "rtdb_delete_ok" : classifyHttpFailureStage(http);
    response.detail = http.stage + " | " + http.detail;
    response.header = http.header;
    return ok;
}

RtdbRestClient &rtdbRestClient() {
    static RtdbRestClient client(APP_FIREBASE_DATABASE_URL, APP_FIREBASE_LEGACY_TOKEN);
    return client;
}
