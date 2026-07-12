#include "FirebasePipeline.h"

#include <FS.h>
#include <LittleFS.h>
#include <ArduinoJson.h>
#include <time.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "Storage.h"

#if USE_SIM_NETWORK
#include "SimA7680C.h"
#endif

FirebasePipeline::FirebasePipeline(const FirebasePipelineConfig &cfg,
                                   RawTelemetryReporter &rawTelemetryReporter,
                                   NodeRuntimePublisher &nodeRuntimePublisher)
    : _cfg(cfg),
      _rawTelemetryReporter(rawTelemetryReporter),
      _nodeRuntimePublisher(nodeRuntimePublisher),
      _nativeFirebaseMode(!(USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED)) {}

namespace {
const char *firebaseTokenTypeName(int type) {
    switch (type) {
        case token_type_legacy_token:
            return "legacy token";
        case token_type_id_token:
            return "id token";
        case token_type_custom_token:
            return "custom token";
        case token_type_oauth2_access_token:
            return "oauth2 access token";
        default:
            return "undefined";
    }
}

const char *firebaseTokenStatusName(int status) {
    switch (status) {
        case token_status_on_initialize:
            return "on_initialize";
        case token_status_on_signing:
            return "on_signing";
        case token_status_on_request:
            return "on_request";
        case token_status_on_refresh:
            return "on_refresh";
        case token_status_ready:
            return "ready";
        case token_status_error:
            return "error";
        default:
            return "uninitialized";
    }
}

void firebaseTokenStatusLogger(token_info_t info) {
    static int lastType = -1;
    static int lastStatus = -1;
    static int lastErrCode = 0x7fffffff;
    static String lastErrMessage;
    String errMessage = info.error.message.c_str();

    bool changed = lastType != (int)info.type ||
                   lastStatus != (int)info.status ||
                   lastErrCode != info.error.code ||
                   lastErrMessage != errMessage;
    if (!changed) {
        return;
    }

    lastType = (int)info.type;
    lastStatus = (int)info.status;
    lastErrCode = info.error.code;
    lastErrMessage = errMessage;

    CUS_DBGF("[FIREBASE] Token status: type=%s(%d) status=%s(%d) err_code=%d err=%s\n",
             firebaseTokenTypeName((int)info.type),
             (int)info.type,
             firebaseTokenStatusName((int)info.status),
             (int)info.status,
             info.error.code,
             info.error.message.c_str());
}

uint32_t replayUtcSec(uint64_t utcMs) {
    if (utcMs > 0) {
        return (uint32_t)(utcMs / 1000ULL);
    }
    time_t now = time(nullptr);
    if (now < 1700000000) {
        return 0;
    }
    return (uint32_t)now;
}

void setNull(JsonVariant value) {
    value.set(nullptr);
}

bool parseRecord(FirebaseJson &record, JsonDocument &doc) {
    String json;
    record.toString(json, false);
    return deserializeJson(doc, json) == DeserializationError::Ok;
}

bool saveRecord(FirebaseJson &record, JsonDocument &doc) {
    String json;
    serializeJson(doc, json);
    return record.setJsonData(json);
}

uint32_t extractRecordTsSample(JsonObjectConst root) {
    JsonVariantConst tsSample = root["system_record"]["time"]["ts_sample"];
    if (tsSample.isNull()) {
        return 0;
    }
    return static_cast<uint32_t>(tsSample.as<unsigned long>());
}

bool extractRecordTimeValid(JsonObjectConst root) {
    return root["system_record"]["time"]["time_valid"] | false;
}

uint32_t extractRecordSeqNo(JsonObjectConst root) {
    JsonVariantConst seqNo = root["system_record"]["identity"]["seq_no"];
    if (seqNo.isNull()) {
        return 0;
    }
    return static_cast<uint32_t>(seqNo.as<unsigned long>());
}

String canonicalTelemetryRecordId(uint32_t tsSample, uint32_t seqNo) {
    if (tsSample < 1700000000UL) {
        return "";
    }
    char buf[48];
    snprintf(buf, sizeof(buf), "%lu_%lu", (unsigned long)tsSample, (unsigned long)seqNo);
    return String(buf);
}

String canonicalTelemetryDateKey(uint32_t tsSample) {
    if (tsSample < 1700000000UL) {
        return "";
    }

    time_t sec = (time_t)tsSample;
    struct tm tmLocal;
#if defined(_WIN32)
    localtime_s(&tmLocal, &sec);
#else
    localtime_r(&sec, &tmLocal);
#endif
    char buf[16];
    strftime(buf, sizeof(buf), "%Y-%m-%d", &tmLocal);
    return String(buf);
}

String canonicalTelemetryPath(uint32_t tsSample, uint32_t seqNo) {
    String dateKey = canonicalTelemetryDateKey(tsSample);
    String recordId = canonicalTelemetryRecordId(tsSample, seqNo);
    if (!dateKey.length() || !recordId.length()) {
        return "";
    }
    return String(APP_RTDB_PATH_NODE_TELEMETRY) + "/" + dateKey + "/" + recordId;
}

bool restampReplayRecordIfNeeded(FirebaseJson &record, uint64_t utcMs) {
    uint32_t nowSec = replayUtcSec(utcMs);
    if (nowSec == 0) {
        return false;
    }

    JsonDocument doc;
    if (!parseRecord(record, doc)) {
        return false;
    }

    JsonObject root = doc.as<JsonObject>();
    JsonObject timeObject = root["system_record"]["time"].to<JsonObject>();
    bool timeValid = timeObject["time_valid"] | false;
    uint32_t tsSample = extractRecordTsSample(root);
    if (timeValid && tsSample >= 1700000000UL) {
        return false;
    }

    uint32_t seqNo = extractRecordSeqNo(root);
    String recordId = canonicalTelemetryRecordId(nowSec, seqNo);
    String recordPath = canonicalTelemetryPath(nowSec, seqNo);

    timeObject["ts_sample"] = (unsigned long)nowSec;
    timeObject["clock_source"] = "reconstructed_on_replay";
    timeObject["time_valid"] = true;
    timeObject["time_reconstructed"] = true;

    JsonObject identity = root["system_record"]["identity"].to<JsonObject>();
    identity["record_id"] = recordId;
    identity["record_path"] = recordPath;

    return saveRecord(record, doc);
}

bool updateUploadState(FirebaseJson &record,
                       const char *phase,
                       bool attempted,
                       bool uploadOk,
                       const char *stage,
                       int httpStatus,
                       int latencyMs,
                       bool tlsOk,
                       const String &errorCode,
                       const String &bufferReason) {
    JsonDocument doc;
    if (!parseRecord(record, doc)) {
        return false;
    }

    JsonObject slot = doc["sim_record"]["upload"][phase].to<JsonObject>();
    slot["attempted"] = attempted;
    slot["upload_ok"] = uploadOk;
    slot["upload_stage"] = stage ? stage : "";
    if (httpStatus >= 0) {
        slot["http_status"] = httpStatus;
    } else {
        setNull(slot["http_status"]);
    }
    if (latencyMs >= 0) {
        slot["upload_latency_ms"] = latencyMs;
    } else {
        setNull(slot["upload_latency_ms"]);
    }
    slot["tls_ok"] = tlsOk;
    slot["last_error_code"] = errorCode;
    slot["buffer_reason_code"] = bufferReason;
    return saveRecord(record, doc);
}

bool updateSyncState(FirebaseJson &record,
                     bool telemetryPersisted,
                     const String &telemetryPath,
                     bool buffered,
                     bool replayed,
                     bool latestUpdated,
                     const String &bufferReason,
                     const String &lastErrorCode) {
    JsonDocument doc;
    if (!parseRecord(record, doc)) {
        return false;
    }

    JsonObject sync = doc["system_record"]["sync"].to<JsonObject>();
    sync["telemetry_persisted"] = telemetryPersisted;
    if (telemetryPersisted && telemetryPath.length()) {
        sync["telemetry_record_path"] = telemetryPath;
    } else {
        setNull(sync["telemetry_record_path"]);
    }
    sync["buffered"] = buffered;
    sync["replayed"] = replayed;
    sync["latest_updated"] = latestUpdated;
    sync["buffer_reason_code"] = bufferReason;
    sync["last_error_code"] = lastErrorCode;
    return saveRecord(record, doc);
}
}  // namespace

bool FirebasePipeline::configLooksValid() const {
    String databaseUrl = _cfg.databaseUrl;
    return databaseUrl.startsWith("http") &&
           (databaseUrl.indexOf("firebaseio.com") >= 0 ||
            databaseUrl.indexOf("firebasedatabase.app") >= 0);
}

bool FirebasePipeline::ready() const {
    return _ready;
}

bool FirebasePipeline::usesNativeFirebase() const {
    return _nativeFirebaseMode;
}

String FirebasePipeline::stateSummary() const {
    char buf[448];
    snprintf(buf,
             sizeof(buf),
             "inst=%p mode=%s begin=%d transport=%d auth=%d publish=%d ready=%d last_probe=%s last_probe_http=%d last_publish=%s",
             (const void *)this,
             _nativeFirebaseMode ? "native" : "sim_rest",
             _beginDone ? 1 : 0,
             _transportReady ? 1 : 0,
             _authInitialized ? 1 : 0,
             _publishEnabled ? 1 : 0,
             _ready ? 1 : 0,
             _lastProbe.stage.c_str(),
             _lastProbe.httpCode,
             _lastPublishProbeDetail.c_str());
    return String(buf);
}

void FirebasePipeline::updateReadyFlag() {
    _ready = _beginDone && _transportReady && _authInitialized;
}

FirebaseBootstrapResult FirebasePipeline::begin(FirebaseConfig &firebaseConfig,
                                                FirebaseAuth &firebaseAuth,
                                                FirebaseData &firebaseData,
                                                FirebaseData &firebaseOtaData) {
    FirebaseBootstrapResult result;
    CUS_DBGLN("[FIREBASE] Dang khoi tao RTDB...");
    _ready = false;
    _beginDone = false;
    _transportReady = false;
    _authInitialized = false;
    _publishEnabled = false;
    _lastProbe = FirebaseProbeResult{};
    _lastPublishProbeDetail = "";
    _lastPublishProbePath = "";

    result.configValid = configLooksValid();
    if (!result.configValid) {
        CUS_DBGLN("[FIREBASE] CANH BAO: FIREBASE_DATABASE_URL chua dung dinh dang RTDB.");
        CUS_DBGLN("[FIREBASE] Vi du dung: https://<project>-default-rtdb.firebaseio.com");
    }

    bool hasLegacyToken = strlen(_cfg.legacyToken) > 0 &&
                          String(_cfg.legacyToken) != "YOUR_RTDB_LEGACY_TOKEN";
    result.usingLegacyAuth = hasLegacyToken;
    result.tokenConfigured = hasLegacyToken || strlen(_cfg.apiKey) > 0;
    result.legacyTokenLength = strlen(_cfg.legacyToken);
    result.apiKeyLength = strlen(_cfg.apiKey);

#if USE_SIM_NETWORK
    _nativeFirebaseMode = false;
    result.transportConfigured = APP_FIREBASE_SIM_TRANSPORT_ENABLED;
    _transportReady = result.transportConfigured;
    if (!result.transportConfigured) {
        result.authSummary = buildAuthSetupSummary(result.usingLegacyAuth,
                                                   result.tokenConfigured,
                                                   result.legacyTokenLength,
                                                   result.apiKeyLength) +
                             " transport=sim_bridge_missing";
        result.probe.attempted = false;
        result.probe.ok = false;
        result.probe.stage = "transport_not_ready";
        result.probe.detail = "sim_firebase_transport_not_implemented";
        CUS_DBGLN("[FIREBASE] SIM transport bridge cho Firebase chua duoc noi. Tam dung truoc Firebase.begin().");
        CUS_DBGF("[FIREBASE] Bootstrap config: %s\n", result.authSummary.c_str());
        return result;
    }

    result.beginAttempted = true;
    _beginDone = true;
    result.authSummary = buildAuthSetupSummary(result.usingLegacyAuth,
                                               result.tokenConfigured,
                                               result.legacyTokenLength,
                                               result.apiKeyLength) +
                         " transport=sim_http_rest";
    CUS_DBGF("[FIREBASE] Bootstrap config: %s\n", result.authSummary.c_str());
    result.probe = probeDatabaseAccess(firebaseData);
    result.readyAfterBegin = ready();
    return result;
#else
    firebaseData.stopWiFiClient();
    firebaseOtaData.stopWiFiClient();
    Firebase.reset(&firebaseConfig);
    firebaseConfig = FirebaseConfig();
    firebaseAuth = FirebaseAuth();

    _nativeFirebaseMode = true;
    result.transportConfigured = true;
    _transportReady = true;
    Firebase.reconnectWiFi(true);
#endif

    firebaseData.setBSSLBufferSize(_cfg.tlsRxBufferSize, _cfg.tlsTxBufferSize);
    firebaseOtaData.setBSSLBufferSize(_cfg.tlsRxBufferSize, _cfg.tlsTxBufferSize);
    firebaseData.setResponseSize(2048);
    firebaseOtaData.setResponseSize(2048);

    firebaseConfig.database_url = _cfg.databaseUrl;
    firebaseConfig.token_status_callback = firebaseTokenStatusLogger;

    if (hasLegacyToken) {
        firebaseConfig.api_key.clear();
        firebaseConfig.signer.tokens.legacy_token = _cfg.legacyToken;
        firebaseConfig.signer.tokens.token_type = token_type_legacy_token;
        firebaseConfig.signer.tokens.status = token_status_ready;
    } else {
        firebaseConfig.api_key = _cfg.apiKey;
    }

    result.authSummary = buildAuthSetupSummary(result.usingLegacyAuth,
                                               result.tokenConfigured,
                                               result.legacyTokenLength,
                                               result.apiKeyLength);
    CUS_DBGF("[FIREBASE] Bootstrap config: %s\n", result.authSummary.c_str());

    result.beginAttempted = true;
    _beginDone = true;
    Firebase.begin(&firebaseConfig, &firebaseAuth);
    _authInitialized = Firebase.ready();
    _publishEnabled = _authInitialized;
    updateReadyFlag();
    result.readyAfterBegin = ready();
    result.probe = probeDatabaseAccess(firebaseData);
    result.readyAfterBegin = ready();
    return result;
}

void FirebasePipeline::probeTelemetryPathIfNeeded(FirebaseData &firebaseData, uint64_t utcMs) {
    _nodeRuntimePublisher.probeTelemetryPathIfNeeded(firebaseData, utcMs);
}

FirebaseProbeResult FirebasePipeline::probeDatabaseAccess(FirebaseData &firebaseData) {
    FirebaseProbeResult result;
    result.attempted = true;

#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    RtdbRestResponse rest;
    bool ok = rtdbRestClient().probe(rest);
    result.ok = ok;
    result.httpCode = rest.statusCode;
    result.errorCode = ok ? 0 : (rest.transportOk ? rest.statusCode : -1);
    result.stage = rest.stage;
    char buf[256];
    snprintf(buf,
             sizeof(buf),
             "%s http=%d transport=%d response=%d detail=%s",
             rest.stage.c_str(),
             rest.statusCode,
             rest.transportOk ? 1 : 0,
             rest.responseReceived ? 1 : 0,
             rest.detail.c_str());
    result.detail = String(buf);
    _transportReady = rest.transportOk;
    _authInitialized = ok;
    _lastProbe = result;
    _publishEnabled = ok;
    _lastPublishProbePath = APP_RTDB_PATH_NODE_INFO;
    _lastPublishProbeDetail = ok ? "publish_gate_bypassed_sim_rest"
                                 : ("probe_fail: " + result.detail);
    updateReadyFlag();
    return result;
#else
    bool ok = Firebase.getShallowData(firebaseData, "/");
    result.ok = ok;
    result.httpCode = firebaseData.httpCode();
    result.errorCode = firebaseData.errorCode();

    if (ok) {
        result.stage = "rtdb_probe_ok";
        result.detail = "root shallow read ok";
    } else {
        result.stage = "rtdb_probe_fail";
        result.detail = firebaseData.errorReason();
        if (!result.detail.length()) {
            result.detail = "unknown_rtdb_probe_error";
        }
    }

    char buf[256];
    snprintf(buf,
             sizeof(buf),
             "%s http=%d err=%d detail=%s",
             result.stage.c_str(),
             result.httpCode,
             result.errorCode,
             result.detail.c_str());
    result.detail = String(buf);
    _transportReady = networkIsConnected();
    _authInitialized = ok || Firebase.ready();
    _publishEnabled = _authInitialized;
    _lastProbe = result;
    updateReadyFlag();
    return result;
#endif
}

bool FirebasePipeline::ensurePublishReady(FirebaseData &firebaseData, uint64_t utcMs) {
    (void)utcMs;
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    (void)firebaseData;
    _publishEnabled = _beginDone && _transportReady && _authInitialized;
    _lastPublishProbePath = APP_RTDB_PATH_NODE_TELEMETRY;
    if (_publishEnabled) {
        if (!_lastPublishProbeDetail.length() ||
            _lastPublishProbeDetail.startsWith("probe_fail")) {
            _lastPublishProbeDetail = "publish_gate_bypassed_sim_rest";
        }
    }
    updateReadyFlag();
    return _publishEnabled;
#else
    if (_publishEnabled) {
        updateReadyFlag();
        return true;
    }

    if (!_beginDone || !_transportReady || !_authInitialized) {
        updateReadyFlag();
        return false;
    }

    uint32_t now = millis();
    if (_lastPublishProbeMs > 0 &&
        (now - _lastPublishProbeMs) < APP_TELEMETRY_PROBE_INTERVAL_MS) {
        updateReadyFlag();
        return _publishEnabled;
    }
    _lastPublishProbeMs = now;

    String probePath;
    String probeError;
    if (_rawTelemetryReporter.probePublishPath(firebaseData, &probePath, probeError)) {
        _publishEnabled = true;
        _lastPublishProbePath = probePath;
        _lastPublishProbeDetail = "probe_ok";
    } else {
        _publishEnabled = false;
        _lastPublishProbePath = probePath;
        _lastPublishProbeDetail = probeError;
    }

    updateReadyFlag();
    return _publishEnabled;
#endif
}

bool FirebasePipeline::isAuthInitializationError(const String &err) const {
    return err.indexOf("authentication was not initialized") >= 0 ||
           err.indexOf("auth_not_initialized") >= 0 ||
           err.indexOf("Firebase.ready=false") >= 0;
}

RawTelemetryRecordContext FirebasePipeline::buildRecordContext(DeviceContext &deviceContext,
                                                               const String &fwVersion,
                                                               const String &runningPartition,
                                                               bool sensorError,
                                                               const char *payloadKind) const {
    RawTelemetryRecordContext ctx;
    bool hasInternet = networkIsConnected();
    ctx.deviceId = deviceContext.deviceId();
    ctx.bootId = deviceContext.bootId();
    ctx.firmwareVersion = fwVersion;
    ctx.runningPartition = runningPartition;
    ctx.wakeReason = deviceContext.wakeReason();
    ctx.recordType = sensorError ? "sensor_fault" : "sensor_sample";
    ctx.payloadKind = payloadKind ? payloadKind : "unknown";
    ctx.seq = deviceContext.nextSeq();
    ctx.tsDeviceMs = millis();
    ctx.resetReason = deviceContext.resetReason();
    ctx.wifiStatus = networkStatusCode();
    ctx.rssi = networkSignalDbm();
    ctx.hasInternet = hasInternet;
    ctx.sensorError = sensorError;
    return ctx;
}

bool FirebasePipeline::isTlsTransportError(const String &err) const {
    return err.indexOf("SSL") >= 0 ||
           err.indexOf("ssl") >= 0 ||
           err.indexOf("TLS") >= 0 ||
           err.indexOf("tls") >= 0 ||
           err.indexOf("handshake") >= 0 ||
           err.indexOf("mbedtls") >= 0 ||
           err.indexOf("record is too large") >= 0;
}

bool FirebasePipeline::shouldPublishSuccessDiagnostics() {
    uint32_t now = millis();
    if (_lastSuccessDiagPublishMs > 0 &&
        (now - _lastSuccessDiagPublishMs) < APP_TELEMETRY_SUCCESS_DIAG_INTERVAL_MS) {
        return false;
    }
    _lastSuccessDiagPublishMs = now;
    return true;
}

void FirebasePipeline::publishTelemetryDebug(FirebaseData &firebaseData,
                                             bool ok,
                                             const String &refOrPath,
                                             const String &detail,
                                             uint64_t utcMs) {
    _nodeRuntimePublisher.publishTelemetryDebug(firebaseData, ok, refOrPath, detail, utcMs);
}

void FirebasePipeline::publishTelemetryChannel(FirebaseData &firebaseData,
                                               bool ok,
                                               bool fallbackUsed,
                                               bool tlsError,
                                               const char *stage,
                                               const String &refOrPath,
                                               const String &detail,
                                               uint64_t utcMs) {
    _nodeRuntimePublisher.publishTelemetryChannel(firebaseData,
                                                  ok,
                                                  fallbackUsed,
                                                  tlsError,
                                                  stage,
                                                  refOrPath,
                                                  detail,
                                                  utcMs);
}

String FirebasePipeline::buildAuthSetupSummary(bool usingLegacyAuth,
                                               bool tokenConfigured,
                                               uint16_t legacyTokenLength,
                                               uint16_t apiKeyLength) const {
    char buf[224];
    snprintf(buf,
             sizeof(buf),
             "url_ok=%d auth=%s token_cfg=%d legacy_len=%u api_len=%u",
             configLooksValid() ? 1 : 0,
             usingLegacyAuth ? "legacy" : "api_key",
             tokenConfigured ? 1 : 0,
             (unsigned)legacyTokenLength,
             (unsigned)apiKeyLength);
    return String(buf);
}

bool FirebasePipeline::bufferRawRecord(FirebaseJson &record,
                                       const char *reason,
                                       bool &offlineReplayPending) {
    String reasonCode = (reason && strlen(reason)) ? String(reason) : String("offline");
    updateSyncState(record, false, "", true, false, false, reasonCode, reasonCode);

    String line;
    record.toString(line, false);
    offlineReplayPending = saveOfflineData(line);
    return offlineReplayPending;
}

bool FirebasePipeline::pushPayload(FirebaseData &firebaseData,
                                   const char *payload,
                                   bool sensorError,
                                   const char *payloadKind,
                                   DeviceContext &deviceContext,
                                   const String &fwVersion,
                                   const String &runningPartition,
                                   bool &offlineReplayPending,
                                   uint64_t utcMs) {
    TelemetryPushResult result = pushPayloadDetailed(firebaseData,
                                                     payload,
                                                     sensorError,
                                                     payloadKind,
                                                     deviceContext,
                                                     fwVersion,
                                                     runningPartition,
                                                     offlineReplayPending,
                                                     utcMs);
    return result.uploaded;
}

TelemetryPushResult FirebasePipeline::pushPayloadDetailed(FirebaseData &firebaseData,
                                                          const char *payload,
                                                          bool sensorError,
                                                          const char *payloadKind,
                                                          DeviceContext &deviceContext,
                                                          const String &fwVersion,
                                                          const String &runningPartition,
                                                          bool &offlineReplayPending,
                                                          uint64_t utcMs) {
    RawTelemetryRecordContext ctx = buildRecordContext(deviceContext,
                                                       fwVersion,
                                                       runningPartition,
                                                       sensorError,
                                                       payloadKind);

    TelemetryPushResult result;
    result.networkReady = ctx.hasInternet;

    FirebaseJson record;
    String err;
    if (!_rawTelemetryReporter.buildRecord(payload, ctx, record, err)) {
        CUS_DBGF("[FIREBASE] telemetry build LOI: %s\n", err.c_str());
        publishTelemetryDebug(firebaseData, false, "build_record", err, utcMs);
        publishTelemetryChannel(firebaseData, false, false, false, "build_record", "build_record", err, utcMs);
        result.stage = "build_error";
        result.detail = err;
        return result;
    }

    ensurePublishReady(firebaseData, utcMs);
    result.transportReady = _transportReady;
    result.beginDone = _beginDone;
    result.authInitialized = _authInitialized;
    result.publishEnabled = _publishEnabled;
    result.firebaseReady = ready();
    result.pipelineState = stateSummary();

    bool canUpload = result.networkReady &&
                     result.transportReady &&
                     result.beginDone &&
                     result.authInitialized &&
                     result.publishEnabled;

    if (!result.networkReady) {
        result.stage = "network_down";
        result.detail = "networkIsConnected=false";
    } else if (!result.transportReady) {
        result.stage = "publish_blocked_transport_not_ready";
        result.detail = result.pipelineState;
    } else if (!result.beginDone) {
        result.stage = "publish_blocked_begin_not_done";
        result.detail = result.pipelineState;
    } else if (!result.authInitialized) {
        result.stage = "publish_blocked_auth_not_initialized";
        result.detail = result.pipelineState;
    } else if (!result.publishEnabled) {
        result.stage = "publish_blocked_gate_not_ready";
        result.detail = result.pipelineState;
    }

    if (canUpload) {
        result.uploadAttempted = true;
        TelemetryPublishResult publishResult;
        uint32_t uploadStartMs = millis();

        updateUploadState(record, "direct", true, true, "direct_upload", -1, -1, true, "", "");
        updateSyncState(record, false, "", false, false, false, "", "");

        if (_rawTelemetryReporter.publishRecord(firebaseData, record, publishResult, err)) {
            int uploadLatencyMs = (int)(millis() - uploadStartMs);
            updateUploadState(record,
                              "direct",
                              true,
                              true,
                              "direct_upload",
                              publishResult.httpStatus,
                              uploadLatencyMs,
                              !result.tlsError,
                              "",
                              "");
            updateSyncState(record, true, publishResult.path, false, false, false, "", "");

            String latestError;
            bool latestUpdated = false;
            if (!_nodeRuntimePublisher.publishLatestIfNewer(firebaseData, record, &latestUpdated, &latestError)) {
                CUS_DBGF("[FIREBASE] latest update fail: %s\n", latestError.c_str());
            }

            result.uploaded = true;
            result.latestUpdated = latestUpdated;
            result.stage = "uploaded";
            result.detail = latestUpdated ? "ok_latest_updated" : "ok_latest_unchanged";
            result.refId = publishResult.refId;
            result.telemetryPath = publishResult.path;
            if (shouldPublishSuccessDiagnostics()) {
                publishTelemetryDebug(firebaseData, true, publishResult.path, result.detail, utcMs);
                publishTelemetryChannel(firebaseData, true, false, false, "direct_upload", publishResult.path, result.detail, utcMs);
            }
            CUS_DBGF("[FIREBASE] Node telemetry OK path=%s\n", publishResult.path.c_str());
            return result;
        }

        int uploadLatencyMs = (int)(millis() - uploadStartMs);
        result.tlsError = isTlsTransportError(err) || isTlsTransportError(publishResult.detail);
        result.refId = publishResult.refId;
        result.telemetryPath = publishResult.path;

        if (publishResult.duplicate) {
            updateUploadState(record,
                              "direct",
                              true,
                              false,
                              "duplicate_key",
                              publishResult.httpStatus,
                              uploadLatencyMs,
                              !result.tlsError,
                              "duplicate_key",
                              "");
            updateSyncState(record, true, publishResult.path, false, false, false, "", "duplicate_key");

            String latestError;
            bool latestUpdated = false;
            if (!_nodeRuntimePublisher.publishLatestIfNewer(firebaseData, record, &latestUpdated, &latestError)) {
                CUS_DBGF("[FIREBASE] latest update after duplicate fail: %s\n", latestError.c_str());
            }

            result.uploaded = true;
            result.duplicate = true;
            result.latestUpdated = latestUpdated;
            result.stage = "duplicate_key";
            result.detail = "telemetry_record_exists";
            publishTelemetryDebug(firebaseData, true, publishResult.path, result.detail, utcMs);
            publishTelemetryChannel(firebaseData, true, false, false, "duplicate_key", publishResult.path, result.detail, utcMs);
            return result;
        }

        if (isAuthInitializationError(err)) {
            _authInitialized = false;
            _publishEnabled = false;
            updateReadyFlag();
            result.transportReady = _transportReady;
            result.beginDone = _beginDone;
            result.authInitialized = _authInitialized;
            result.publishEnabled = _publishEnabled;
            result.firebaseReady = ready();
            result.pipelineState = stateSummary();
            result.stage = "publish_blocked_auth_not_initialized";
            result.detail = err.length() ? err : result.pipelineState;
        } else {
            result.stage = publishResult.stage.length() ? publishResult.stage : "publish_error";
            result.detail = err.length() ? err : publishResult.detail;
        }

        String directErrorCode = result.stage.length() ? result.stage : String("publish_error");
        updateUploadState(record,
                          "direct",
                          true,
                          false,
                          result.stage.c_str(),
                          publishResult.httpStatus,
                          uploadLatencyMs,
                          !result.tlsError,
                          directErrorCode,
                          directErrorCode);
        updateSyncState(record, false, "", false, false, false, directErrorCode, directErrorCode);

        publishTelemetryDebug(firebaseData, false, "publish_record", result.detail, utcMs);
        publishTelemetryChannel(firebaseData,
                                false,
                                true,
                                result.tlsError,
                                "direct_fail_buffered",
                                publishResult.path.length() ? publishResult.path : String("publish_record"),
                                result.detail,
                                utcMs);
        CUS_DBGF("[FIREBASE] Node telemetry upload LOI: %s\n", result.detail.c_str());
    }

    String bufferReason = result.stage.length() ? result.stage : String("offline");
    if (!result.uploadAttempted) {
        updateUploadState(record, "direct", false, false, result.stage.c_str(), -1, -1, false, "", bufferReason);
        updateSyncState(record, false, "", false, false, false, bufferReason, bufferReason);
    }

    result.bufferStoreOk = bufferRawRecord(record, bufferReason.c_str(), offlineReplayPending);
    result.buffered = result.bufferStoreOk;
    if (!result.bufferStoreOk) {
        result.stage = "buffer_store_fail";
        result.detail = result.detail.length() ? (result.detail + " | saveOfflineData=false") : "saveOfflineData=false";
    }

    publishTelemetryDebug(firebaseData, false, "offline_buffer", result.stage, utcMs);
    publishTelemetryChannel(firebaseData,
                            false,
                            true,
                            result.tlsError,
                            "offline_buffer",
                            "offline_buffer",
                            result.stage,
                            utcMs);

    return result;
}

void FirebasePipeline::replayOfflineIfAny(FirebaseData &firebaseData,
                                          bool &offlineReplayPending,
                                          uint64_t utcMs) {
    (void)replayOfflineIfAnyDetailed(firebaseData, offlineReplayPending, utcMs);
}

OfflineReplayResult FirebasePipeline::replayOfflineIfAnyDetailed(FirebaseData &firebaseData,
                                                                 bool &offlineReplayPending,
                                                                 uint64_t utcMs) {
    OfflineReplayResult result;
    uint32_t now = millis();
    if (now - _lastReplayMs < _cfg.offlineReplayIntervalMs) {
        result.stage = "replay_not_due";
        result.detail = "interval_guard";
        return result;
    }
    _lastReplayMs = now;

    result.networkReady = networkIsConnected();
    ensurePublishReady(firebaseData, utcMs);
    result.firebaseReady = ready();
    if (!result.networkReady) {
        result.stage = "replay_network_down";
        result.detail = "networkIsConnected=false";
        return result;
    }
    if (!result.firebaseReady) {
        result.stage = "replay_firebase_not_ready";
        result.detail = "Firebase.ready=false";
        return result;
    }
    if (!_publishEnabled) {
        result.stage = "replay_publish_gate_not_ready";
        result.detail = _lastPublishProbeDetail.length() ? _lastPublishProbeDetail : "publish_gate_not_ready";
        return result;
    }
    if (!offlineReplayPending) {
        result.stage = "replay_no_pending_flag";
        result.detail = "offlineReplayPending=false";
        return result;
    }

    result.attempted = true;
    result.filePresent = storageFileExists(_cfg.offlineRawFile);
    if (!result.filePresent) {
        offlineReplayPending = false;
        result.stage = "replay_file_missing";
        result.detail = _cfg.offlineRawFile;
        return result;
    }

    File in = LittleFS.open(_cfg.offlineRawFile, FILE_READ);
    result.fileOpenOk = (bool)in;
    if (!in) {
        CUS_DBGLN("[STORAGE] Khong mo duoc file replay offline.");
        offlineReplayPending = storageFileExists(_cfg.offlineRawFile);
        result.stage = "replay_open_fail";
        result.detail = _cfg.offlineRawFile;
        return result;
    }

    String remaining;
    bool haveLatestCandidate = false;
    uint32_t latestCandidateTs = 0;
    FirebaseJson latestCandidateRecord;
    while (in.available()) {
        String line = in.readStringUntil('\n');
        line.trim();
        if (!line.length()) {
            continue;
        }

        FirebaseJson record;
        if (!record.setJsonData(line)) {
            CUS_DBGLN("[STORAGE] Bo qua dong JSON loi trong offline_data.");
            result.invalidJsonCount++;
            continue;
        }

        restampReplayRecordIfNeeded(record, utcMs);

        TelemetryPublishResult publishResult;
        String err;
        uint32_t uploadStartMs = millis();
        updateUploadState(record, "replay", true, true, "replay_upload", -1, -1, true, "", "");
        updateSyncState(record, false, "", false, true, false, "", "");

        if (_rawTelemetryReporter.publishRecord(firebaseData, record, publishResult, err)) {
            int uploadLatencyMs = (int)(millis() - uploadStartMs);
            updateUploadState(record,
                              "replay",
                              true,
                              true,
                              "replay_upload",
                              publishResult.httpStatus,
                              uploadLatencyMs,
                              true,
                              "",
                              "");
            updateSyncState(record, true, publishResult.path, false, true, false, "", "");
            result.replayedCount++;

            JsonDocument replayDoc;
            if (parseRecord(record, replayDoc)) {
                uint32_t candidateTs = extractRecordTsSample(replayDoc.as<JsonObjectConst>());
                if (candidateTs > latestCandidateTs) {
                    latestCandidateTs = candidateTs;
                    String recordJson;
                    record.toString(recordJson, false);
                    latestCandidateRecord.setJsonData(recordJson);
                    haveLatestCandidate = candidateTs >= 1700000000UL;
                }
            }

            publishTelemetryChannel(firebaseData, true, true, false, "replay_upload", publishResult.path, "ok", utcMs);
            continue;
        }

        int uploadLatencyMs = (int)(millis() - uploadStartMs);
        if (publishResult.duplicate) {
            updateUploadState(record,
                              "replay",
                              true,
                              false,
                              "duplicate_key",
                              publishResult.httpStatus,
                              uploadLatencyMs,
                              true,
                              "duplicate_key",
                              "");
            updateSyncState(record, true, publishResult.path, false, true, false, "", "duplicate_key");
            result.replayedCount++;

            JsonDocument replayDoc;
            if (parseRecord(record, replayDoc)) {
                uint32_t candidateTs = extractRecordTsSample(replayDoc.as<JsonObjectConst>());
                if (candidateTs > latestCandidateTs) {
                    latestCandidateTs = candidateTs;
                    String recordJson;
                    record.toString(recordJson, false);
                    latestCandidateRecord.setJsonData(recordJson);
                    haveLatestCandidate = candidateTs >= 1700000000UL;
                }
            }

            publishTelemetryChannel(firebaseData, true, true, false, "replay_duplicate", publishResult.path, "duplicate_key", utcMs);
            continue;
        }

        {
            result.failedCount++;
            String errorCode = publishResult.stage.length() ? publishResult.stage : String("replay_fail");
            updateUploadState(record,
                              "replay",
                              true,
                              false,
                              errorCode.c_str(),
                              publishResult.httpStatus,
                              uploadLatencyMs,
                              !isTlsTransportError(err),
                              errorCode,
                              errorCode);
            updateSyncState(record, false, "", true, false, false, errorCode, errorCode);

            result.detail = err.length() ? err : publishResult.detail;
            publishTelemetryChannel(firebaseData,
                                    false,
                                    true,
                                    isTlsTransportError(result.detail),
                                    "replay_fail",
                                    publishResult.path.length() ? publishResult.path : String("publish_record"),
                                    result.detail,
                                    utcMs);
            String remainingLine;
            record.toString(remainingLine, false);
            remaining += remainingLine;
            remaining += '\n';
        }
    }
    in.close();

    if (haveLatestCandidate) {
        String latestError;
        bool latestUpdated = false;
        if (_nodeRuntimePublisher.publishLatestIfNewer(firebaseData, latestCandidateRecord, &latestUpdated, &latestError)) {
            result.latestUpdated = latestUpdated;
        } else if (latestError.length()) {
            result.detail = result.detail.length() ? (result.detail + " | latest=" + latestError) : ("latest=" + latestError);
        }
    }

    if (!remaining.length()) {
        result.cleanupOk = LittleFS.remove(_cfg.offlineRawFile);
        offlineReplayPending = false;
    } else {
        File out = LittleFS.open(_cfg.offlineRawFile, "w");
        if (out) {
            out.print(remaining);
            out.close();
        } else {
            result.rewriteOk = false;
        }
        offlineReplayPending = true;
    }
    result.hasRemaining = offlineReplayPending;

    if (result.replayedCount) {
        CUS_DBGF("[STORAGE] Replay offline thanh cong %lu ban ghi.\n", (unsigned long)result.replayedCount);
    }

    if (!result.rewriteOk) {
        result.stage = "replay_rewrite_fail";
        if (!result.detail.length()) {
            result.detail = "cannot rewrite remaining offline file";
        }
    } else if (!result.cleanupOk && !result.hasRemaining) {
        result.stage = "replay_cleanup_fail";
        if (!result.detail.length()) {
            result.detail = "cannot remove offline file";
        }
    } else if (result.failedCount > 0) {
        result.stage = "replay_partial_fail";
    } else if (result.invalidJsonCount > 0 && result.replayedCount == 0) {
        result.stage = "replay_invalid_json_only";
        result.detail = "all pending lines invalid";
    } else if (result.replayedCount > 0) {
        result.stage = "replay_ok";
        result.detail = "offline records uploaded";
    } else {
        result.stage = "replay_no_valid_records";
        if (!result.detail.length()) {
            result.detail = "no records replayed";
        }
    }

    return result;
}
