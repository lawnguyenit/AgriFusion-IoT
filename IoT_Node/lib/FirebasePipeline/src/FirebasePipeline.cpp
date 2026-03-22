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
      _nodeRuntimePublisher(nodeRuntimePublisher) {}

bool FirebasePipeline::configLooksValid() const {
    String databaseUrl = _cfg.databaseUrl;
    return databaseUrl.startsWith("http") &&
           (databaseUrl.indexOf("firebaseio.com") >= 0 ||
            databaseUrl.indexOf("firebasedatabase.app") >= 0);
}

void FirebasePipeline::begin(FirebaseConfig &firebaseConfig,
                             FirebaseAuth &firebaseAuth,
                             FirebaseData &firebaseData,
                             FirebaseData &firebaseOtaData) {
    CUS_DBGLN("[FIREBASE] Dang khoi tao RTDB...");

    if (!configLooksValid()) {
        CUS_DBGLN("[FIREBASE] CANH BAO: FIREBASE_DATABASE_URL chua dung dinh dang RTDB.");
        CUS_DBGLN("[FIREBASE] Vi du dung: https://<project>-default-rtdb.firebaseio.com");
    }

    firebaseConfig.database_url = _cfg.databaseUrl;
    firebaseConfig.api_key = _cfg.apiKey;

    if (strlen(_cfg.legacyToken) > 0 && String(_cfg.legacyToken) != "YOUR_RTDB_LEGACY_TOKEN") {
        firebaseConfig.signer.tokens.legacy_token = _cfg.legacyToken;
    }

    Firebase.begin(&firebaseConfig, &firebaseAuth);
#if USE_SIM_NETWORK
    firebaseData.setGSMClient(&client, &modem, SIM_GSM_PIN, SIM_APN, SIM_APN_USER, SIM_APN_PASS);
    firebaseOtaData.setGSMClient(&client, &modem, SIM_GSM_PIN, SIM_APN, SIM_APN_USER, SIM_APN_PASS);
    Firebase.reconnectNetwork(true);
#else
    Firebase.reconnectWiFi(true);
#endif

    firebaseData.setBSSLBufferSize(_cfg.tlsRxBufferSize, _cfg.tlsTxBufferSize);
    firebaseOtaData.setBSSLBufferSize(_cfg.tlsRxBufferSize, _cfg.tlsTxBufferSize);
}

void FirebasePipeline::probeTelemetryPathIfNeeded(FirebaseData &firebaseData, uint64_t utcMs) {
    _nodeRuntimePublisher.probeTelemetryPathIfNeeded(firebaseData, utcMs);
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

void FirebasePipeline::bufferRawRecord(FirebaseJson &record,
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
    RawTelemetryRecordContext ctx = buildRecordContext(deviceContext,
                                                       fwVersion,
                                                       runningPartition,
                                                       sensorError,
                                                       payloadKind);

    FirebaseJson record;
    String err;
    if (!_rawTelemetryReporter.buildRecord(payload, ctx, record, err)) {
        CUS_DBGF("[FIREBASE] telemetry build LOI: %s\n", err.c_str());
        publishTelemetryDebug(firebaseData, false, "build_record", err, utcMs);
        publishTelemetryChannel(firebaseData, false, false, false, "build_record", "build_record", err, utcMs);
        return false;
    }

    record.set("fallback_used", false);
    record.set("was_buffered", false);
    record.set("replayed", false);

    bool canUpload = networkIsConnected() && Firebase.ready();
    if (canUpload) {
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
            return true;
        }

        publishTelemetryDebug(firebaseData, false, "publish_record", err, utcMs);
        publishTelemetryChannel(firebaseData,
                                false,
                                true,
                                isTlsTransportError(err),
                                "direct_fail_buffered",
                                "publish_record",
                                err,
                                utcMs);
        CUS_DBGF("[FIREBASE] Node telemetry upload LOI: %s\n", err.c_str());
    }

    bufferRawRecord(record, canUpload ? err.c_str() : "offline", offlineReplayPending);
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

    return false;
}

void FirebasePipeline::replayOfflineIfAny(FirebaseData &firebaseData,
                                          bool &offlineReplayPending,
                                          uint64_t utcMs) {
    uint32_t now = millis();
    if (now - _lastReplayMs < _cfg.offlineReplayIntervalMs) {
        return;
    }
    _lastReplayMs = now;

    if (!networkIsConnected() || !Firebase.ready() || !offlineReplayPending) {
        return;
    }

    if (!LittleFS.exists(_cfg.offlineRawFile)) {
        offlineReplayPending = false;
        return;
    }

    File in = LittleFS.open(_cfg.offlineRawFile, FILE_READ);
    if (!in) {
        CUS_DBGLN("[STORAGE] Khong mo duoc file replay offline.");
        offlineReplayPending = LittleFS.exists(_cfg.offlineRawFile);
        return;
    }

    String remaining;
    uint32_t replayedCount = 0;
    while (in.available()) {
        String line = in.readStringUntil('\n');
        line.trim();
        if (!line.length()) {
            continue;
        }

        FirebaseJson record;
        if (!record.setJsonData(line)) {
            CUS_DBGLN("[STORAGE] Bo qua dong JSON loi trong offline_data.");
            continue;
        }

        record.set("was_buffered", true);
        record.set("replayed", true);
        record.set("fallback_used", true);
        record.set("replayed_at_ms", (int)millis());

        String rawRefId;
        String err;
        if (_rawTelemetryReporter.publishRecord(firebaseData, record, &rawRefId, err, false)) {
            replayedCount++;
            publishTelemetryChannel(firebaseData, true, true, false, "replay_upload", rawRefId, "ok", utcMs);
        } else {
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
        LittleFS.remove(_cfg.offlineRawFile);
        offlineReplayPending = false;
    } else {
        File out = LittleFS.open(_cfg.offlineRawFile, "w");
        if (out) {
            out.print(remaining);
            out.close();
        }
        offlineReplayPending = true;
    }

    if (replayedCount) {
        CUS_DBGF("[STORAGE] Replay offline thanh cong %lu ban ghi.\n", (unsigned long)replayedCount);
    }
}
