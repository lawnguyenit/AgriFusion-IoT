#include "FirebasePipeline.h"

#include <FS.h>
#include <LittleFS.h>

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

FirebaseBootstrapResult FirebasePipeline::begin(FirebaseConfig &firebaseConfig,
                                                FirebaseAuth &firebaseAuth,
                                                FirebaseData &firebaseData,
                                                FirebaseData &firebaseOtaData) {
    FirebaseBootstrapResult result;
    CUS_DBGLN("[FIREBASE] Dang khoi tao RTDB...");
    _ready = false;

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

    firebaseData.stopWiFiClient();
    firebaseOtaData.stopWiFiClient();
    Firebase.reset(&firebaseConfig);
    firebaseConfig = FirebaseConfig();
    firebaseAuth = FirebaseAuth();

#if USE_SIM_NETWORK
    _nativeFirebaseMode = false;
    result.transportConfigured = APP_FIREBASE_SIM_TRANSPORT_ENABLED;
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
    result.authSummary = buildAuthSetupSummary(result.usingLegacyAuth,
                                               result.tokenConfigured,
                                               result.legacyTokenLength,
                                               result.apiKeyLength) +
                         " transport=sim_http_rest";
    CUS_DBGF("[FIREBASE] Bootstrap config: %s\n", result.authSummary.c_str());
    result.probe = probeDatabaseAccess(firebaseData);
    result.readyAfterBegin = result.probe.ok;
    _ready = result.readyAfterBegin;
    return result;
#else
    _nativeFirebaseMode = true;
    result.transportConfigured = true;
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
    Firebase.begin(&firebaseConfig, &firebaseAuth);
    result.readyAfterBegin = Firebase.ready();
    result.probe = probeDatabaseAccess(firebaseData);
    _ready = result.readyAfterBegin;
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
    result.errorCode = ok ? 0 : -1;
    result.stage = rest.stage;
    result.detail = rest.detail;
    _ready = ok;
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
    return result;
#endif
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
    record.set("fallback_used", true);
    record.set("was_buffered", true);
    record.set("replayed", false);
    record.set("buffered_at_ms", (int)millis());
    if (reason && strlen(reason)) {
        record.set("buffer_reason", reason);
    }

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

    record.set("fallback_used", false);
    record.set("was_buffered", false);
    record.set("replayed", false);

    result.firebaseReady = ready();
    bool canUpload = result.networkReady && result.firebaseReady;
    if (canUpload) {
        result.uploadAttempted = true;
        String telemetryRefId;
        if (_rawTelemetryReporter.publishRecord(firebaseData, record, &telemetryRefId, err, false)) {
            _nodeRuntimePublisher.publishNodeLive(firebaseData,
                                                  payload,
                                                  telemetryRefId,
                                                  ctx,
                                                  sensorError,
                                                  utcMs);
            publishTelemetryDebug(firebaseData, true, telemetryRefId, "ok", utcMs);
            publishTelemetryChannel(firebaseData, true, false, false, "direct_upload", telemetryRefId, "ok", utcMs);
            CUS_DBGF("[FIREBASE] Node telemetry OK ref=%s\n", telemetryRefId.c_str());
            result.uploaded = true;
            result.stage = "uploaded";
            result.detail = "ok";
            result.refId = telemetryRefId;
            return result;
        }

        result.tlsError = isTlsTransportError(err);
        publishTelemetryDebug(firebaseData, false, "publish_record", err, utcMs);
        publishTelemetryChannel(firebaseData,
                                false,
                                true,
                                result.tlsError,
                                "direct_fail_buffered",
                                "publish_record",
                                err,
                                utcMs);
        CUS_DBGF("[FIREBASE] Node telemetry upload LOI: %s\n", err.c_str());
        result.stage = "publish_error";
        result.detail = err;
    } else if (!result.networkReady) {
        result.stage = "network_down";
        result.detail = "networkIsConnected=false";
    } else {
        result.stage = "firebase_not_ready";
        result.detail = "Firebase.ready=false";
    }

    const char *bufferReason = nullptr;
    if (result.stage == "publish_error") {
        bufferReason = err.c_str();
    } else if (result.stage == "firebase_not_ready") {
        bufferReason = "firebase_not_ready";
    } else if (result.stage == "network_down") {
        bufferReason = "network_down";
    } else {
        bufferReason = "offline";
    }

    result.bufferStoreOk = bufferRawRecord(record, bufferReason, offlineReplayPending);
    result.buffered = result.bufferStoreOk;
    if (!result.bufferStoreOk) {
        result.stage = "buffer_store_fail";
        if (result.detail.length()) {
            result.detail += " | saveOfflineData=false";
        } else {
            result.detail = "saveOfflineData=false";
        }
    }
    if (!canUpload) {
        publishTelemetryDebug(firebaseData, false, "offline_buffer", "wifi_or_firebase_not_ready", utcMs);
        publishTelemetryChannel(firebaseData,
                                false,
                                true,
                                false,
                                "offline_buffer",
                                "offline_buffer",
                                "wifi_or_firebase_not_ready",
                                utcMs);
    }

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
    if (!offlineReplayPending) {
        result.stage = "replay_no_pending_flag";
        result.detail = "offlineReplayPending=false";
        return result;
    }

    result.attempted = true;
    result.filePresent = LittleFS.exists(_cfg.offlineRawFile);
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
        offlineReplayPending = LittleFS.exists(_cfg.offlineRawFile);
        result.stage = "replay_open_fail";
        result.detail = _cfg.offlineRawFile;
        return result;
    }

    String remaining;
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

        record.set("was_buffered", true);
        record.set("replayed", true);
        record.set("fallback_used", true);
        record.set("replayed_at_ms", (int)millis());

        String rawRefId;
        String err;
        if (_rawTelemetryReporter.publishRecord(firebaseData, record, &rawRefId, err, false)) {
            result.replayedCount++;
            publishTelemetryChannel(firebaseData, true, true, false, "replay_upload", rawRefId, "ok", utcMs);
        } else {
            result.failedCount++;
            result.detail = err;
            publishTelemetryChannel(firebaseData,
                                    false,
                                    true,
                                    isTlsTransportError(err),
                                    "replay_fail",
                                    "publish_record",
                                    err,
                                    utcMs);
            remaining += line;
            remaining += '\n';
        }
    }
    in.close();

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
