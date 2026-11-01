#include "AppRuntime.h"

#include <FS.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <cstring>
#include <esp_sleep.h>
#include <esp_task_wdt.h>
#include <time.h>

#include "Config.h"
#include "NetworkBridge.h"
#include "Storage.h"
#include "TransportStability.h"
#include <addons/TokenHelper.h>
#if USE_SIM_NETWORK
#include "SimA7680C.h"
#endif

#define APP_LOG_SYS(fmt, ...)    CUS_DBGF(APP_LOG_SYS_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_SENSOR(fmt, ...) CUS_DBGF(APP_LOG_SENSOR_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_NET(fmt, ...)    CUS_DBGF(APP_LOG_NET_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_CLOUD(fmt, ...)  CUS_DBGF(APP_LOG_CLOUD_TAG " " fmt, ##__VA_ARGS__)
#define APP_LOG_OTA(fmt, ...)    CUS_DBGF(APP_LOG_OTA_TAG " " fmt, ##__VA_ARGS__)

namespace {
String buildUploadDiagSummary(bool firebaseReady) {
#if USE_SIM_NETWORK
    SimNetworkState sim = simReadNetworkState(false);
    char buf[256];
    snprintf(buf,
             sizeof(buf),
             "net=%d fb=%d reg=%d attach=%d gprs=%d ip=%s rssi=%d op=%s",
             networkIsConnected() ? 1 : 0,
             firebaseReady ? 1 : 0,
             sim.networkRegistered ? 1 : 0,
             sim.packetAttached ? 1 : 0,
             sim.gprsConnected ? 1 : 0,
             sim.localIp.c_str(),
             sim.signalDbm,
             sim.operatorName.c_str());
    return String(buf);
#else
    char buf[160];
    snprintf(buf,
             sizeof(buf),
             "net=%d fb=%d status=%d ip=%s rssi=%d",
             networkIsConnected() ? 1 : 0,
             firebaseReady ? 1 : 0,
             networkStatusCode(),
             networkLocalIp().c_str(),
             networkSignalDbm());
    return String(buf);
#endif
}

String buildReplayDiagSummary(const OfflineReplayResult &result) {
    char buf[192];
    snprintf(buf,
             sizeof(buf),
             "stage=%s replayed=%lu failed=%lu invalid=%lu remain=%d",
             result.stage.c_str(),
             (unsigned long)result.replayedCount,
             (unsigned long)result.failedCount,
             (unsigned long)result.invalidJsonCount,
             result.hasRemaining ? 1 : 0);
    return String(buf);
}

bool isReplayResultInteresting(const OfflineReplayResult &result) {
    return result.replayedCount > 0 ||
           result.failedCount > 0 ||
           result.invalidJsonCount > 0 ||
           result.stage == "replay_open_fail" ||
           result.stage == "replay_rewrite_fail" ||
           result.stage == "replay_cleanup_fail" ||
           result.stage == "replay_partial_fail";
}

String buildFirebaseAuthDiagSummary() {
#if USE_SIM_NETWORK && APP_FIREBASE_SIM_TRANSPORT_ENABLED
    return "custom_sim_rest_transport";
#else
    token_info_t info = Firebase.authTokenInfo();
    char buf[320];
    snprintf(buf,
             sizeof(buf),
             "type=%s(%d) status=%s(%d) err_code=%d err=%s",
             getTokenType(info),
             (int)info.type,
             getTokenStatus(info),
             (int)info.status,
             info.error.code,
             info.error.message.c_str());
    return String(buf);
#endif
}
}  // namespace

AppRuntime::AppRuntime()
    : _rawTelemetryReporter(APP_RTDB_PATH_NODE_ROOT),
      _otaReporter(APP_RTDB_PATH_OTA_STATUS, APP_RTDB_PATH_OTA_HISTORY),
      _nodeRuntimePublisher(makeNodeRuntimeConfig()),
      _firebasePipeline(makeFirebasePipelineConfig(), _rawTelemetryReporter, _nodeRuntimePublisher),
      _sht30Service(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, APP_SHT30_RETRY_INIT_MS),
      _packetBuilder(_sht30Service),
      _serialNpk(1) {}

NodeRuntimeConfig AppRuntime::makeNodeRuntimeConfig() {
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

FirebasePipelineConfig AppRuntime::makeFirebasePipelineConfig() {
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

void AppRuntime::begin() {
    APP_LOG_SYS("Khoi dong node %s, mode=%s, chu ky=%lu giay.\n",
                APP_NODE_ID,
                APP_RUN_CONTINUOUS ? "continuous" : "sleep",
                (unsigned long)(APP_SENSOR_SAMPLE_INTERVAL_MS / 1000UL));

    initTimeSync();
    _deviceContext.begin();
    _otaBootGuard.begin(_otaStateStore, APP_OTA_MAX_PENDING_BOOTS);

    if (!APP_RUN_CONTINUOUS) {
        runSleepCycle();
        return;
    }

    _dataQueue = xQueueCreate(APP_QUEUE_LENGTH, sizeof(SensorMessage));
    if (_dataQueue == NULL) {
        APP_LOG_SYS("Khong tao duoc data queue.\n");
        return;
    }

    xTaskCreatePinnedToCore(sensorTaskEntry,
                            "SensorTask",
                            APP_SENSOR_TASK_STACK_SIZE,
                            this,
                            APP_SENSOR_TASK_PRIORITY,
                            &_taskSensorHandle,
                            APP_SENSOR_TASK_CORE);

    xTaskCreatePinnedToCore(networkTaskEntry,
                            "NetworkTask",
                            APP_NETWORK_TASK_STACK_SIZE,
                            this,
                            APP_NETWORK_TASK_PRIORITY,
                            &_taskNetworkHandle,
                            APP_NETWORK_TASK_CORE);
}

void AppRuntime::runSleepCycle() {
    APP_LOG_SYS("Bat dau phien wake cycle, retry SIM=%u lan moi %lu giay.\n",
                (unsigned)APP_SIM_READY_MAX_POLLS,
                (unsigned long)(APP_SIM_READY_RETRY_INTERVAL_MS / 1000UL));

    initTimeSync();
    setupStorage();
    _offlineReplayPending = storageFileExists(APP_OFFLINE_RAW_FILE);

    String payload;
    bool sensorAlarm = false;
    if (!collectSingleSample(payload, sensorAlarm)) {
        APP_LOG_SENSOR("Khong tao duoc mau hop le, ngu va thu lai sau.\n");
        enterTimedDeepSleep(APP_SLEEP_FAIL_RETRY_INTERVAL_MS, "sample_fail");
        return;
    }

    bool cloudReady = waitForCloudReadyWindow();
    bool hasInternet = networkIsConnected();
    bool firebaseReady = _firebaseClientInitialized ? _firebasePipeline.ready() : false;
    logConnectivityTransitions(hasInternet, firebaseReady);

    if (cloudReady) {
        publishSystemStatusCached("boot", "wake cycle network ready", true);
        publishNodeInfoIfDue(true);

        if (_offlineReplayPending) {
            OfflineReplayResult replay = _firebasePipeline.replayOfflineIfAnyDetailed(_firebaseData,
                                                                                      _offlineReplayPending,
                                                                                      utcEpochMsIfSynced());
            _replayInvalidJsonCount += replay.invalidJsonCount;
            if (isReplayResultInteresting(replay)) {
                APP_LOG_CLOUD("Replay offline: %s detail=%s\n",
                              buildReplayDiagSummary(replay).c_str(),
                              replay.detail.c_str());
            }
        }

        uint32_t uploadStartMs = millis();
        TelemetryPushResult result = _firebasePipeline.pushPayloadDetailed(_firebaseData,
                                                                           payload.c_str(),
                                                                           sensorAlarm,
                                                                           sensorAlarm ? APP_PAYLOAD_KIND_SENSOR_ALARM : APP_PAYLOAD_KIND_NODE_PACKET,
                                                                           _deviceContext,
                                                                           currentFwVersion(),
                                                                           currentFwPartition(),
                                                                           _offlineReplayPending,
                                                                           utcEpochMsIfSynced());
        uint32_t uploadElapsedMs = millis() - uploadStartMs;

        if (result.uploaded) {
            APP_LOG_CLOUD("Wake upload OK in %lu ms ref=%s.\n",
                          (unsigned long)uploadElapsedMs,
                          result.refId.c_str());
            publishSystemStatusCached(sensorAlarm ? "sensor_alarm" : "online",
                                      sensorAlarm ? "wake upload sensor alarm" : "wake upload ok",
                                      true);
            enterTimedDeepSleep(APP_SENSOR_SAMPLE_INTERVAL_MS, "cycle_done");
            return;
        }

        APP_LOG_CLOUD("Wake upload buffered: stage=%s detail=%s elapsed=%lu ms state={%s}\n",
                      result.stage.c_str(),
                      result.detail.c_str(),
                      (unsigned long)uploadElapsedMs,
                      result.pipelineState.c_str());
        enterTimedDeepSleep(APP_SLEEP_FAIL_RETRY_INTERVAL_MS, "upload_buffered");
        return;
    }

    annotatePayloadSendState(payload, "sim_not_ready_timeout", APP_SIM_READY_MAX_POLLS);
    TelemetryPushResult buffered = _firebasePipeline.pushPayloadDetailed(_firebaseData,
                                                                         payload.c_str(),
                                                                         sensorAlarm,
                                                                         sensorAlarm ? APP_PAYLOAD_KIND_SENSOR_ALARM : APP_PAYLOAD_KIND_NODE_PACKET,
                                                                         _deviceContext,
                                                                         currentFwVersion(),
                                                                         currentFwPartition(),
                                                                         _offlineReplayPending,
                                                                         utcEpochMsIfSynced());
    if (!buffered.bufferStoreOk) {
        APP_LOG_CLOUD("Khong luu duoc packet fail-window vao backlog: stage=%s detail=%s\n",
                      buffered.stage.c_str(),
                      buffered.detail.c_str());
    } else {
        APP_LOG_CLOUD("SIM/cloud chua san sang sau cua so retry, packet da duoc dem lai. stage=%s detail=%s\n",
                      buffered.stage.c_str(),
                      buffered.detail.c_str());
    }
    enterTimedDeepSleep(APP_SLEEP_FAIL_RETRY_INTERVAL_MS, "sim_retry_timeout");
}

void AppRuntime::sensorTaskEntry(void *ctx) {
    static_cast<AppRuntime *>(ctx)->sensorTaskLoop();
}

void AppRuntime::networkTaskEntry(void *ctx) {
    static_cast<AppRuntime *>(ctx)->networkTaskLoop();
}

bool AppRuntime::enqueueSensorMessage(const SensorMessage &msg, TickType_t waitTicks) {
    if (xQueueSend(_dataQueue, &msg, waitTicks) == pdPASS) {
        return true;
    }

#if APP_QUEUE_REPLACE_OLDEST_ON_FULL
    SensorMessage droppedMsg = {};
    if (xQueueReceive(_dataQueue, &droppedMsg, 0) == pdPASS &&
        xQueueSend(_dataQueue, &msg, 0) == pdPASS) {
        _queueReplaceCount++;
        APP_LOG_SENSOR("Queue day, da bo ban tin cu nhat de giu mau moi. replaces=%lu waiting=%lu spaces=%lu\n",
                       (unsigned long)_queueReplaceCount,
                       (unsigned long)uxQueueMessagesWaiting(_dataQueue),
                       (unsigned long)uxQueueSpacesAvailable(_dataQueue));
        return true;
    }
#endif

    _queueDropCount++;
    APP_LOG_SENSOR("Queue day, bo mat ban tin hien tai. drops=%lu waiting=%lu spaces=%lu\n",
                   (unsigned long)_queueDropCount,
                   (unsigned long)uxQueueMessagesWaiting(_dataQueue),
                   (unsigned long)uxQueueSpacesAvailable(_dataQueue));
    return false;
}

void AppRuntime::setMessagePayloadKind(SensorMessage &msg, const char *kind) {
    msg.payloadKind[0] = '\0';
    if (!kind) {
        return;
    }
    strncpy(msg.payloadKind, kind, sizeof(msg.payloadKind) - 1);
    msg.payloadKind[sizeof(msg.payloadKind) - 1] = '\0';
}

String AppRuntime::currentFwVersion() const {
    return _otaBootGuard.info().runningVersion.length()
               ? _otaBootGuard.info().runningVersion
               : OtaBootGuard::currentRunningVersion();
}

String AppRuntime::currentFwPartition() const {
    return _otaBootGuard.info().runningPartition.length()
               ? _otaBootGuard.info().runningPartition
               : OtaBootGuard::currentRunningPartition();
}

bool AppRuntime::collectSingleSample(String &payloadOut, bool &sensorAlarmOut) {
    payloadOut = "";
    sensorAlarmOut = false;

    _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    _npkSensor.begin(_serialNpk);

    APP_LOG_SENSOR("Bat dau chu ky do wake-once.\n");
    uint32_t sampleStartMs = millis();
    auto parseShtState = [](const String &json, bool &readOk, bool &sampleValid, String &errorText) {
        readOk = false;
        sampleValid = false;
        errorText = "json_parse_fail";

        JsonDocument doc;
        if (deserializeJson(doc, json) != DeserializationError::Ok) {
            return;
        }

        readOk = doc["sht_read_ok"] | false;
        sampleValid = doc["sht_sample_valid"] | false;
        errorText = doc["sht_error"] | "unknown";
    };

    NPK_Data data = {};
    bool npkRecoveredInsideWindow = false;
    uint32_t npkFailBeforeRecover = 0;
    for (uint32_t attempt = 1; attempt <= (uint32_t)APP_SENSOR_RETRY_WINDOW_COUNT; ++attempt) {
        data = _npkSensor.read();
        if (data.readOk) {
            if (attempt > 1) {
                npkRecoveredInsideWindow = true;
                npkFailBeforeRecover = attempt - 1;
                APP_LOG_SENSOR("NPK phuc hoi trong cua so retry tai lan %lu/%u.\n",
                               (unsigned long)attempt,
                               (unsigned)APP_SENSOR_RETRY_WINDOW_COUNT);
            }
            break;
        }

        APP_LOG_SENSOR("NPK mat ket noi/loi, retry %lu/%u sau cua so %lu ms. code=%s(0x%02X)\n",
                       (unsigned long)attempt,
                       (unsigned)APP_SENSOR_RETRY_WINDOW_COUNT,
                       (unsigned long)APP_SENSOR_RETRY_WINDOW_MS,
                       MyNPK::errorCodeToString(data.errorCodeRaw),
                       data.errorCodeRaw);

        if ((_npkFailCount + (int)attempt) > 0 &&
            (((_npkFailCount + (int)attempt) % APP_NPK_UART_RESET_FAIL_INTERVAL) == 0)) {
            APP_LOG_SENSOR("Reset lai UART NPK trong cua so retry.\n");
            _serialNpk.end();
            delay(80);
            _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
            _npkSensor.begin(_serialNpk);
            delay(50);
        }

        if (attempt < (uint32_t)APP_SENSOR_RETRY_WINDOW_COUNT) {
            delay(APP_SENSOR_RETRY_WINDOW_MS);
        }
    }

    String shtJson;
    bool shtReadOk = false;
    bool shtSampleValid = false;
    String shtError = "not_started";
    for (uint32_t attempt = 1; attempt <= (uint32_t)APP_SENSOR_RETRY_WINDOW_COUNT; ++attempt) {
        if (!_sht30Service.ready()) {
            APP_LOG_SENSOR("SHT30 chua ready, thu init lai trong cua so retry %lu/%u.\n",
                           (unsigned long)attempt,
                           (unsigned)APP_SENSOR_RETRY_WINDOW_COUNT);
            _sht30Service.tryInit(attempt == 1);
        }

        shtJson = _sht30Service.buildJsonPayload("sht30_air",
                                                 "sht30_1",
                                                 APP_EDGE_SYSTEM_SHT,
                                                 APP_EDGE_SYSTEM_ID_SHT,
                                                 "sht30",
                                                 SHT30_READ_MAX_ATTEMPTS,
                                                 SHT30_RETRY_DELAY_MS,
                                                 SHT30_MAX_WAIT_MS);
        parseShtState(shtJson, shtReadOk, shtSampleValid, shtError);
        if (shtSampleValid) {
            if (attempt > 1) {
                APP_LOG_SENSOR("SHT30 phuc hoi trong cua so retry tai lan %lu/%u.\n",
                               (unsigned long)attempt,
                               (unsigned)APP_SENSOR_RETRY_WINDOW_COUNT);
            }
            break;
        }

        APP_LOG_SENSOR("SHT30 chua on dinh, retry %lu/%u sau cua so %lu ms. read_ok=%d err=%s\n",
                       (unsigned long)attempt,
                       (unsigned)APP_SENSOR_RETRY_WINDOW_COUNT,
                       (unsigned long)APP_SENSOR_RETRY_WINDOW_MS,
                       shtReadOk ? 1 : 0,
                       shtError.c_str());

        if (attempt < (uint32_t)APP_SENSOR_RETRY_WINDOW_COUNT) {
            delay(APP_SENSOR_RETRY_WINDOW_MS);
        }
    }

    bool recoveredAfterFail = false;
    uint32_t failStreakBeforeRecover = 0;
    bool sensorAlarm = false;

    if (data.readOk) {
        if (_npkFailCount > 0) {
            recoveredAfterFail = true;
            failStreakBeforeRecover = (uint32_t)_npkFailCount;
            APP_LOG_SENSOR("NPK phuc hoi sau %d lan fail lien tiep.\n", _npkFailCount);
        } else if (npkRecoveredInsideWindow) {
            recoveredAfterFail = true;
            failStreakBeforeRecover = npkFailBeforeRecover;
        }
        _npkFailCount = 0;
    } else {
        _npkFailCount++;
        APP_LOG_SENSOR("NPK fail streak=%d code=%s(0x%02X)\n",
                       _npkFailCount,
                       MyNPK::errorCodeToString(data.errorCodeRaw),
                       data.errorCodeRaw);

        if (_npkFailCount > 0 && (_npkFailCount % APP_NPK_UART_RESET_FAIL_INTERVAL) == 0) {
            APP_LOG_SENSOR("Reset lai UART NPK do fail streak cao.\n");
            _serialNpk.end();
            delay(80);
            _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
            _npkSensor.begin(_serialNpk);
            delay(50);
        }

        if (_npkFailCount >= APP_NPK_FAIL_ALARM_THRESHOLD) {
            sensorAlarm = true;
            APP_LOG_SENSOR("Canh bao NPK fail den nguong alarm.\n");
        }
    }

    String npkJson = _npkSensor.makeJsonFromData(data,
                                                 APP_SENSOR_SAMPLE_INTERVAL_MS,
                                                 (uint32_t)_npkFailCount,
                                                 recoveredAfterFail,
                                                 failStreakBeforeRecover,
                                                 sensorAlarm);

    payloadOut = _packetBuilder.buildCombinedNodePacket(npkJson,
                                                        shtJson,
                                                        sensorAlarm,
                                                        currentFwVersion(),
                                                        currentFwPartition());
    APP_LOG_SENSOR("Packet size=%u bytes, read_elapsed=%lu ms.\n",
                   (unsigned)payloadOut.length(),
                   (unsigned long)(millis() - sampleStartMs));

    if (payloadOut.isEmpty()) {
        return false;
    }

    if (payloadOut.length() >= APP_SENSOR_PAYLOAD_BUFFER_SIZE) {
        _payloadOversizeCount++;
        APP_LOG_SENSOR("Canh bao: payload=%u bytes vuot moc cu=%u, nhung van tiep tuc vi sleep-mode gui truc tiep.\n",
                       (unsigned)payloadOut.length(),
                       (unsigned)APP_SENSOR_PAYLOAD_BUFFER_SIZE);
    }

    sensorAlarmOut = sensorAlarm;
    return true;
}

bool AppRuntime::annotatePayloadSendState(String &payload, const char *state, uint32_t attempts) const {
    if (!payload.length()) {
        return false;
    }

    JsonDocument doc;
    if (deserializeJson(doc, payload) != DeserializationError::Ok) {
        return false;
    }

    JsonObject packet = doc["packet"].to<JsonObject>();
    JsonObject system = packet["system_data"].to<JsonObject>();
    system["send_state"] = state ? state : "unknown";
    system["send_attempts"] = (int)attempts;
    system["send_retry_interval_ms"] = (int)APP_SIM_READY_RETRY_INTERVAL_MS;
    system["send_retry_max_polls"] = (int)APP_SIM_READY_MAX_POLLS;
    system["send_window_ms"] = (int)(APP_SIM_READY_RETRY_INTERVAL_MS * APP_SIM_READY_MAX_POLLS);

    payload = "";
    serializeJson(doc, payload);
    return true;
}

bool AppRuntime::waitForCloudReadyWindow() {
    bool netOk = networkSetup();
    if (!netOk) {
        APP_LOG_NET("Khoi dong mang lan dau chua thanh cong, se vao cua so retry.\n");
    }

    initTimeSync();
    for (uint32_t poll = 1; poll <= (uint32_t)APP_SIM_READY_MAX_POLLS; ++poll) {
        networkMaintain();
        bool hasInternet = networkIsConnected();
        APP_LOG_NET("Wake retry %lu/%u: net=%d diag={%s}\n",
                    (unsigned long)poll,
                    (unsigned)APP_SIM_READY_MAX_POLLS,
                    hasInternet ? 1 : 0,
                    buildUploadDiagSummary(false).c_str());

        bool transportReady = ensureCloudTransportReady(hasInternet, "wake_retry_window", poll == 1);
        if (transportReady) {
            beginFirebaseClientIfNeeded(hasInternet, !_firebaseClientInitialized, "wake_retry_window");
            bool firebaseReady = _firebaseClientInitialized ? _firebasePipeline.ready() : false;
            if (firebaseReady) {
                APP_LOG_NET("Cloud ready trong cua so retry tai lan %lu.\n", (unsigned long)poll);
                return true;
            }
        }

        if (poll < (uint32_t)APP_SIM_READY_MAX_POLLS) {
            APP_LOG_NET("Cloud chua san sang, cho %lu giay roi hoi lai.\n",
                        (unsigned long)(APP_SIM_READY_RETRY_INTERVAL_MS / 1000UL));
            delay(APP_SIM_READY_RETRY_INTERVAL_MS);
        }
    }

    return false;
}

void AppRuntime::enterTimedDeepSleep(uint32_t sleepMs, const char *reason) const {
    APP_LOG_SYS("Ket thuc phien wake, vao deep sleep %lu giay. reason=%s\n",
                (unsigned long)(sleepMs / 1000UL),
                reason ? reason : "na");
    DEBUG_PORT.flush();
    delay(100);
    esp_sleep_enable_timer_wakeup((uint64_t)sleepMs * 1000ULL);
    esp_deep_sleep_start();
}

void AppRuntime::initTimeSync() const {
    configTzTime(APP_NODE_TZ_CONFIG, "time.google.com", "pool.ntp.org", "time.cloudflare.com");
}

void AppRuntime::maintainTimeSync() {
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

uint64_t AppRuntime::utcEpochMsIfSynced() {
    time_t now = time(nullptr);
    if (now < 1700000000) {
        return 0;
    }
    return static_cast<uint64_t>(now) * 1000ULL;
}

void AppRuntime::publishNodeInfoIfDue(bool force) {
    _nodeRuntimePublisher.publishNodeInfoIfDue(_firebaseData,
                                               _deviceContext,
                                               currentFwVersion(),
                                               force,
                                               utcEpochMsIfSynced());
}

void AppRuntime::publishSystemStatusCached(const char *state, const char *detail, bool force) {
    String nextState = state ? state : "unknown";
    String nextDetail = detail ? detail : "";
    uint32_t now = millis();
    bool changed = (_statusCache.state != nextState) || (_statusCache.detail != nextDetail);
    bool refreshDue = (now - _statusCache.lastPublishMs) >= APP_STATUS_REFRESH_INTERVAL_MS;

    if (!force && !changed && !refreshDue) {
        return;
    }

    _nodeRuntimePublisher.publishSystemStatus(_firebaseData, state, detail, utcEpochMsIfSynced());
    _statusCache.state = nextState;
    _statusCache.detail = nextDetail;
    _statusCache.lastPublishMs = now;
}

void AppRuntime::logConnectivityTransitions(bool hasInternet, bool firebaseReady) {
    if (!_haveConnectivitySnapshot ||
        _lastNetworkConnected != hasInternet ||
        _lastFirebaseReady != firebaseReady) {
        APP_LOG_NET("State change: net=%d->%d fb=%d->%d diag={%s}\n",
                    _haveConnectivitySnapshot ? (_lastNetworkConnected ? 1 : 0) : -1,
                    hasInternet ? 1 : 0,
                    _haveConnectivitySnapshot ? (_lastFirebaseReady ? 1 : 0) : -1,
                    firebaseReady ? 1 : 0,
                    buildUploadDiagSummary(firebaseReady).c_str());
        _lastNetworkConnected = hasInternet;
        _lastFirebaseReady = firebaseReady;
        _haveConnectivitySnapshot = true;
    }
}

void AppRuntime::maybeLogRuntimeDiagnostics(bool hasInternet, bool firebaseReady) {
    uint32_t now = millis();
    if (now - _lastDiagLogMs < APP_RUNTIME_DIAG_INTERVAL_MS) {
        return;
    }
    _lastDiagLogMs = now;

    APP_LOG_SYS("Heartbeat: uptime=%lus net=%d fb=%d fb_init=%d fb_begin=%lu queue_wait=%lu queue_free=%lu offline=%d drops=%lu oversize=%lu buffer_fail=%lu replay_issue=%lu invalid_offline=%lu diag={%s}\n",
                (unsigned long)(millis() / 1000UL),
                hasInternet ? 1 : 0,
                firebaseReady ? 1 : 0,
                _firebaseClientInitialized ? 1 : 0,
                (unsigned long)_firebaseBeginCount,
                (unsigned long)uxQueueMessagesWaiting(_dataQueue),
                (unsigned long)uxQueueSpacesAvailable(_dataQueue),
                _offlineReplayPending ? 1 : 0,
                (unsigned long)_queueDropCount,
                (unsigned long)_payloadOversizeCount,
                (unsigned long)_bufferStoreFailCount,
                (unsigned long)_replayIssueCount,
                (unsigned long)_replayInvalidJsonCount,
                buildUploadDiagSummary(firebaseReady).c_str());

    if (_firebaseClientInitialized && _firebasePipeline.usesNativeFirebase()) {
        APP_LOG_CLOUD("Heartbeat auth={%s}\n", buildFirebaseAuthDiagSummary().c_str());
    }
}

bool AppRuntime::ensureCloudTransportReady(bool hasInternet, const char *reason, bool verboseLog) {
#if USE_SIM_NETWORK
    if (!hasInternet) {
        _lastCloudTransportReady = false;
        return false;
    }

    uint32_t now = millis();
    bool timeReadyBefore = utcEpochMsIfSynced() > 0;
    bool firebaseReadyBefore = _firebaseClientInitialized && _firebasePipeline.ready();
    if (firebaseReadyBefore && !verboseLog) {
        return true;
    }

    uint32_t &gateMs = verboseLog ? _lastTransportDiagMs : _lastTransportBootstrapMs;
    uint32_t minInterval = verboseLog ? APP_TRANSPORT_DIAG_INTERVAL_MS : APP_TRANSPORT_BOOTSTRAP_INTERVAL_MS;
    if (gateMs > 0 && (now - gateMs) < minInterval) {
        return _lastCloudTransportReady;
    }
    gateMs = now;

    APP_LOG_NET("Transport bootstrap reason=%s time_ready_before=%d\n",
                reason ? reason : "na",
                timeReadyBefore ? 1 : 0);

    CloudTransportReport report = runCloudTransportCycle();
    APP_LOG_NET("Transport bootstrap result transport_ready=%d time_ready=%d http_ok=%d stage=%s\n",
                report.transportUsable ? 1 : 0,
                report.timeReadyAfter ? 1 : 0,
                report.httpProbe.ok ? 1 : 0,
                report.stage.c_str());

    if (verboseLog || !report.transportUsable || !report.timeReadyAfter) {
        printCloudTransportReport(report);
    }

    _lastCloudTransportReady = report.transportUsable;
    return report.transportUsable;
#else
    (void)hasInternet;
    (void)reason;
    (void)verboseLog;
    return true;
#endif
}

bool AppRuntime::beginFirebaseClientIfNeeded(bool hasInternet, bool networkJustRecovered, const char *reasonHint) {
    if (!hasInternet) {
        return false;
    }

    uint32_t now = millis();
    bool cooldownPassed = (now - _lastFirebaseBeginMs) >= APP_FIREBASE_REBEGIN_INTERVAL_MS;
    bool firstBoot = !_firebaseClientInitialized;
    bool stuckNotReady = _firebaseClientInitialized &&
                         _firebaseNotReadySinceMs > 0 &&
                         cooldownPassed &&
                         (now - _firebaseNotReadySinceMs) >= APP_FIREBASE_REBEGIN_INTERVAL_MS;

    if (!firstBoot && !networkJustRecovered && !stuckNotReady) {
        return false;
    }

    if (!firstBoot && !cooldownPassed && !networkJustRecovered) {
        return false;
    }

    if (!ensureCloudTransportReady(hasInternet, "before_firebase_begin", false)) {
        APP_LOG_CLOUD("Hoan Firebase begin vi cloud prerequisites chua san sang.\n");
        return false;
    }

    const char *reason = reasonHint ? reasonHint : "runtime";
    if (firstBoot) {
        reason = "boot_network_ready";
    } else if (networkJustRecovered) {
        reason = "network_recovered";
    } else if (stuckNotReady) {
        reason = "firebase_stuck_not_ready";
    }

    _firebaseBeginCount++;
    _lastFirebaseBeginMs = now;
    _lastFirebaseNotReadyLogMs = 0;
    APP_LOG_CLOUD("Firebase begin attempt=%lu reason=%s diag={%s}\n",
                  (unsigned long)_firebaseBeginCount,
                  reason,
                  buildUploadDiagSummary(false).c_str());

    FirebaseBootstrapResult bootstrap = _firebasePipeline.begin(_firebaseConfig,
                                                                _firebaseAuth,
                                                                _firebaseData,
                                                                _firebaseOtaData);
    _firebaseClientInitialized = bootstrap.transportConfigured && bootstrap.beginAttempted;

    if (!_firebasePipeline.configLooksValid()) {
        APP_LOG_CLOUD("Firebase config co van de: database_url khong dung dinh dang RTDB.\n");
    }

    APP_LOG_CLOUD("Firebase bootstrap: %s\n", bootstrap.authSummary.c_str());
    APP_LOG_CLOUD("Firebase auth after begin: %s\n", buildFirebaseAuthDiagSummary().c_str());
    APP_LOG_CLOUD("Firebase probe after begin: ready=%d %s state={%s}\n",
                  bootstrap.readyAfterBegin ? 1 : 0,
                  bootstrap.probe.detail.c_str(),
                  _firebasePipeline.stateSummary().c_str());

    if (!bootstrap.transportConfigured) {
        APP_LOG_CLOUD("Firebase begin bi chan: %s\n", bootstrap.probe.detail.c_str());
        return false;
    }
    return true;
}

void AppRuntime::maybeLogFirebaseNotReady(bool hasInternet, bool firebaseReady) {
    if (!hasInternet || !_firebaseClientInitialized || firebaseReady) {
        if (firebaseReady) {
            _firebaseNotReadySinceMs = 0;
        }
        return;
    }

    uint32_t now = millis();
    if (_firebaseNotReadySinceMs == 0) {
        _firebaseNotReadySinceMs = now;
    }

    if (_lastFirebaseNotReadyLogMs > 0 &&
        (now - _lastFirebaseNotReadyLogMs) < APP_FIREBASE_NOT_READY_LOG_MS) {
        return;
    }

    _lastFirebaseNotReadyLogMs = now;
    const char *phase = _firebaseEverReady ? "runtime" : "startup";
    FirebaseProbeResult probe = _firebasePipeline.probeDatabaseAccess(_firebaseData);
    APP_LOG_CLOUD("Firebase not ready phase=%s elapsed=%lu ms auth={%s} probe={%s} state={%s} diag={%s}\n",
                  phase,
                  (unsigned long)(now - _firebaseNotReadySinceMs),
                  buildFirebaseAuthDiagSummary().c_str(),
                  probe.detail.c_str(),
                  _firebasePipeline.stateSummary().c_str(),
                  buildUploadDiagSummary(false).c_str());

    ensureCloudTransportReady(hasInternet, "firebase_not_ready_diag", true);
}

OtaStoredEvent AppRuntime::makeOtaEvent(const char *stage,
                                        const char *status,
                                        const String &detail,
                                        const String &version,
                                        const String &requestId) const {
    OtaStoredEvent ev;
    ev.valid = true;
    ev.stage = stage;
    ev.status = status;
    ev.detail = detail;
    ev.version = version;
    ev.requestId = requestId;
    return ev;
}

bool AppRuntime::reportOrStoreOtaEvent(const OtaStoredEvent &event) {
    if (!event.valid) {
        return true;
    }

    if (_firebasePipeline.usesNativeFirebase() && networkIsConnected() && Firebase.ready()) {
        if (_otaReporter.reportEvent(_firebaseOtaData, event, currentFwVersion(), currentFwPartition())) {
            return true;
        }
        APP_LOG_OTA("Report fail: %s\n", _firebaseOtaData.errorReason().c_str());
    }

    return _otaStateStore.savePendingEvent(event);
}

void AppRuntime::handleOtaCommandIfAny() {
    if (!_firebasePipeline.usesNativeFirebase()) {
        return;
    }
    static uint32_t lastPollMs = 0;
    uint32_t now = millis();
    if (now - lastPollMs < APP_OTA_POLL_INTERVAL_MS) {
        return;
    }
    lastPollMs = now;

    OtaCommand cmd;
    String err;
    if (!_otaManager.fetchCommand(_firebaseOtaData, APP_RTDB_PATH_OTA_COMMAND, cmd, err)) {
        APP_LOG_OTA("Poll command fail: %s\n", err.c_str());
        return;
    }

    if (!cmd.enabled) {
        return;
    }

    String lastHandled = _otaStateStore.loadLastHandledRequestId();
    if (!cmd.force && cmd.requestId == lastHandled) {
        APP_LOG_OTA("Duplicate request ignored: %s\n", cmd.requestId.c_str());
        _otaManager.disableCommand(_firebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
        return;
    }

    String runningVer = currentFwVersion();
    if (!cmd.force && cmd.version.length() > 0 && cmd.version == runningVer) {
        reportOrStoreOtaEvent(makeOtaEvent("command", "skipped", "same firmware version", cmd.version, cmd.requestId));
        _otaStateStore.saveLastHandledRequestId(cmd.requestId);
        _otaManager.disableCommand(_firebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
        return;
    }

    reportOrStoreOtaEvent(makeOtaEvent("download", "started", cmd.url, cmd.version, cmd.requestId));
    publishSystemStatusCached("ota_downloading", cmd.version.c_str(), true);

    String targetPartition;
    String otaErr;
    if (!_otaManager.performHttpOta(cmd, targetPartition, otaErr)) {
        reportOrStoreOtaEvent(makeOtaEvent("update", "failed", otaErr, cmd.version, cmd.requestId));
        _otaStateStore.saveLastHandledRequestId(cmd.requestId);
        _otaManager.disableCommand(_firebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
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
    _otaStateStore.savePendingValidation(pending);
    _otaStateStore.saveLastHandledRequestId(cmd.requestId);

    reportOrStoreOtaEvent(makeOtaEvent("reboot", "pending_validation", targetPartition, cmd.version, cmd.requestId));
    _otaManager.disableCommand(_firebaseOtaData, APP_RTDB_PATH_OTA_COMMAND);
    publishSystemStatusCached("ota_rebooting", cmd.version.c_str(), true);

    delay(1000);
    ESP.restart();
}

void AppRuntime::maybeConfirmOtaAfterHealthyWindow() {
    if (!_firebasePipeline.usesNativeFirebase()) {
        return;
    }
    static bool confirmedThisBoot = false;
    static uint32_t healthySinceMs = 0;

    if (confirmedThisBoot || !_otaBootGuard.isPendingValidation()) {
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

    if (_otaBootGuard.confirmPendingValidation(_otaStateStore)) {
        confirmedThisBoot = true;
        _otaReporter.flushPendingEvent(_firebaseOtaData, _otaStateStore, currentFwVersion(), currentFwPartition());
        publishSystemStatusCached("ota_confirmed", currentFwVersion().c_str(), true);
    }
}

void AppRuntime::sensorTaskLoop() {
    _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    _npkSensor.begin(_serialNpk);
    _sht30Service.tryInit();

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

        if (!_sht30Service.ready()) {
            APP_LOG_SENSOR("SHT30 chua ready, thu init lai.\n");
            _sht30Service.tryInit();
        }

        uint32_t sampleStartMs = millis();
        uint32_t sampleIntervalMs = (lastSampleMs == 0) ? 0 : (sampleStartMs - lastSampleMs);
        lastSampleMs = sampleStartMs;

        APP_LOG_SENSOR("Bat dau chu ky do moi, elapsed=%lu ms.\n", (unsigned long)sampleIntervalMs);

        NPK_Data data = _npkSensor.read();
        SensorMessage npkMsg = {};

        bool recoveredAfterFail = false;
        uint32_t failStreakBeforeRecover = 0;
        bool sensorAlarm = false;

        if (data.readOk) {
            if (_npkFailCount > 0) {
                recoveredAfterFail = true;
                failStreakBeforeRecover = (uint32_t)_npkFailCount;
                APP_LOG_SENSOR("NPK phuc hoi sau %d lan fail lien tiep.\n", _npkFailCount);
            }
            _npkFailCount = 0;
        } else {
            _npkFailCount++;
            APP_LOG_SENSOR("NPK fail streak=%d code=%s(0x%02X)\n",
                           _npkFailCount,
                           MyNPK::errorCodeToString(data.errorCodeRaw),
                           data.errorCodeRaw);

            if (_npkFailCount > 0 && (_npkFailCount % APP_NPK_UART_RESET_FAIL_INTERVAL) == 0) {
                APP_LOG_SENSOR("Reset lai UART NPK do fail streak cao.\n");
                _serialNpk.end();
                delay(80);
                _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
                _npkSensor.begin(_serialNpk);
                delay(50);
            }

            if (_npkFailCount >= APP_NPK_FAIL_ALARM_THRESHOLD) {
                sensorAlarm = true;
                APP_LOG_SENSOR("Canh bao NPK fail den nguong alarm.\n");
            }
        }

        String npkJson = _npkSensor.makeJsonFromData(data,
                                                     sampleIntervalMs,
                                                     (uint32_t)_npkFailCount,
                                                     recoveredAfterFail,
                                                     failStreakBeforeRecover,
                                                     sensorAlarm);

        String combinedPayload = _packetBuilder.buildCombinedNodePacket(npkJson,
                                                                        sensorAlarm,
                                                                        currentFwVersion(),
                                                                        currentFwPartition());
        APP_LOG_SENSOR("Packet size=%u bytes.\n", (unsigned)combinedPayload.length());
        if (combinedPayload.length() >= sizeof(npkMsg.jsonPayload)) {
            _payloadOversizeCount++;
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

void AppRuntime::networkTaskLoop() {
    esp_task_wdt_delete(NULL);

    APP_LOG_NET("Task bat dau, mode=%s.\n", APP_RUN_CONTINUOUS ? "continuous" : "sleep");

    bool netOk = networkSetup();
    if (!netOk) {
        APP_LOG_NET("Khoi dong mang that bai, se retry trong loop.\n");
    }

    initTimeSync();
    setupStorage();
    _offlineReplayPending = storageFileExists(APP_OFFLINE_RAW_FILE);

    if (_firebasePipeline.usesNativeFirebase()) {
        _otaReporter.flushPendingEvent(_firebaseOtaData, _otaStateStore, currentFwVersion(), currentFwPartition());
    }

    SensorMessage rcvMsg = {};

    for (;;) {
        networkMaintain();
        bool hasInternet = networkIsConnected();
        bool networkJustRecovered = _haveConnectivitySnapshot && !_lastNetworkConnected && hasInternet;

        beginFirebaseClientIfNeeded(hasInternet, networkJustRecovered);

        bool firebaseReady = _firebaseClientInitialized ? _firebasePipeline.ready() : false;
        if (firebaseReady) {
            _firebaseEverReady = true;
            _firebaseNotReadySinceMs = 0;
        } else {
            maybeLogFirebaseNotReady(hasInternet, firebaseReady);
            beginFirebaseClientIfNeeded(hasInternet, false, "recheck_after_not_ready");
        }

        logConnectivityTransitions(hasInternet, firebaseReady);
        maybeLogRuntimeDiagnostics(hasInternet, firebaseReady);

        if (hasInternet && firebaseReady) {
            if (!_bootCloudSnapshotPublished) {
                publishSystemStatusCached("boot", "network task started", true);
                publishNodeInfoIfDue(true);
                _bootCloudSnapshotPublished = true;
            }
            maintainTimeSync();
            _firebasePipeline.probeTelemetryPathIfNeeded(_firebaseData, utcEpochMsIfSynced());
            publishNodeInfoIfDue(false);
            if (_firebasePipeline.usesNativeFirebase()) {
                _otaReporter.flushPendingEvent(_firebaseOtaData, _otaStateStore, currentFwVersion(), currentFwPartition());
                maybeConfirmOtaAfterHealthyWindow();
                handleOtaCommandIfAny();
            }
            OfflineReplayResult replay = _firebasePipeline.replayOfflineIfAnyDetailed(_firebaseData,
                                                                                      _offlineReplayPending,
                                                                                      utcEpochMsIfSynced());
            _replayInvalidJsonCount += replay.invalidJsonCount;
            if (isReplayResultInteresting(replay)) {
                if (replay.failedCount > 0 || !replay.rewriteOk || !replay.cleanupOk) {
                    _replayIssueCount++;
                }
                APP_LOG_CLOUD("Replay offline: %s detail=%s\n",
                              buildReplayDiagSummary(replay).c_str(),
                              replay.detail.c_str());
            }
        }

        if (xQueueReceive(_dataQueue, &rcvMsg, pdMS_TO_TICKS(APP_QUEUE_RECV_WAIT_MS)) == pdPASS) {
            const char *payloadKind = strlen(rcvMsg.payloadKind) ? rcvMsg.payloadKind : "unknown_json";
            APP_LOG_NET("Nhan payload kind=%s, error=%d.\n", payloadKind, rcvMsg.isError ? 1 : 0);

            if (rcvMsg.isError) {
                APP_LOG_CLOUD("Sensor alarm -> push telemetry fault + status.\n");
                uint32_t uploadStartMs = millis();
                TelemetryPushResult result = _firebasePipeline.pushPayloadDetailed(_firebaseData,
                                                                                   rcvMsg.jsonPayload,
                                                                                   true,
                                                                                   APP_PAYLOAD_KIND_SENSOR_ALARM,
                                                                                   _deviceContext,
                                                                                   currentFwVersion(),
                                                                                   currentFwPartition(),
                                                                                   _offlineReplayPending,
                                                                                   utcEpochMsIfSynced());
                uint32_t uploadElapsedMs = millis() - uploadStartMs;
                if (!result.uploaded) {
                    if (!result.bufferStoreOk) {
                        _bufferStoreFailCount++;
                    }
                    APP_LOG_CLOUD("Sensor alarm buffered: stage=%s detail=%s elapsed=%lu ms state={%s} diag={%s}\n",
                                  result.stage.c_str(),
                                  result.detail.c_str(),
                                  (unsigned long)uploadElapsedMs,
                                  result.pipelineState.c_str(),
                                  buildUploadDiagSummary(result.firebaseReady).c_str());
                } else {
                    APP_LOG_CLOUD("Sensor alarm upload OK in %lu ms.\n", (unsigned long)uploadElapsedMs);
                }
                publishSystemStatusCached("sensor_alarm", "sensor fault buffered or uploaded", true);
            } else {
                uint32_t uploadStartMs = millis();
                TelemetryPushResult result = _firebasePipeline.pushPayloadDetailed(_firebaseData,
                                                                                   rcvMsg.jsonPayload,
                                                                                   false,
                                                                                   payloadKind,
                                                                                   _deviceContext,
                                                                                   currentFwVersion(),
                                                                                   currentFwPartition(),
                                                                                   _offlineReplayPending,
                                                                                   utcEpochMsIfSynced());
                uint32_t uploadElapsedMs = millis() - uploadStartMs;
                if (result.uploaded) {
                    APP_LOG_CLOUD("Upload RTDB OK in %lu ms.\n", (unsigned long)uploadElapsedMs);
                    publishSystemStatusCached("online", "rtdb write ok");
                } else {
                    if (!result.bufferStoreOk) {
                        _bufferStoreFailCount++;
                    }
                    APP_LOG_CLOUD("Upload buffered: stage=%s detail=%s elapsed=%lu ms state={%s} diag={%s}\n",
                                  result.stage.c_str(),
                                  result.detail.c_str(),
                                  (unsigned long)uploadElapsedMs,
                                  result.pipelineState.c_str(),
                                  buildUploadDiagSummary(result.firebaseReady).c_str());

                    if (result.stage == "network_down") {
                        publishSystemStatusCached("offline_buffering", "network down, buffered");
                    } else if (result.stage == "firebase_not_ready" ||
                               result.stage == "publish_blocked_auth_not_initialized" ||
                               result.stage == "publish_blocked_gate_not_ready" ||
                               result.stage == "publish_blocked_begin_not_done" ||
                               result.stage == "publish_blocked_transport_not_ready") {
                        publishSystemStatusCached("degraded", "firebase not ready, buffered");
                    } else if (result.stage == "publish_error") {
                        publishSystemStatusCached("degraded", "rtdb publish error, buffered");
                    } else {
                        publishSystemStatusCached(hasInternet ? "degraded" : "offline_buffering",
                                                  hasInternet ? "telemetry build/buffer issue" : "offline buffered");
                    }
                }
            }
        }

        vTaskDelay(pdMS_TO_TICKS(APP_NETWORK_LOOP_DELAY_MS));
    }
}
