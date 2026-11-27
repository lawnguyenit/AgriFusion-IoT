#include "OtaManager.h"

#include <HTTPClient.h>
#include <Update.h>
#include <WiFiClientSecure.h>
#include <esp_ota_ops.h>

namespace {
String joinPath(const char *basePath, const char *leaf) {
    String path(basePath);
    if (!path.endsWith("/")) {
        path += "/";
    }
    path += leaf;
    return path;
}

bool isMissingPathError(const String &errorText) {
    String lowered = errorText;
    lowered.toLowerCase();
    return lowered.indexOf("path not exist") >= 0 || lowered.indexOf("not found") >= 0;
}
}  // namespace

bool OtaManager::fetchCommand(FirebaseData &fbdo, const char *basePath, OtaCommand &cmd, String &err) {
    cmd = OtaCommand{};
    err = "";

    if (!Firebase.getBool(fbdo, joinPath(basePath, "enabled"))) {
        err = fbdo.errorReason();
        if (isMissingPathError(err)) {
            cmd.enabled = false;
            err = "";
            return true;
        }
        return false;
    }
    cmd.enabled = fbdo.to<bool>();

    if (!cmd.enabled) {
        return true;
    }

    if (!Firebase.getString(fbdo, joinPath(basePath, "request_id"))) {
        err = fbdo.errorReason();
        return false;
    }
    cmd.requestId = fbdo.stringData();

    if (!Firebase.getString(fbdo, joinPath(basePath, "version"))) {
        err = fbdo.errorReason();
        return false;
    }
    cmd.version = fbdo.stringData();

    if (!Firebase.getString(fbdo, joinPath(basePath, "url"))) {
        err = fbdo.errorReason();
        return false;
    }
    cmd.url = fbdo.stringData();

    // Optional values
    if (Firebase.getString(fbdo, joinPath(basePath, "md5"))) {
        cmd.md5 = fbdo.stringData();
    }
    if (Firebase.getBool(fbdo, joinPath(basePath, "force"))) {
        cmd.force = fbdo.to<bool>();
    }

    if (cmd.requestId.isEmpty() || cmd.url.isEmpty()) {
        err = "missing request_id/url";
        return false;
    }

    return true;
}

bool OtaManager::disableCommand(FirebaseData &fbdo, const char *basePath) {
    return Firebase.setBool(fbdo, joinPath(basePath, "enabled"), false);
}

bool OtaManager::performHttpOta(const OtaCommand &cmd, String &targetPartitionLabel, String &errorDetail) {
    errorDetail = "";
    targetPartitionLabel = "";

    if (cmd.url.isEmpty()) {
        errorDetail = "empty ota url";
        return false;
    }

    const esp_partition_t *targetPartition = esp_ota_get_next_update_partition(NULL);
    if (targetPartition && targetPartition->label) {
        targetPartitionLabel = targetPartition->label;
    }

    WiFiClientSecure client;
    client.setInsecure();

    HTTPClient http;
    http.setTimeout(15000);
    if (!http.begin(client, cmd.url)) {
        errorDetail = "http.begin failed";
        return false;
    }

    int httpCode = http.GET();
    if (httpCode != HTTP_CODE_OK) {
        errorDetail = "http GET code " + String(httpCode);
        http.end();
        return false;
    }

    int contentLength = http.getSize();
    size_t otaSize = (contentLength > 0) ? (size_t)contentLength : UPDATE_SIZE_UNKNOWN;

    if (!Update.begin(otaSize)) {
        errorDetail = String("Update.begin failed: ") + Update.errorString();
        http.end();
        return false;
    }

    if (cmd.md5.length() > 0) {
        Update.setMD5(cmd.md5.c_str());
    }

    WiFiClient *stream = http.getStreamPtr();
    size_t written = Update.writeStream(*stream);

    if (contentLength > 0 && written != (size_t)contentLength) {
        Update.abort();
        errorDetail = "written bytes mismatch";
        http.end();
        return false;
    }

    if (!Update.end(true)) {
        errorDetail = String("Update.end failed: ") + Update.errorString();
        http.end();
        return false;
    }

    if (!Update.isFinished()) {
        errorDetail = "update not finished";
        http.end();
        return false;
    }

    http.end();
    return true;
}
