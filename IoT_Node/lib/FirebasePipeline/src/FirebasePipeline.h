#ifndef FIREBASE_PIPELINE_H
#define FIREBASE_PIPELINE_H

#include <Arduino.h>
#include <FirebaseESP32.h>

#include "DeviceContext.h"
#include "NodeRuntimePublisher.h"
#include "RawTelemetryReporter.h"

struct FirebasePipelineConfig {
    const char *databaseUrl = "";
    const char *apiKey = "";
    const char *legacyToken = "";
    const char *offlineRawFile = "/offline_data.txt";
    uint32_t offlineReplayIntervalMs = 10000;
    uint16_t tlsRxBufferSize = 4096;
    uint16_t tlsTxBufferSize = 2048;
};

class FirebasePipeline {
public:
    FirebasePipeline(const FirebasePipelineConfig &cfg,
                     RawTelemetryReporter &rawTelemetryReporter,
                     NodeRuntimePublisher &nodeRuntimePublisher);

    bool configLooksValid() const;

    void begin(FirebaseConfig &firebaseConfig,
               FirebaseAuth &firebaseAuth,
               FirebaseData &firebaseData,
               FirebaseData &firebaseOtaData);

    void probeTelemetryPathIfNeeded(FirebaseData &firebaseData, uint64_t utcMs);

    bool pushPayload(FirebaseData &firebaseData,
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

private:
    FirebasePipelineConfig _cfg;
    RawTelemetryReporter &_rawTelemetryReporter;
    NodeRuntimePublisher &_nodeRuntimePublisher;
    uint32_t _lastReplayMs = 0;

    RawTelemetryRecordContext buildRecordContext(DeviceContext &deviceContext,
                                                 const String &fwVersion,
                                                 const String &runningPartition,
                                                 bool sensorError,
                                                 const char *payloadKind) const;

    bool isTlsTransportError(const String &err) const;

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

    void bufferRawRecord(FirebaseJson &record,
                         const char *reason,
                         bool &offlineReplayPending);
};

#endif
