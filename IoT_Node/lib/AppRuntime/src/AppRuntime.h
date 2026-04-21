#ifndef APP_RUNTIME_H
#define APP_RUNTIME_H

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>

#include <FirebaseESP32.h>

#include "Config.h"
#include "DeviceContext.h"
#include "FirebasePipeline.h"
#include "NodePacketBuilder.h"
#include "NodeRuntimePublisher.h"
#include "NPK.h"
#include "OtaBootGuard.h"
#include "OtaManager.h"
#include "OtaRtdbReporter.h"
#include "OtaStateStore.h"
#include "RawTelemetryReporter.h"
#include "Sht30Service.h"

class AppRuntime {
public:
    AppRuntime();

    void begin();

private:
    struct SensorMessage {
        char jsonPayload[APP_SENSOR_PAYLOAD_BUFFER_SIZE];
        char payloadKind[APP_MESSAGE_KIND_BUFFER_SIZE];
        bool isError;
    };

    struct SystemStatusCache {
        String state;
        String detail;
        uint32_t lastPublishMs = 0;
    };

    FirebaseConfig _firebaseConfig;
    FirebaseAuth _firebaseAuth;
    FirebaseData _firebaseData;
    FirebaseData _firebaseOtaData;

    DeviceContext _deviceContext;
    RawTelemetryReporter _rawTelemetryReporter;
    OtaStateStore _otaStateStore;
    OtaBootGuard _otaBootGuard;
    OtaRtdbReporter _otaReporter;
    OtaManager _otaManager;
    NodeRuntimePublisher _nodeRuntimePublisher;
    FirebasePipeline _firebasePipeline;
    Sht30Service _sht30Service;
    NodePacketBuilder _packetBuilder;
    MyNPK _npkSensor;
    HardwareSerial _serialNpk;

    TaskHandle_t _taskSensorHandle = nullptr;
    TaskHandle_t _taskNetworkHandle = nullptr;
    QueueHandle_t _dataQueue = nullptr;

    bool _offlineReplayPending = false;
    int _npkFailCount = 0;
    SystemStatusCache _statusCache;

    static NodeRuntimeConfig makeNodeRuntimeConfig();
    static FirebasePipelineConfig makeFirebasePipelineConfig();

    static void sensorTaskEntry(void *ctx);
    static void networkTaskEntry(void *ctx);

    void sensorTaskLoop();
    void networkTaskLoop();

    bool enqueueSensorMessage(const SensorMessage &msg,
                              TickType_t waitTicks = pdMS_TO_TICKS(APP_QUEUE_SEND_WAIT_MS));
    static void setMessagePayloadKind(SensorMessage &msg, const char *kind);

    String currentFwVersion() const;
    String currentFwPartition() const;

    void initTimeSync() const;
    void maintainTimeSync();
    static uint64_t utcEpochMsIfSynced();

    void publishNodeInfoIfDue(bool force = false);
    void publishSystemStatusCached(const char *state, const char *detail, bool force = false);

    OtaStoredEvent makeOtaEvent(const char *stage,
                                const char *status,
                                const String &detail,
                                const String &version,
                                const String &requestId) const;
    bool reportOrStoreOtaEvent(const OtaStoredEvent &event);
    void handleOtaCommandIfAny();
    void maybeConfirmOtaAfterHealthyWindow();
};

#endif
