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

FirebaseConfig firebaseConfig;
FirebaseAuth firebaseAuth;

// RTDB config for Firebase Hosting / Web app / AI pipeline.
static const char* FIREBASE_DATABASE_URL = "https://agri-fusion-iot-default-rtdb.asia-southeast1.firebasedatabase.app";
static const char* FIREBASE_API_KEY = "AIzaSyAih-kFW-VkgEKVXnTd7aiFCiUjNy-6j18";
static const char* FIREBASE_LEGACY_TOKEN = "wZehBBnCza75i6iNpcUgKQT463dmHXMbfqRuYVsc";

static const char* RTDB_PATH_NODE_ROOT = "/Node1";
static const char* RTDB_PATH_NODE_INFO = "/Node1/info";
static const char* RTDB_PATH_NODE_LIVE = "/Node1/live";
static const char* RTDB_PATH_NODE_STATUS_EVENTS = "/Node1/status_events";
static const char* OFFLINE_RAW_FILE = "/offline_data.txt";
static bool gOfflineReplayPending = false;

// Edge-system classification for multi-edge ingestion pipelines.
static const char* EDGE_SYSTEM_NPK = "soil_npk_edge";
static const char* EDGE_SYSTEM_ID_NPK = "edge_npk_01";
static const char* EDGE_SYSTEM_SHT = "air_climate_edge";
static const char* EDGE_SYSTEM_ID_SHT = "edge_sht30_01";

// Node registry metadata (edit for each deployed node).
static const char* NODE_SLOT_KEY = "Node1";
static const char* NODE_ID = "Node1";
static const char* NODE_NAME = "Vuon sau rieng A";
static const char* NODE_SITE_ID = "farm_a_zone_1";
static const char* NODE_DEVICE_UID = "esp32s3_node1";

static const char* NODE_POWER_TYPE = "solar_battery";
static const uint32_t TELEMETRY_RETENTION_DAYS = 30;
static const char* NODE_TIMEZONE = "Asia/Ho_Chi_Minh";

// OTA paths (single-device deployment).
static const char* RTDB_PATH_OTA_STATUS = "/ota/status";
static const char* RTDB_PATH_OTA_HISTORY = "/ota/history";
static const char* RTDB_PATH_OTA_COMMAND = "/ota/command";

static const uint32_t OTA_POLL_INTERVAL_MS = 15000; //15s
static const uint32_t OTA_CONFIRM_HEALTH_MS = 60000; //60s
static const uint32_t OTA_MAX_PENDING_BOOTS = 3; // Max count reboot = 3
static const uint32_t OFFLINE_REPLAY_INTERVAL_MS = 10000;
static const uint32_t NODE_INFO_PUSH_INTERVAL_MS = 300000; // 5 min
static const uint32_t SENSOR_SAMPLE_INTERVAL_MS = 30000; // chu ky 30s
static const uint32_t NETWORK_LOOP_DELAY_MS = 150;
static const size_t SENSOR_PAYLOAD_BUFFER_SIZE = 1536;
static const uint32_t TIME_SYNC_RETRY_MS = 30000;

TaskHandle_t TaskSensor_Handle;
TaskHandle_t TaskNetwork_Handle;
QueueHandle_t dataQueue;

FirebaseData firebaseData;
FirebaseData firebaseOtaData;

DeviceContext deviceContext;
RawTelemetryReporter rawTelemetryReporter(RTDB_PATH_NODE_ROOT);
OtaStateStore otaStateStore;
OtaBootGuard otaBootGuard;
OtaRtdbReporter otaReporter(RTDB_PATH_OTA_STATUS, RTDB_PATH_OTA_HISTORY);
OtaManager otaManager;

int npkFailCount = 0;
const int NPK_MAX_FAIL = 10;
const uint32_t SHT30_RETRY_INIT_MS = 10000;

struct SensorMessage {
    char jsonPayload[SENSOR_PAYLOAD_BUFFER_SIZE];
    char payloadKind[24];
    bool isError;
};

MyNPK npkSensor;
HardwareSerial SerialNPK(1);
static NodeRuntimeConfig makeNodeRuntimeConfig() {
    NodeRuntimeConfig cfg;
    cfg.nodeRootPath = RTDB_PATH_NODE_ROOT;
    cfg.nodeInfoPath = RTDB_PATH_NODE_INFO;
    cfg.nodeLivePath = RTDB_PATH_NODE_LIVE;
    cfg.nodeStatusEventsPath = RTDB_PATH_NODE_STATUS_EVENTS;
    cfg.nodeId = NODE_ID;
    cfg.deviceUid = NODE_DEVICE_UID;
    cfg.siteId = NODE_SITE_ID;
    cfg.powerType = NODE_POWER_TYPE;
    cfg.timezone = NODE_TIMEZONE;
    cfg.telemetryRetentionDays = TELEMETRY_RETENTION_DAYS;
    cfg.wakeIntervalSec = SENSOR_SAMPLE_INTERVAL_MS / 1000U;
    cfg.nodeInfoPushIntervalMs = NODE_INFO_PUSH_INTERVAL_MS;
    cfg.probeIntervalMs = 30000;
    return cfg;
}

static FirebasePipelineConfig makeFirebasePipelineConfig() {
    FirebasePipelineConfig cfg;
    cfg.databaseUrl = FIREBASE_DATABASE_URL;
    cfg.apiKey = FIREBASE_API_KEY;
    cfg.legacyToken = FIREBASE_LEGACY_TOKEN;
    cfg.offlineRawFile = OFFLINE_RAW_FILE;
    cfg.offlineReplayIntervalMs = OFFLINE_REPLAY_INTERVAL_MS;
    cfg.tlsRxBufferSize = 4096;
    cfg.tlsTxBufferSize = 2048;
    return cfg;
}

NodeRuntimePublisher nodeRuntimePublisher(makeNodeRuntimeConfig());
FirebasePipeline firebasePipeline(makeFirebasePipelineConfig(), rawTelemetryReporter, nodeRuntimePublisher);
Sht30Service sht30Service(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, SHT30_RETRY_INIT_MS);

static String currentFwVersion();
static String currentFwPartition();
static uint64_t utcEpochMsIfSynced();
static void initTimeSync();
static void maintainTimeSync();

static bool enqueueSensorMessage(const SensorMessage& msg, TickType_t waitTicks = pdMS_TO_TICKS(10)) {
    if (xQueueSend(dataQueue, &msg, waitTicks) == pdPASS) {
        return true;
    }

    CUS_DBGLN("[QUEUE] Day queue du -> Mat ban tin!");
    return false;
}

static void setMessagePayloadKind(SensorMessage& msg, const char* kind) {
    msg.payloadKind[0] = '\0';
    if (!kind) {
        return;
    }
    strncpy(msg.payloadKind, kind, sizeof(msg.payloadKind) - 1);
    msg.payloadKind[sizeof(msg.payloadKind) - 1] = '\0';
}

static void copyObject(JsonObject dst, JsonObjectConst src) {
    for (JsonPairConst kv : src) {
        dst[kv.key().c_str()] = kv.value();
    }
}

static String buildCombinedNodePacket(const String& npkPayloadJson, bool npkAlarm) {
    JsonDocument outDoc;
    outDoc["schema_version"] = 3;
    outDoc["node_key"] = NODE_SLOT_KEY;
    outDoc["node_id"] = NODE_ID;
    outDoc["node_name"] = NODE_NAME;

    JsonObject packet = outDoc["packet"].to<JsonObject>();

    JsonDocument npkDoc;
    JsonObject npkOut = packet["npk_data"].to<JsonObject>();
    if (deserializeJson(npkDoc, npkPayloadJson) == DeserializationError::Ok) {
        JsonObjectConst npkSrc = npkDoc.as<JsonObjectConst>();
        copyObject(npkOut, npkSrc);
    } else {
        npkOut["read_ok"] = false;
        npkOut["error_code"] = "npk_payload_invalid";
    }
    npkOut["edge_system"] = EDGE_SYSTEM_NPK;
    npkOut["edge_system_id"] = EDGE_SYSTEM_ID_NPK;
    npkOut["edge_stream"] = "npk";

    JsonDocument shtDoc;
    JsonObject shtOut = packet["sht30_data"].to<JsonObject>();
    String shtJson = sht30Service.buildJsonPayload("sht30_air",
                                                   "sht30_1",
                                                   EDGE_SYSTEM_SHT,
                                                   EDGE_SYSTEM_ID_SHT,
                                                   "sht30",
                                                   SHT30_READ_MAX_ATTEMPTS,
                                                   SHT30_RETRY_DELAY_MS,
                                                   SHT30_MAX_WAIT_MS);
    if (deserializeJson(shtDoc, shtJson) == DeserializationError::Ok) {
        JsonObjectConst shtSrc = shtDoc.as<JsonObjectConst>();
        copyObject(shtOut, shtSrc);
    } else {
        shtOut["sht_read_ok"] = false;
        shtOut["sht_error"] = "sht_payload_invalid";
    }

    JsonObject systemOut = packet["system_data"].to<JsonObject>();
    systemOut["edge_system_primary"] = EDGE_SYSTEM_NPK;
    systemOut["edge_system_secondary"] = EDGE_SYSTEM_SHT;
    systemOut["edge_system_id_primary"] = EDGE_SYSTEM_ID_NPK;
    systemOut["edge_system_id_secondary"] = EDGE_SYSTEM_ID_SHT;
    systemOut["wifi_status"] = networkStatusCode();
    systemOut["wifi_connected"] = networkIsConnected();
    systemOut["rssi"] = networkSignalDbm();
    systemOut["transport"] = networkTransportName();
    systemOut["npk_alarm"] = npkAlarm;
    systemOut["sht_ready"] = sht30Service.ready();
    systemOut["firmware_version"] = currentFwVersion();
    systemOut["running_partition"] = currentFwPartition();
    systemOut["ts_device_ms"] = (int)millis();

    String out;
    serializeJson(outDoc, out);
    return out;
}

static String currentFwVersion() {
    return otaBootGuard.info().runningVersion.length() ? otaBootGuard.info().runningVersion : OtaBootGuard::currentRunningVersion();
}

static String currentFwPartition() {
    return otaBootGuard.info().runningPartition.length() ? otaBootGuard.info().runningPartition : OtaBootGuard::currentRunningPartition();
}

static OtaStoredEvent makeOtaEvent(const char* stage, const char* status, const String& detail,
                                   const String& version, const String& requestId) {
    OtaStoredEvent ev;
    ev.valid = true;
    ev.stage = stage;
    ev.status = status;
    ev.detail = detail;
    ev.version = version;
    ev.requestId = requestId;
    return ev;
}

static bool reportOrStoreOtaEvent(const OtaStoredEvent& event) {
    if (!event.valid) {
        return true;
    }

    if (networkIsConnected() && Firebase.ready()) {
        if (otaReporter.reportEvent(firebaseOtaData, event, currentFwVersion(), currentFwPartition())) {
            return true;
        }
        CUS_DBGF("[OTA] report fail: %s\n", firebaseOtaData.errorReason().c_str());
    }

    return otaStateStore.savePendingEvent(event);
}

static void publishSystemStatus(const char* state, const char* detail) {
    nodeRuntimePublisher.publishSystemStatus(firebaseData, state, detail, utcEpochMsIfSynced());
}

static void publishNodeInfoIfDue(bool force = false) {
    nodeRuntimePublisher.publishNodeInfoIfDue(firebaseData,
                                              deviceContext,
                                              currentFwVersion(),
                                              force,
                                              utcEpochMsIfSynced());
}

static void initTimeSync() {
    // UTC+7 for Asia/Ho_Chi_Minh.
    configTzTime("ICT-7", "time.google.com", "pool.ntp.org", "time.cloudflare.com");
}

static void maintainTimeSync() {
    static uint32_t lastAttemptMs = 0;
    if (!networkIsConnected()) {
        return;
    }
    if (utcEpochMsIfSynced() > 0) {
        return;
    }
    if (millis() - lastAttemptMs < TIME_SYNC_RETRY_MS) {
        return;
    }

    lastAttemptMs = millis();
    CUS_DBGLN("[TIME] NTP chua sync, thu dong bo lai...");
    initTimeSync();
}

static uint64_t utcEpochMsIfSynced() {
    time_t now = time(nullptr);
    if (now < 1700000000) {
        return 0;
    }
    return static_cast<uint64_t>(now) * 1000ULL;
}

static void handleOtaCommandIfAny() {
    static uint32_t lastPollMs = 0;
    uint32_t now = millis();
    if (now - lastPollMs < OTA_POLL_INTERVAL_MS) {
        return;
    }
    lastPollMs = now;

    OtaCommand cmd;
    String err;
    if (!otaManager.fetchCommand(firebaseOtaData, RTDB_PATH_OTA_COMMAND, cmd, err)) {
        // Skip noisy logs for missing command path. Keep only debug-level visibility.
        CUS_DBGF("[OTA] Poll command fail: %s\n", err.c_str());
        return;
    }

    if (!cmd.enabled) {
        return;
    }

    String lastHandled = otaStateStore.loadLastHandledRequestId();
    if (!cmd.force && cmd.requestId == lastHandled) {
        CUS_DBGF("[OTA] Duplicate request ignored: %s\n", cmd.requestId.c_str());
        otaManager.disableCommand(firebaseOtaData, RTDB_PATH_OTA_COMMAND);
        return;
    }

    String runningVer = currentFwVersion();
    if (!cmd.force && cmd.version.length() > 0 && cmd.version == runningVer) {
        reportOrStoreOtaEvent(makeOtaEvent("command", "skipped", "same firmware version", cmd.version, cmd.requestId));
        otaStateStore.saveLastHandledRequestId(cmd.requestId);
        otaManager.disableCommand(firebaseOtaData, RTDB_PATH_OTA_COMMAND);
        return;
    }

    reportOrStoreOtaEvent(makeOtaEvent("download", "started", cmd.url, cmd.version, cmd.requestId));
    publishSystemStatus("ota_downloading", cmd.version.c_str());

    String targetPartition;
    String otaErr;
    
    if (!otaManager.performHttpOta(cmd, targetPartition, otaErr)) {
        reportOrStoreOtaEvent(makeOtaEvent("update", "failed", otaErr, cmd.version, cmd.requestId));
        otaStateStore.saveLastHandledRequestId(cmd.requestId);
        otaManager.disableCommand(firebaseOtaData, RTDB_PATH_OTA_COMMAND);
        publishSystemStatus("ota_failed", otaErr.c_str());
        return;
    }

    OtaPendingValidationInfo pending;
    pending.active = true;
    pending.requestId = cmd.requestId;
    pending.targetVersion = cmd.version;
    pending.targetPartition = targetPartition;
    pending.previousPartition = currentFwPartition();
    pending.bootCount = 0;
    otaStateStore.savePendingValidation(pending);
    otaStateStore.saveLastHandledRequestId(cmd.requestId);

    reportOrStoreOtaEvent(makeOtaEvent("reboot", "pending_validation", targetPartition, cmd.version, cmd.requestId));
    otaManager.disableCommand(firebaseOtaData, RTDB_PATH_OTA_COMMAND);
    publishSystemStatus("ota_rebooting", cmd.version.c_str());

    delay(1000);
    ESP.restart();
}

static void maybeConfirmOtaAfterHealthyWindow() {
    static bool confirmedThisBoot = false;
    static uint32_t healthySinceMs = 0;

    if (confirmedThisBoot || !otaBootGuard.isPendingValidation()) {
        return;
    }

    bool healthy = (networkIsConnected() && Firebase.ready());
    if (!healthy) {
        healthySinceMs = 0;
        return;
    }

    if (healthySinceMs == 0) {
        healthySinceMs = millis();
        return;
    }

    if (millis() - healthySinceMs < OTA_CONFIRM_HEALTH_MS) {
        return;
    }

    if (otaBootGuard.confirmPendingValidation(otaStateStore)) {
        confirmedThisBoot = true;
        otaReporter.flushPendingEvent(firebaseOtaData, otaStateStore, currentFwVersion(), currentFwPartition());
        publishSystemStatus("ota_confirmed", currentFwVersion().c_str());
    }
}

void TaskSensor(void *pvParameters) {
    (void)pvParameters;
    SerialNPK.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    npkSensor.begin(SerialNPK);
    sht30Service.tryInit();
    uint32_t lastSampleMs = 0;

    for (;;) {
        // Keep SHT30 in retry loop in case of wiring/noise/power glitches.
        if (!sht30Service.ready()) {
            sht30Service.tryInit();
        }

        uint32_t sampleStartMs = millis();
        uint32_t sampleIntervalMs = (lastSampleMs == 0) ? 0 : (sampleStartMs - lastSampleMs);
        lastSampleMs = sampleStartMs;

        NPK_Data data = npkSensor.read();
        SensorMessage npkMsg = {};

        bool recoveredAfterFail = false;
        uint32_t failStreakBeforeRecover = 0;
        bool sensorAlarm = false;

        if (data.readOk) {
            if (npkFailCount > 0) {
                recoveredAfterFail = true;
                failStreakBeforeRecover = (uint32_t)npkFailCount;
                CUS_DBGF("[SENSOR] Khoi phuc sau %d lan fail lien tiep.\n", npkFailCount);
            }
            npkFailCount = 0;
        } else {
            npkFailCount++;
            CUS_DBGF("[SENSOR] Read fail streak=%d code=%s(0x%02X)\n",
                     npkFailCount,
                     MyNPK::errorCodeToString(data.errorCodeRaw),
                     data.errorCodeRaw);

            // Auto-recover NPK UART session if repeated timeouts happen.
            if (npkFailCount > 0 && (npkFailCount % 5) == 0) {
                CUS_DBGLN("[SENSOR] Thu reset ket noi UART NPK do fail streak cao.");
                SerialNPK.end();
                delay(80);
                SerialNPK.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
                npkSensor.begin(SerialNPK);
                delay(50);
            }

            if (npkFailCount == NPK_MAX_FAIL) {
                sensorAlarm = true;
                CUS_DBGLN("[SENSOR] CANH BAO: Sensor fail lien tiep den nguong.");
            }
        }

        String jsonStr = npkSensor.makeJsonFromData(
            data,
            sampleIntervalMs,
            (uint32_t)npkFailCount,
            recoveredAfterFail,
            failStreakBeforeRecover,
            sensorAlarm
        );

        String combinedPayload = buildCombinedNodePacket(jsonStr, sensorAlarm);
        CUS_DBGF("[SENSOR] node packet size=%u bytes (buffer=%u)\n",
                 (unsigned)combinedPayload.length(),
                 (unsigned)sizeof(npkMsg.jsonPayload));
        if (combinedPayload.length() >= sizeof(npkMsg.jsonPayload)) {
            CUS_DBGF("[QUEUE] Payload qua lon (%u bytes), bo qua chu ky nay.\n",
                     (unsigned)combinedPayload.length());
            vTaskDelay(pdMS_TO_TICKS(SENSOR_SAMPLE_INTERVAL_MS));
            continue;
        }

        combinedPayload.toCharArray(npkMsg.jsonPayload, sizeof(npkMsg.jsonPayload));
        npkMsg.isError = sensorAlarm;
        setMessagePayloadKind(npkMsg, "node_packet_json");

        if (enqueueSensorMessage(npkMsg)) {
            if (data.readOk) {
                CUS_DBGLN("[SENSOR] Data OK -> Sent to Queue");
            } else {
                CUS_DBGLN("[SENSOR] Data FAIL -> Sent to Queue");
            }
        }

        vTaskDelay(pdMS_TO_TICKS(SENSOR_SAMPLE_INTERVAL_MS));
    }
}

void TaskNetwork(void *pvParameters) {
    (void)pvParameters;

    // GSM/Firebase operations can block for many seconds; avoid false WDT resets on this task.
    esp_task_wdt_delete(NULL);

    bool netOk = networkSetup();
    if (!netOk) {
        CUS_DBGLN("[NET] Khoi dong mang that bai, se tiep tuc retry trong loop.");
    }

    firebasePipeline.begin(firebaseConfig, firebaseAuth, firebaseData, firebaseOtaData);
    initTimeSync();
    setupStorage();
    gOfflineReplayPending = LittleFS.exists(OFFLINE_RAW_FILE);

    // Flush boot/rollback/pending events persisted before network became available.
    otaReporter.flushPendingEvent(firebaseOtaData, otaStateStore, currentFwVersion(), currentFwPartition());
    publishSystemStatus("boot", "network task started");
    publishNodeInfoIfDue(true);

    SensorMessage rcvMsg = {};

    for (;;) {
        networkMaintain();
        bool hasInternet = networkIsConnected();

        if (hasInternet && Firebase.ready()) {
            maintainTimeSync();
            firebasePipeline.probeTelemetryPathIfNeeded(firebaseData, utcEpochMsIfSynced());
            publishNodeInfoIfDue(false);
            otaReporter.flushPendingEvent(firebaseOtaData, otaStateStore, currentFwVersion(), currentFwPartition());
            maybeConfirmOtaAfterHealthyWindow();
            handleOtaCommandIfAny();
            firebasePipeline.replayOfflineIfAny(firebaseData, gOfflineReplayPending, utcEpochMsIfSynced());
        }

        if (xQueueReceive(dataQueue, &rcvMsg, pdMS_TO_TICKS(100)) == pdPASS) {
            CUS_DBGF("[NET] Nhan du lieu: %s\n", rcvMsg.jsonPayload);
            const char* payloadKind = strlen(rcvMsg.payloadKind) ? rcvMsg.payloadKind : "unknown_json";

            if (rcvMsg.isError) {
                CUS_DBGLN("[NET] Sensor alarm -> ghi system_status (stub cho SMS/notify)");
                firebasePipeline.pushPayload(firebaseData,
                                             rcvMsg.jsonPayload,
                                             true,
                                             "sensor_alarm_json",
                                             deviceContext,
                                             currentFwVersion(),
                                             currentFwPartition(),
                                             gOfflineReplayPending,
                                             utcEpochMsIfSynced());
                publishSystemStatus("sensor_alarm", rcvMsg.jsonPayload);
                continue;
            }

            CUS_DBG("[FIREBASE] Dang day RTDB... ");
            if (firebasePipeline.pushPayload(firebaseData,
                                             rcvMsg.jsonPayload,
                                             false,
                                             payloadKind,
                                             deviceContext,
                                             currentFwVersion(),
                                             currentFwPartition(),
                                             gOfflineReplayPending,
                                             utcEpochMsIfSynced())) {
                CUS_DBGLN("OK");
                publishSystemStatus("online", "rtdb write ok");
            } else {
                CUS_DBGLN("BUFFERED");
                publishSystemStatus(hasInternet ? "degraded" : "offline_buffering",
                                    hasInternet ? "rtdb write fail, buffered" : "offline -> buffered");
            }
        }

        vTaskDelay(pdMS_TO_TICKS(NETWORK_LOOP_DELAY_MS));
    }
}

void setup() {
#if DEBUG_MODE
    Serial.begin(115200);
    delay(1000);
    CUS_DBGLN("\n=== HE THONG IOT AGRI-FUSION KHOI DONG ===");
#endif

    deviceContext.begin();
    otaBootGuard.begin(otaStateStore, OTA_MAX_PENDING_BOOTS);

    dataQueue = xQueueCreate(10, sizeof(SensorMessage));
    if (dataQueue == NULL) {
        CUS_DBGLN("[SYS] LOI: Khong tao duoc Queue!");
        return;
    }

    xTaskCreatePinnedToCore(TaskSensor, "SensorTask", 8192, NULL, 1, &TaskSensor_Handle, 1);
    xTaskCreatePinnedToCore(TaskNetwork, "NetworkTask", 16384, NULL, 2, &TaskNetwork_Handle, 0);
}

void loop() {
    vTaskDelete(NULL);
}

