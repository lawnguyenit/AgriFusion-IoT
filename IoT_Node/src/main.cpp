#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <freertos/queue.h>
#include <WiFi.h>
#include <FS.h>
#include <LittleFS.h>
#include <FirebaseESP32.h>
#include <ArduinoJson.h>
#include <time.h>
#include <cstring>
#include <esp_task_wdt.h>

#include "Storage.h"
#include "Config.h"
#include "NPK.h"
#include "NetworkBridge.h"
#include "DeviceContext.h"
#include "FirebasePipeline.h"
#include "RawTelemetryReporter.h"
#include "NodeRuntimePublisher.h"
#include "OtaStateStore.h"
#include "OtaBootGuard.h"
#include "OtaRtdbReporter.h"
#include "OtaManager.h"
#include "Sht30Service.h"

#if USE_SIM_NETWORK
#include "SimA7680C.h"
#endif

#define APP_LOG_SYS(fmt, ...)    CUS_DBGF(APP_LOG_SYS_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_SENSOR(fmt, ...) CUS_DBGF(APP_LOG_SENSOR_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_NET(fmt, ...)    CUS_DBGF(APP_LOG_NET_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_CLOUD(fmt, ...)  CUS_DBGF(APP_LOG_CLOUD_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_OTA(fmt, ...)    CUS_DBGF(APP_LOG_OTA_TAG " " fmt, ##__VA_ARGS__)

FirebaseConfig firebaseConfig;
FirebaseAuth firebaseAuth;

namespace {
bool gOfflineReplayPending = false;

TaskHandle_t gTaskSensorHandle = nullptr;
TaskHandle_t gTaskNetworkHandle = nullptr;
QueueHandle_t gDataQueue = nullptr;

FirebaseData gFirebaseData;
FirebaseData gFirebaseOtaData;

DeviceContext gDeviceContext;
RawTelemetryReporter gRawTelemetryReporter(APP_RTDB_PATH_NODE_ROOT);
OtaStateStore gOtaStateStore;
OtaBootGuard gOtaBootGuard;
OtaRtdbReporter gOtaReporter(APP_RTDB_PATH_OTA_STATUS, APP_RTDB_PATH_OTA_HISTORY);
OtaManager gOtaManager;

int gNpkFailCount = 0;

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

SystemStatusCache gStatusCache;
MyNPK gNpkSensor;
HardwareSerial gSerialNpk(1);

NodeRuntimeConfig makeNodeRuntimeConfig() {
    NodeRuntimeConfig cfg;
    cfg.nodeRootPath = APP_RTDB_PATH_NODE_ROOT;
    cfg.nodeInfoPath = APP_RTDB_PATH_NODE_INFO;
    cfg.nodeLivePath = APP_RTDB_PATH_NODE_LIVE;
    cfg.nodeStatusEventsPath = APP_RTDB_PATH_NODE_STATUS;
    cfg.nodeId = APP_NODE_ID;
    cfg.deviceUid = APP_NODE_DEVICE_UID;
    cfg.siteId = APP_NODE_SITE_ID;
    cfg.powerType = APP_NODE_POWER_TYPE;
    cfg.timezone = APP_NODE_TIMEZONE;
    cfg.telemetryRetentionDays = APP_TELEMETRY_RETENTION_DAYS;
    cfg.wakeIntervalSec = APP_SENSOR_SAMPLE_INTERVAL_MS / 1000U;
    cfg.nodeInfoPushIntervalMs = APP_NODE_INFO_PUSH_INTERVAL_MS;
    cfg.probeIntervalMs = APP_TELEMETRY_PROBE_INTERVAL_MS;
    return cfg;
}

FirebasePipelineConfig makeFirebasePipelineConfig() {
    FirebasePipelineConfig cfg;
    cfg.databaseUrl = APP_FIREBASE_DATABASE_URL;
    cfg.apiKey = APP_FIREBASE_API_KEY;
    cfg.legacyToken = APP_FIREBASE_LEGACY_TOKEN;
    cfg.offlineRawFile = APP_OFFLINE_RAW_FILE;
    cfg.offlineReplayIntervalMs = APP_OFFLINE_REPLAY_INTERVAL_MS;
    cfg.tlsRxBufferSize = 4096;
    cfg.tlsTxBufferSize = 2048;
    return cfg;
}

NodeRuntimePublisher gNodeRuntimePublisher(makeNodeRuntimeConfig());
FirebasePipeline gFirebasePipeline(makeFirebasePipelineConfig(), gRawTelemetryReporter, gNodeRuntimePublisher);
Sht30Service gSht30Service(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, APP_SHT30_RETRY_INIT_MS);

String currentFwVersion();
String currentFwPartition();
uint64_t utcEpochMsIfSynced();
void initTimeSync();
void maintainTimeSync();

bool enqueueSensorMessage(const SensorMessage& msg, TickType_t waitTicks = pdMS_TO_TICKS(APP_QUEUE_SEND_WAIT_MS)) {
    if (xQueueSend(gDataQueue, &msg, waitTicks) == pdPASS) {
        return true;
    }

    APP_LOG_SENSOR("Queue day, bo mat ban tin hien tai.\n");
    return false;
}

void setMessagePayloadKind(SensorMessage& msg, const char* kind) {
    msg.payloadKind[0] = '\0';
    if (!kind) {
        return;
    }
    strncpy(msg.payloadKind, kind, sizeof(msg.payloadKind) - 1);
    msg.payloadKind[sizeof(msg.payloadKind) - 1] = '\0';
}

void copyObject(JsonObject dst, JsonObjectConst src) {
    for (JsonPairConst kv : src) {
        dst[kv.key().c_str()] = kv.value();
    }
}

String buildCombinedNodePacket(const String& npkPayloadJson, bool npkAlarm) {
    JsonDocument outDoc;
    outDoc["schema_version"] = 3;
    outDoc["node_key"] = APP_NODE_SLOT_KEY;
    outDoc["node_id"] = APP_NODE_ID;
    outDoc["node_name"] = APP_NODE_NAME;

    JsonObject packet = outDoc["packet"].to<JsonObject>();

    JsonDocument npkDoc;
    JsonObject npkOut = packet["npk_data"].to<JsonObject>();
    if (deserializeJson(npkDoc, npkPayloadJson) == DeserializationError::Ok) {
        copyObject(npkOut, npkDoc.as<JsonObjectConst>());
    } else {
        npkOut["read_ok"] = false;
        npkOut["error_code"] = "npk_payload_invalid";
    }
    npkOut["edge_system"] = APP_EDGE_SYSTEM_NPK;
    npkOut["edge_system_id"] = APP_EDGE_SYSTEM_ID_NPK;
    npkOut["edge_stream"] = "npk";

    JsonDocument shtDoc;
    JsonObject shtOut = packet["sht30_data"].to<JsonObject>();
    String shtJson = gSht30Service.buildJsonPayload("sht30_air",
                                                    "sht30_1",
                                                    APP_EDGE_SYSTEM_SHT,
                                                    APP_EDGE_SYSTEM_ID_SHT,
                                                    "sht30",
                                                    SHT30_READ_MAX_ATTEMPTS,
                                                    SHT30_RETRY_DELAY_MS,
                                                    SHT30_MAX_WAIT_MS);
    if (deserializeJson(shtDoc, shtJson) == DeserializationError::Ok) {
        copyObject(shtOut, shtDoc.as<JsonObjectConst>());
    } else {
        shtOut["sht_read_ok"] = false;
        shtOut["sht_error"] = "sht_payload_invalid";
    }

    JsonObject systemOut = packet["system_data"].to<JsonObject>();
    systemOut["edge_system_primary"] = APP_EDGE_SYSTEM_NPK;
    systemOut["edge_system_secondary"] = APP_EDGE_SYSTEM_SHT;
    systemOut["edge_system_id_primary"] = APP_EDGE_SYSTEM_ID_NPK;
    systemOut["edge_system_id_secondary"] = APP_EDGE_SYSTEM_ID_SHT;
    systemOut["wifi_status"] = networkStatusCode();
    systemOut["wifi_connected"] = networkIsConnected();
    systemOut["rssi"] = networkSignalDbm();
    systemOut["transport"] = networkTransportName();
    systemOut["npk_alarm"] = npkAlarm;
    systemOut["sht_ready"] = gSht30Service.ready();
    systemOut["firmware_version"] = currentFwVersion();
    systemOut["running_partition"] = currentFwPartition();
    systemOut["ts_device_ms"] = (int)millis();

    String out;
    serializeJson(outDoc, out);
    return out;
}

String currentFwVersion() {
    return gOtaBootGuard.info().runningVersion.length()
               ? gOtaBootGuard.info().runningVersion
               : OtaBootGuard::currentRunningVersion();
}

String currentFwPartition() {
    return gOtaBootGuard.info().runningPartition.length()
               ? gOtaBootGuard.info().runningPartition
               : OtaBootGuard::currentRunningPartition();
}

OtaStoredEvent makeOtaEvent(const char* stage,
                            const char* status,
                            const String& detail,
                            const String& version,
                            const String& requestId) {
    OtaStoredEvent ev;
    ev.valid = true;
    ev.stage = stage;
    ev.status = status;
    ev.detail = detail;
    ev.version = version;
    ev.requestId = requestId;
    return ev;
}

bool reportOrStoreOtaEvent(const OtaStoredEvent& event) {
    if (!event.valid) {
        return true;
    }

    if (networkIsConnected() && Firebase.ready()) {
        if (gOtaReporter.reportEvent(gFirebaseOtaData, event, currentFwVersion(), currentFwPartition())) {
            return true;
        }
        APP_LOG_OTA("Report fail: %s\n", gFirebaseOtaData.errorReason().c_str());
    }

    return gOtaStateStore.savePendingEvent(event);
}

void publishSystemStatusCached(const char* state, const char* detail, bool force = false) {
    String nextState = state ? state : "unknown";
    String nextDetail = detail ? detail : "";
    uint32_t now = millis();
    bool changed = (gStatusCache.state != nextState) || (gStatusCache.detail != nextDetail);
    bool refreshDue = (now - gStatusCache.lastPublishMs) >= APP_STATUS_REFRESH_INTERVAL_MS;

    if (!force && !changed && !refreshDue) {
        return;
    }

    gNodeRuntimePublisher.publishSystemStatus(gFirebaseData, state, detail, utcEpochMsIfSynced());
    gStatusCache.state = nextState;
    gStatusCache.detail = nextDetail;
    gStatusCache.lastPublishMs = now;
}

void publishNodeInfoIfDue(bool force = false) {
    gNodeRuntimePublisher.publishNodeInfoIfDue(gFirebaseData,
                                               gDeviceContext,
                                               currentFwVersion(),
                                               force,
                                               utcEpochMsIfSynced());
}

void initTimeSync() {
    configTzTime(APP_NODE_TZ_CONFIG, "time.google.com", "pool.ntp.org", "time.cloudflare.com");
}

void maintainTimeSync() {
    static uint32_t lastAttemptMs = 0;
    if (!networkIsConnected()) {
        return;
    }
    if (utcEpochMsIfSynced() > 0) {
        return;
    }
    if (millis() - lastAttemptMs < APP_TIME_SYNC_RETRY_MS) {
        return;
    }

    lastAttemptMs = millis();
    APP_LOG_NET("NTP chua sync, thu dong bo lai.\n");
    initTimeSync();
}

uint64_t utcEpochMsIfSynced() {
    time_t now = time(nullptr);
    if (now < 1700000000) {
        return 0;
    }
    return static_cast<uint64_t>(now) * 1000ULL;
}

void handleOtaCommandIfAny() {
    static uint32_t lastPollMs = 0;
    uint32_t now = millis();
    if (now - lastPollMs < APP_OTA_POLL_INTERVAL_MS) {
        return;
    }
    lastPollMs = now;

    OtaCommand cmd;
    String err;
    if (!gOtaManager.fetchCommand(gFirebaseOtaData, APP_RTDB_PATH_OTA_COMMAND, cmd, err)) {
        APP_LOG_OTA("Poll command fail: %s\n", err.c_str());
        return;
    }

    if (!cmd.enabled) {
        return;
    }

    String lastHandled = gOtaStateStore.loadLastHandledRequestId();
    if (!cmd.force && cmd.requestId == lastHandled) {
        APP_LOG_OTA("Duplicate request ignored: %s\n", cmd.requestId.c_str());
        gOtaManager.disableCommand(gFirebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
        return;
    }

    String runningVer = currentFwVersion();
    if (!cmd.force && cmd.version.length() > 0 && cmd.version == runningVer) {
        reportOrStoreOtaEvent(makeOtaEvent("command", "skipped", "same firmware version", cmd.version, cmd.requestId));
        gOtaStateStore.saveLastHandledRequestId(cmd.requestId);
        gOtaManager.disableCommand(gFirebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
        return;
    }

    reportOrStoreOtaEvent(makeOtaEvent("download", "started", cmd.url, cmd.version, cmd.requestId));
    publishSystemStatusCached("ota_downloading", cmd.version.c_str(), true);

    String targetPartition;
    String otaErr;
    if (!gOtaManager.performHttpOta(cmd, targetPartition, otaErr)) {
        reportOrStoreOtaEvent(makeOtaEvent("update", "failed", otaErr, cmd.version, cmd.requestId));
        gOtaStateStore.saveLastHandledRequestId(cmd.requestId);
        gOtaManager.disableCommand(gFirebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
        publishSystemStatusCached("ota_failed", otaErr.c_str(), true);
        return;
    }

    OtaPendingValidationInfo pending;
    pending.active = true;
    pending.requestId = cmd.requestId;
    pending.targetVersion = cmd.version;
    pending.targetPartition = targetPartition;
    pending.previousPartition = currentFwPartition();
    pending.bootCount = 0;
    gOtaStateStore.savePendingValidation(pending);
    gOtaStateStore.saveLastHandledRequestId(cmd.requestId);

    reportOrStoreOtaEvent(makeOtaEvent("reboot", "pending_validation", targetPartition, cmd.version, cmd.requestId));
    gOtaManager.disableCommand(gFirebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
    publishSystemStatusCached("ota_rebooting", cmd.version.c_str(), true);

    delay(1000);
    ESP.restart();
}

void maybeConfirmOtaAfterHealthyWindow() {
    static bool confirmedThisBoot = false;
    static uint32_t healthySinceMs = 0;

    if (confirmedThisBoot || !gOtaBootGuard.isPendingValidation()) {
        return;
    }

    bool healthy = networkIsConnected() && Firebase.ready();
    if (!healthy) {
        healthySinceMs = 0;
        return;
    }

    if (healthySinceMs == 0) {
        healthySinceMs = millis();
        return;
    }

    if (millis() - healthySinceMs < APP_OTA_CONFIRM_HEALTH_MS) {
        return;
    }

    if (gOtaBootGuard.confirmPendingValidation(gOtaStateStore)) {
        confirmedThisBoot = true;
        gOtaReporter.flushPendingEvent(gFirebaseOtaData, gOtaStateStore, currentFwVersion(), currentFwPartition());
        publishSystemStatusCached("ota_confirmed", currentFwVersion().c_str(), true);
    }
}
}  // namespace

void TaskSensor(void *pvParameters) {
    (void)pvParameters;

    gSerialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    gNpkSensor.begin(gSerialNpk);
    gSht30Service.tryInit();

    TickType_t lastWakeTick = xTaskGetTickCount();
    uint32_t lastSampleMs = 0;
    bool firstCycle = true;

    APP_LOG_SENSOR("Task bat dau, chu ky lay mau %lu giay.\n",
                   (unsigned long)(APP_SENSOR_SAMPLE_INTERVAL_MS / 1000UL));

    for (;;) {
        if (!firstCycle) {
            vTaskDelayUntil(&lastWakeTick, pdMS_TO_TICKS(APP_SENSOR_SAMPLE_INTERVAL_MS));
        }
        firstCycle = false;

        if (!gSht30Service.ready()) {
            APP_LOG_SENSOR("SHT30 chua ready, thu init lai.\n");
            gSht30Service.tryInit();
        }

        uint32_t sampleStartMs = millis();
        uint32_t sampleIntervalMs = (lastSampleMs == 0) ? 0 : (sampleStartMs - lastSampleMs);
        lastSampleMs = sampleStartMs;

        APP_LOG_SENSOR("Bat dau chu ky do moi, elapsed=%lu ms.\n", (unsigned long)sampleIntervalMs);

        NPK_Data data = gNpkSensor.read();
        SensorMessage npkMsg = {};

        bool recoveredAfterFail = false;
        uint32_t failStreakBeforeRecover = 0;
        bool sensorAlarm = false;

        if (data.readOk) {
            if (gNpkFailCount > 0) {
                recoveredAfterFail = true;
                failStreakBeforeRecover = (uint32_t)gNpkFailCount;
                APP_LOG_SENSOR("NPK phuc hoi sau %d lan fail lien tiep.\n", gNpkFailCount);
            }
            gNpkFailCount = 0;
        } else {
            gNpkFailCount++;
            APP_LOG_SENSOR("NPK fail streak=%d code=%s(0x%02X)\n",
                           gNpkFailCount,
                           MyNPK::errorCodeToString(data.errorCodeRaw),
                           data.errorCodeRaw);

            if (gNpkFailCount > 0 && (gNpkFailCount % APP_NPK_UART_RESET_FAIL_INTERVAL) == 0) {
                APP_LOG_SENSOR("Reset lai UART NPK do fail streak cao.\n");
                gSerialNpk.end();
                delay(80);
                gSerialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
                gNpkSensor.begin(gSerialNpk);
                delay(50);
            }

            if (gNpkFailCount >= APP_NPK_FAIL_ALARM_THRESHOLD) {
                sensorAlarm = true;
                APP_LOG_SENSOR("Canh bao NPK fail den nguong alarm.\n");
            }
        }

        String npkJson = gNpkSensor.makeJsonFromData(data,
                                                     sampleIntervalMs,
                                                     (uint32_t)gNpkFailCount,
                                                     recoveredAfterFail,
                                                     failStreakBeforeRecover,
                                                     sensorAlarm);

        String combinedPayload = buildCombinedNodePacket(npkJson, sensorAlarm);
        APP_LOG_SENSOR("Packet size=%u bytes.\n", (unsigned)combinedPayload.length());
        if (combinedPayload.length() >= sizeof(npkMsg.jsonPayload)) {
            APP_LOG_SENSOR("Payload qua lon (%u bytes), bo qua chu ky nay.\n",
                           (unsigned)combinedPayload.length());
            continue;
        }

        combinedPayload.toCharArray(npkMsg.jsonPayload, sizeof(npkMsg.jsonPayload));
        npkMsg.isError = sensorAlarm;
        setMessagePayloadKind(npkMsg, APP_PAYLOAD_KIND_NODE_PACKET);

        if (enqueueSensorMessage(npkMsg)) {
            APP_LOG_SENSOR("Da day mau vao queue, read_ok=%d alarm=%d.\n",
                           data.readOk ? 1 : 0,
                           sensorAlarm ? 1 : 0);
        }
    }
}

void TaskNetwork(void *pvParameters) {
    (void)pvParameters;

    esp_task_wdt_delete(NULL);

    APP_LOG_NET("Task bat dau, mode=%s.\n", APP_RUN_CONTINUOUS ? "continuous" : "sleep");

    bool netOk = networkSetup();
    if (!netOk) {
        APP_LOG_NET("Khoi dong mang that bai, se retry trong loop.\n");
    }

    gFirebasePipeline.begin(firebaseConfig, firebaseAuth, gFirebaseData, gFirebaseOtaData);
    initTimeSync();
    setupStorage();
    gOfflineReplayPending = LittleFS.exists(APP_OFFLINE_RAW_FILE);

    gOtaReporter.flushPendingEvent(gFirebaseOtaData, gOtaStateStore, currentFwVersion(), currentFwPartition());
    publishSystemStatusCached("boot", "network task started", true);
    publishNodeInfoIfDue(true);

    SensorMessage rcvMsg = {};

    for (;;) {
        networkMaintain();
        bool hasInternet = networkIsConnected();

        if (hasInternet && Firebase.ready()) {
            maintainTimeSync();
            gFirebasePipeline.probeTelemetryPathIfNeeded(gFirebaseData, utcEpochMsIfSynced());
            publishNodeInfoIfDue(false);
            gOtaReporter.flushPendingEvent(gFirebaseOtaData, gOtaStateStore, currentFwVersion(), currentFwPartition());
            maybeConfirmOtaAfterHealthyWindow();
            handleOtaCommandIfAny();
            gFirebasePipeline.replayOfflineIfAny(gFirebaseData, gOfflineReplayPending, utcEpochMsIfSynced());
        }

        if (xQueueReceive(gDataQueue, &rcvMsg, pdMS_TO_TICKS(APP_QUEUE_RECV_WAIT_MS)) == pdPASS) {
            const char* payloadKind = strlen(rcvMsg.payloadKind) ? rcvMsg.payloadKind : "unknown_json";
            APP_LOG_NET("Nhan payload kind=%s, error=%d.\n", payloadKind, rcvMsg.isError ? 1 : 0);

            if (rcvMsg.isError) {
                APP_LOG_CLOUD("Sensor alarm -> push telemetry fault + status.\n");
                gFirebasePipeline.pushPayload(gFirebaseData,
                                              rcvMsg.jsonPayload,
                                              true,
                                              APP_PAYLOAD_KIND_SENSOR_ALARM,
                                              gDeviceContext,
                                              currentFwVersion(),
                                              currentFwPartition(),
                                              gOfflineReplayPending,
                                              utcEpochMsIfSynced());
                publishSystemStatusCached("sensor_alarm", "sensor fault buffered or uploaded", true);
            } else if (gFirebasePipeline.pushPayload(gFirebaseData,
                                                     rcvMsg.jsonPayload,
                                                     false,
                                                     payloadKind,
                                                     gDeviceContext,
                                                     currentFwVersion(),
                                                     currentFwPartition(),
                                                     gOfflineReplayPending,
                                                     utcEpochMsIfSynced())) {
                APP_LOG_CLOUD("Upload RTDB OK.\n");
                publishSystemStatusCached("online", "rtdb write ok");
            } else {
                APP_LOG_CLOUD("Upload fail/offline -> buffered.\n");
                publishSystemStatusCached(hasInternet ? "degraded" : "offline_buffering",
                                          hasInternet ? "rtdb write fail, buffered" : "offline buffered");
            }
        }

        vTaskDelay(pdMS_TO_TICKS(APP_NETWORK_LOOP_DELAY_MS));
    }
}

void setup() {
#if DEBUG_MODE
    DEBUG_PORT.begin(DEBUG_BAUDRATE);
    Serial.begin(DEBUG_BAUDRATE);
    delay(1000);
    APP_LOG_SYS("Khoi dong node %s, mode=%s, chu ky=%lu giay.\n",
                APP_NODE_ID,
                APP_RUN_CONTINUOUS ? "continuous" : "sleep",
                (unsigned long)(APP_SENSOR_SAMPLE_INTERVAL_MS / 1000UL));
#endif

    gDeviceContext.begin();
    gOtaBootGuard.begin(gOtaStateStore, APP_OTA_MAX_PENDING_BOOTS);

    gDataQueue = xQueueCreate(APP_QUEUE_LENGTH, sizeof(SensorMessage));
    if (gDataQueue == NULL) {
        APP_LOG_SYS("Khong tao duoc data queue.\n");
        return;
    }

    xTaskCreatePinnedToCore(TaskSensor,
                            "SensorTask",
                            APP_SENSOR_TASK_STACK_SIZE,
                            NULL,
                            APP_SENSOR_TASK_PRIORITY,
                            &gTaskSensorHandle,
                            APP_SENSOR_TASK_CORE);

    xTaskCreatePinnedToCore(TaskNetwork,
                            "NetworkTask",
                            APP_NETWORK_TASK_STACK_SIZE,
                            NULL,
                            APP_NETWORK_TASK_PRIORITY,
                            &gTaskNetworkHandle,
                            APP_NETWORK_TASK_CORE);
}

void loop() {
    vTaskDelete(NULL);
}
