#ifndef FIREBASE_PIPELINE_H
#define FIREBASE_PIPELINE_H

#include <Arduino.h>
#include <FirebaseESP32.h>

#include "DeviceContext.h"
#include "NodeRuntimePublisher.h"
#include "RawTelemetryReporter.h"
#include "RtdbRestClient.h"

struct FirebasePipelineConfig {
    const char *databaseUrl = "";
    const char *apiKey = "";
    const char *legacyToken = "";
    const char *offlineRawFile = "/offline_data.txt";
    uint32_t offlineReplayIntervalMs = 10000;
    uint16_t tlsRxBufferSize = 4096;
    uint16_t tlsTxBufferSize = 2048;
};

struct TelemetryPushResult {
    bool uploaded = false;
    bool buffered = false;
    bool uploadAttempted = false;
    bool networkReady = false;
    bool transportReady = false;
    bool beginDone = false;
    bool authInitialized = false;
    bool publishEnabled = false;
    bool firebaseReady = false;
    bool tlsError = false;
    bool bufferStoreOk = false;
    String stage;
    String detail;
    String refId;
    String pipelineState;
};

struct OfflineReplayResult {
    bool attempted = false;
    bool networkReady = false;
    bool firebaseReady = false;
    bool filePresent = false;
    bool fileOpenOk = false;
    bool rewriteOk = true;
    bool cleanupOk = true;
    bool hasRemaining = false;
    uint32_t replayedCount = 0;
    uint32_t failedCount = 0;
    uint32_t invalidJsonCount = 0;
    String stage;
    String detail;
};

struct FirebaseProbeResult {
    bool attempted = false;
    bool ok = false;
    int httpCode = 0;
    int errorCode = 0;
    String stage;
    String detail;
};

struct FirebaseBootstrapResult {
    bool configValid = false;
    bool transportConfigured = false;
    bool beginAttempted = false;
    bool usingLegacyAuth = false;
    bool tokenConfigured = false;
    bool readyAfterBegin = false;
    uint16_t legacyTokenLength = 0;
    uint16_t apiKeyLength = 0;
    String authSummary;
    FirebaseProbeResult probe;
};

class FirebasePipeline {
public:
    FirebasePipeline(const FirebasePipelineConfig &cfg,
                     RawTelemetryReporter &rawTelemetryReporter,
                     NodeRuntimePublisher &nodeRuntimePublisher);

    bool configLooksValid() const;

    FirebaseBootstrapResult begin(FirebaseConfig &firebaseConfig,
                                  FirebaseAuth &firebaseAuth,
                                  FirebaseData &firebaseData,
                                  FirebaseData &firebaseOtaData);

    bool ready() const;
    bool usesNativeFirebase() const;
    String stateSummary() const;

    void probeTelemetryPathIfNeeded(FirebaseData &firebaseData, uint64_t utcMs);

    FirebaseProbeResult probeDatabaseAccess(FirebaseData &firebaseData);

    bool pushPayload(FirebaseData &firebaseData,
                     const char *payload,
                     bool sensorError,
                     const char *payloadKind,
                     DeviceContext &deviceContext,
                     const String &fwVersion,
                     const String &runningPartition,
                     bool &offlineReplayPending,
                     uint64_t utcMs);

    TelemetryPushResult pushPayloadDetailed(FirebaseData &firebaseData,
                                           const char *payload,
                                           bool sensorError,
                                           const char *payloadKind,
                                           DeviceContext &deviceContext,
                                           const String &fwVersion,
                                           const String &runningPartition,
                                           bool &offlineReplayPending,
                                           uint64_t utcMs);

    void replayOfflineIfAny(FirebaseData &firebaseData,
                            bool &offlineReplayPending,
                            uint64_t utcMs);

    OfflineReplayResult replayOfflineIfAnyDetailed(FirebaseData &firebaseData,
                                                   bool &offlineReplayPending,
                                                   uint64_t utcMs);

private:
    FirebasePipelineConfig _cfg;
    RawTelemetryReporter &_rawTelemetryReporter;
    NodeRuntimePublisher &_nodeRuntimePublisher;
    uint32_t _lastReplayMs = 0;
    uint32_t _lastPublishProbeMs = 0;
    bool _nativeFirebaseMode = true;
    bool _ready = false;
    bool _beginDone = false;
    bool _transportReady = false;
    bool _authInitialized = false;
    bool _publishEnabled = false;
    FirebaseProbeResult _lastProbe;
    String _lastPublishProbeDetail;
    String _lastPublishProbePath;
    uint32_t _lastSuccessDiagPublishMs = 0;

    RawTelemetryRecordContext buildRecordContext(DeviceContext &deviceContext,
                                                 const String &fwVersion,
                                                 const String &runningPartition,
                                                 bool sensorError,
                                                 const char *payloadKind) const;

    void updateReadyFlag();
    bool ensurePublishReady(FirebaseData &firebaseData, uint64_t utcMs);
    bool isAuthInitializationError(const String &err) const;
    bool isTlsTransportError(const String &err) const;
    bool shouldPublishSuccessDiagnostics();

    void publishTelemetryDebug(FirebaseData &firebaseData,
                               bool ok,
                               const String &refOrPath,
                               const String &detail,
                               uint64_t utcMs);

    void publishTelemetryChannel(FirebaseData &firebaseData,
                                 bool ok,
                                 bool fallbackUsed,
                                 bool tlsError,
                                 const char *stage,
                                 const String &refOrPath,
                                 const String &detail,
                                 uint64_t utcMs);

    String buildAuthSetupSummary(bool usingLegacyAuth,
                                 bool tokenConfigured,
                                 uint16_t legacyTokenLength,
                                 uint16_t apiKeyLength) const;

    bool bufferRawRecord(FirebaseJson &record,
                         const char *reason,
                         bool &offlineReplayPending);
};

#endif
