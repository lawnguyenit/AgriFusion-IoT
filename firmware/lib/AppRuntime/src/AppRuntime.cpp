#include "AppRuntime.h"

#include <FS.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <ArduinoJson.h>
#include <cstring>
#include <esp_sleep.h>
#include <esp_ota_ops.h>
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

namespace {
String buildUploadDiagSummary(bool firebaseReady) {
#if USE_SIM_NETWORK
    SimNetworkState sim = simReadNetworkState(false);
    char buf[256];
    snprintf(buf,
             sizeof(buf),
             "net=%d fb=%d reg=%d attach=%d gprs=%d ip=%s ip_valid=%d ip_source=%s csq=%d rssi=%d op=%s",
             networkIsConnected() ? 1 : 0,
             firebaseReady ? 1 : 0,
             sim.networkRegistered ? 1 : 0,
             sim.packetAttached ? 1 : 0,
             sim.gprsConnected ? 1 : 0,
             sim.localIp.c_str(),
             sim.localIpValid ? 1 : 0,
             sim.localIpSource.c_str(),
             sim.signalCsq,
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
      _nodeRuntimePublisher(makeNodeRuntimeConfig()),
      _firebasePipeline(makeFirebasePipelineConfig(), _rawTelemetryReporter, _nodeRuntimePublisher),
      _sht30Service(SHT30_SDA_PIN, SHT30_SCL_PIN, SHT30_I2C_ADDR, APP_SHT30_RETRY_INIT_MS),
      _ds18b20Service(DS18B20_DATA_PIN, DS18B20_RETRY_INIT_MS),
      _soilMoistureService(SOIL_MOISTURE_ADC_PIN,
                           SOIL_MOISTURE_AIR_ADC,
                           SOIL_MOISTURE_WATER_ADC,
                           SOIL_MOISTURE_SAMPLE_COUNT,
                           SOIL_MOISTURE_SAMPLE_GAP_MS),
      _packetBuilder(_sht30Service),
      _serialNpk(1) {}

NodeRuntimeConfig AppRuntime::makeNodeRuntimeConfig() {
    NodeRuntimeConfig cfg;
    cfg.nodeRootPath = APP_RTDB_PATH_NODE_ROOT;
    cfg.nodeInfoPath = APP_RTDB_PATH_NODE_INFO;
    cfg.nodeLatestPath = APP_RTDB_PATH_NODE_LATEST;
    cfg.nodeLatestMetaPath = APP_RTDB_PATH_NODE_LATEST_META;
    cfg.nodeDebugRootPath = APP_RTDB_PATH_NODE_DEBUG_ROOT;
    cfg.nodeDebugStatusPath = APP_RTDB_PATH_NODE_DEBUG_STATUS;
    cfg.nodeDebugTelemetryPath = APP_RTDB_PATH_NODE_DEBUG_TELEMETRY;
    cfg.nodeId = APP_NODE_ID;
    cfg.deviceUid = APP_NODE_DEVICE_UID;
    cfg.siteId = APP_NODE_SITE_ID;
    cfg.powerType = APP_NODE_POWER_TYPE;
    cfg.timezone = APP_NODE_TIMEZONE;
    cfg.telemetryRetentionDays = APP_TELEMETRY_RETENTION_DAYS;
    cfg.wakeIntervalSec = APP_SENSOR_SAMPLE_INTERVAL_MS / 1000U;
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
    if (!APP_RUN_CONTINUOUS) {
        runWakeCycle();
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

void AppRuntime::runWakeCycle() {
    APP_LOG_SYS("Bat dau wake cycle: opening -> collection -> finalization.\n");

    OpeningResult opening = runOpeningPhase();
    CollectionResult collection = runCollectionPhase();
    FinalizationResult finalization = runFinalizationPhase(opening, collection);

    if (finalization.sleepRequested) {
        enterTimedDeepSleep(finalization.sleepMs, finalization.reason.c_str());
    }

    APP_LOG_SYS("Wake cycle khong co quyet dinh sleep, dung lai de tranh lap vo han.\n");
}

OpeningResult AppRuntime::runOpeningPhase() {
    OpeningResult result;
    result.storageReady = setupStorage();
    _offlineReplayPending = storageFileExists(APP_OFFLINE_RAW_FILE);
    result.offlineReplayPending = _offlineReplayPending;

    prepareSensorsForWake(result);
    result.cloudReady = openNetworkAndCloud();
    result.networkReady = networkIsConnected();
    result.timeReady = utcEpochMsIfSynced() > 0;

    char detail[192];
    snprintf(detail,
             sizeof(detail),
             "storage=%d npk=%d sht30=%d ds18b20=%d moisture=%d net=%d cloud=%d time=%d backlog=%d",
             result.storageReady ? 1 : 0,
             result.npkPrepared ? 1 : 0,
             result.sht30Ready ? 1 : 0,
             result.ds18b20Ready ? 1 : 0,
             result.soilMoistureReady ? 1 : 0,
             result.networkReady ? 1 : 0,
             result.cloudReady ? 1 : 0,
             result.timeReady ? 1 : 0,
             result.offlineReplayPending ? 1 : 0);
    result.detail = detail;
    APP_LOG_SYS("Phase opening done: %s\n", result.detail.c_str());
    return result;
}

void AppRuntime::prepareSensorsForWake(OpeningResult &result) {
    APP_LOG_SENSOR("Phase opening: khoi tao NPK UART, SHT30, DS18B20 va moisture.\n");
    _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    _npkSensor.begin(_serialNpk);
    result.npkPrepared = true;
    result.sht30Ready = _sht30Service.tryInit(true);
#if DS18B20_PIPELINE_ENABLED
    result.ds18b20Ready = _ds18b20Service.tryInit(true);
#else
    result.ds18b20Ready = true;
#endif
#if SOIL_MOISTURE_PIPELINE_ENABLED
    _soilMoistureService.begin();
    result.soilMoistureReady = true;
#else
    result.soilMoistureReady = true;
#endif
}

CollectionResult AppRuntime::runCollectionPhase() {
    CollectionResult result;
    uint32_t startMs = millis();
    result.ok = collectSingleSample(result.payload, result.sensorAlarm);
    result.elapsedMs = millis() - startMs;
    result.detail = result.ok ? "sample_built" : "sample_build_failed";
    APP_LOG_SENSOR("Phase collection done: ok=%d alarm=%d elapsed=%lu ms.\n",
                   result.ok ? 1 : 0,
                   result.sensorAlarm ? 1 : 0,
                   (unsigned long)result.elapsedMs);
    return result;
}

FinalizationResult AppRuntime::runFinalizationPhase(const OpeningResult &opening,
                                                    const CollectionResult &collection) {
    FinalizationResult result;
    if (!collection.ok) {
        APP_LOG_SENSOR("Phase collection that bai, khong tao packet de gui.\n");
        result.stage = "sample_fail";
        result.detail = collection.detail;
        result.reason = "sample_fail";
        result.sleepMs = APP_SLEEP_FAIL_RETRY_INTERVAL_MS;
        result.sleepRequested = true;
        return result;
    }

    // Re-check once after collection. The opening result records what was
    // ready before sampling; finalization decides from the current transport
    // state whether it can publish or must buffer.
    networkMaintain();
    bool hasInternet = networkIsConnected();
    if (hasInternet) {
        ensureCloudTransportReady(hasInternet, "finalization_check", false);
        beginFirebaseClientIfNeeded(hasInternet, false, "finalization_check");
    }
    bool firebaseReady = _firebaseClientInitialized ? _firebasePipeline.ready() : false;
    result.cloudReady = hasInternet && firebaseReady;
    if (opening.cloudReady != result.cloudReady) {
        APP_LOG_NET("Finalization cloud state changed: opening=%d current=%d.\n",
                    opening.cloudReady ? 1 : 0,
                    result.cloudReady ? 1 : 0);
    }
    logConnectivityTransitions(hasInternet, firebaseReady);

    if (result.cloudReady) {
        publishSystemStatusCached("opening_complete", "wake cycle cloud ready", true);

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
        TelemetryPushResult pushed = _firebasePipeline.pushPayloadDetailed(
            _firebaseData,
            collection.payload.c_str(),
            collection.sensorAlarm,
            collection.sensorAlarm ? APP_PAYLOAD_KIND_SENSOR_ALARM : APP_PAYLOAD_KIND_NODE_PACKET,
            _deviceContext,
            currentFwVersion(),
            currentFwPartition(),
            _offlineReplayPending,
            utcEpochMsIfSynced());
        uint32_t uploadElapsedMs = millis() - uploadStartMs;

        result.uploaded = pushed.uploaded;
        result.buffered = pushed.buffered;
        result.stage = pushed.stage;
        result.detail = pushed.detail;
        if (pushed.uploaded) {
            APP_LOG_CLOUD("Phase finalization upload OK in %lu ms ref=%s telemetry_path=%s stage=%s duplicate=%d latest_updated=%d.\n",
                          (unsigned long)uploadElapsedMs,
                          pushed.refId.c_str(),
                          pushed.telemetryPath.c_str(),
                          pushed.stage.c_str(),
                          pushed.duplicate ? 1 : 0,
                          pushed.latestUpdated ? 1 : 0);
            publishSystemStatusCached(collection.sensorAlarm ? "sensor_alarm" : "online",
                                      collection.sensorAlarm ? "wake upload sensor alarm" : "wake upload ok",
                                      true);
            result.reason = "cycle_done";
            result.sleepMs = APP_SENSOR_SAMPLE_INTERVAL_MS;
        } else {
            APP_LOG_CLOUD("Phase finalization upload buffered: stage=%s detail=%s elapsed=%lu ms state={%s}\n",
                          pushed.stage.c_str(),
                          pushed.detail.c_str(),
                          (unsigned long)uploadElapsedMs,
                          pushed.pipelineState.c_str());
            result.reason = "upload_buffered";
            result.sleepMs = APP_SLEEP_FAIL_RETRY_INTERVAL_MS;
        }

        result.sleepRequested = true;
        return result;
    }

    String payload = collection.payload;
    annotatePayloadSendState(payload, "cloud_not_ready_timeout", APP_SIM_READY_MAX_POLLS);
    TelemetryPushResult buffered = _firebasePipeline.pushPayloadDetailed(
        _firebaseData,
        payload.c_str(),
        collection.sensorAlarm,
        collection.sensorAlarm ? APP_PAYLOAD_KIND_SENSOR_ALARM : APP_PAYLOAD_KIND_NODE_PACKET,
        _deviceContext,
        currentFwVersion(),
        currentFwPartition(),
        _offlineReplayPending,
        utcEpochMsIfSynced());

    result.buffered = buffered.buffered;
    result.stage = buffered.stage;
    result.detail = buffered.detail;
    APP_LOG_CLOUD("Phase finalization cloud unavailable: buffered=%d stage=%s detail=%s\n",
                  buffered.buffered ? 1 : 0,
                  buffered.stage.c_str(),
                  buffered.detail.c_str());
    result.reason = "cloud_retry_timeout";
    result.sleepMs = APP_SLEEP_FAIL_RETRY_INTERVAL_MS;
    result.sleepRequested = true;
    return result;
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
    const esp_app_desc_t *desc = esp_ota_get_app_description();
    return desc ? String(desc->version) : String("unknown");
}

String AppRuntime::currentFwPartition() const {
    const esp_partition_t *running = esp_ota_get_running_partition();
    return (running && running->label) ? String(running->label) : String("unknown");
}

bool AppRuntime::readDs18b20ForNpk(Ds18b20Reading &reading,
                                   uint8_t &attempts,
                                   uint32_t &elapsedMs,
                                   String &errorText) {
    reading = {};
    attempts = 0U;
    elapsedMs = 0U;
    errorText = "disabled";

#if DS18B20_PIPELINE_ENABLED
    const uint32_t startMs = millis();
    errorText = "not_ready";

    for (uint32_t attempt = 1U;
         attempt <= static_cast<uint32_t>(APP_SENSOR_RETRY_WINDOW_COUNT);
         ++attempt) {
        if (!_ds18b20Service.ready()) {
            APP_LOG_SENSOR("DS18B20 chua ready, thu init lai trong cua so retry %lu/%u.\n",
                           static_cast<unsigned long>(attempt),
                           static_cast<unsigned>(APP_SENSOR_RETRY_WINDOW_COUNT));
            _ds18b20Service.tryInit(true);
        }

        ++attempts;
        if (_ds18b20Service.readPrimary(reading)) {
            errorText = "ok";
            elapsedMs = millis() - startMs;
            APP_LOG_SENSOR("DS18B20 result: read_ok=1 sample_valid=1 retry=%u elapsed=%lu ms error=ok\n",
                           static_cast<unsigned>(attempts - 1U),
                           static_cast<unsigned long>(elapsedMs));
            APP_LOG_SENSOR("DS18B20 value: temp=%.2f C raw=0x%04X resolution=%u-bit\n",
                           static_cast<double>(reading.temperatureC),
                           static_cast<unsigned>(static_cast<uint16_t>(reading.rawTemperature)),
                           static_cast<unsigned>(reading.resolutionBits));
            return true;
        }

        if (!reading.presenceDetected) {
            errorText = "presence_missing";
        } else if (!reading.scratchpadCrcOk) {
            errorText = "scratchpad_crc_failed";
        } else if (!reading.rangeOk) {
            errorText = "out_of_range";
        } else {
            errorText = "read_failed";
        }

        APP_LOG_SENSOR("DS18B20 chua on dinh, retry %lu/%u sau cua so %lu ms. error=%s\n",
                       static_cast<unsigned long>(attempt),
                       static_cast<unsigned>(APP_SENSOR_RETRY_WINDOW_COUNT),
                       static_cast<unsigned long>(APP_SENSOR_RETRY_WINDOW_MS),
                       errorText.c_str());
        if (attempt < static_cast<uint32_t>(APP_SENSOR_RETRY_WINDOW_COUNT)) {
            delay(APP_SENSOR_RETRY_WINDOW_MS);
        }
    }

    elapsedMs = millis() - startMs;
    APP_LOG_SENSOR("DS18B20 result: read_ok=0 sample_valid=0 retry=%u elapsed=%lu ms error=%s\n",
                   static_cast<unsigned>(attempts),
                   static_cast<unsigned long>(elapsedMs),
                   errorText.c_str());
#endif

    return false;
}

bool AppRuntime::readSoilMoistureForNpk(SoilMoistureReading &reading,
                                        uint8_t &attempts,
                                        uint32_t &elapsedMs,
                                        String &errorText) {
    reading = {};
    attempts = 0U;
    elapsedMs = 0U;
    errorText = "disabled";

#if SOIL_MOISTURE_PIPELINE_ENABLED
    const uint32_t startMs = millis();
    ++attempts;
    const bool readOk = _soilMoistureService.read(reading);
    elapsedMs = millis() - startMs;
    errorText = readOk ? reading.error : "adc_read_failed";
    APP_LOG_SENSOR("Soil moisture result: read_ok=%d sample_valid=%d raw=%d raw_min=%d raw_max=%d voltage=%lu mV percent=%d calibration=%d elapsed=%lu ms error=%s depth_cm=%d..%d\n",
                   readOk ? 1 : 0,
                   reading.sampleValid ? 1 : 0,
                   reading.raw,
                   reading.rawMin,
                   reading.rawMax,
                   static_cast<unsigned long>(reading.voltageMv),
                   reading.percent,
                   reading.calibrationValid ? 1 : 0,
                   static_cast<unsigned long>(elapsedMs),
                   errorText.c_str(),
                   static_cast<int>(SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN),
                   static_cast<int>(SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX));
    return readOk;
#else
    (void)reading;
    (void)attempts;
    (void)elapsedMs;
    (void)errorText;
    return false;
#endif
}

bool AppRuntime::collectSingleSample(String &payloadOut, bool &sensorAlarmOut) {
    payloadOut = "";
    sensorAlarmOut = false;

    APP_LOG_SENSOR("Bat dau thu thap mau trong wake cycle.\n");
    uint32_t sampleStartMs = millis();
    auto parseShtState = [](const String &json,
                            bool &readOk,
                            bool &sampleValid,
                            uint32_t &retryCount,
                            uint32_t &elapsedMs,
                            float &temperatureC,
                            float &humidityPct,
                            String &errorText) {
        readOk = false;
        sampleValid = false;
        retryCount = 0;
        elapsedMs = 0;
        temperatureC = NAN;
        humidityPct = NAN;
        errorText = "json_parse_fail";

        JsonDocument doc;
        if (deserializeJson(doc, json) != DeserializationError::Ok) {
            return;
        }

        readOk = doc["sht_read_ok"] | false;
        sampleValid = doc["sht_sample_valid"] | false;
        retryCount = doc["sht_retry_count"] | 0U;
        elapsedMs = doc["sht_read_elapsed_ms"] | 0U;
        if (sampleValid) {
            temperatureC = doc["sht_temp_c"] | NAN;
            humidityPct = doc["sht_hum_pct"] | NAN;
        }
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
    uint32_t shtRetryCount = 0;
    uint32_t shtReadElapsedMs = 0;
    float shtTemperatureC = NAN;
    float shtHumidityPct = NAN;
    String shtError = "not_started";
    for (uint32_t attempt = 1; attempt <= (uint32_t)APP_SENSOR_RETRY_WINDOW_COUNT; ++attempt) {
        if (!_sht30Service.ready()) {
            APP_LOG_SENSOR("SHT30 chua ready, thu init lai trong cua so retry %lu/%u.\n",
                           (unsigned long)attempt,
                           (unsigned)APP_SENSOR_RETRY_WINDOW_COUNT);
            // Each outer retry is a real init/probe attempt. The service-level
            // throttle is useful between wake cycles, but would otherwise turn
            // retries 2/3 into no-op calls after a failed startup probe.
            _sht30Service.tryInit(true);
        }

        shtJson = _sht30Service.buildJsonPayload(APP_SENSOR_TYPE_SHT30,
                                                 APP_SENSOR_ID_SHT30,
                                                 APP_EDGE_SYSTEM_SHT,
                                                 APP_EDGE_SYSTEM_ID_SHT,
                                                 "sht30",
                                                 SHT30_READ_MAX_ATTEMPTS,
                                                 SHT30_RETRY_DELAY_MS,
                                                 SHT30_MAX_WAIT_MS);
        parseShtState(shtJson,
                      shtReadOk,
                      shtSampleValid,
                      shtRetryCount,
                      shtReadElapsedMs,
                      shtTemperatureC,
                      shtHumidityPct,
                      shtError);
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

    APP_LOG_SENSOR("SHT30 result: read_ok=%d sample_valid=%d retry=%lu elapsed=%lu ms error=%s\n",
                   shtReadOk ? 1 : 0,
                   shtSampleValid ? 1 : 0,
                   (unsigned long)shtRetryCount,
                   (unsigned long)shtReadElapsedMs,
                   shtError.c_str());
    if (shtSampleValid) {
        APP_LOG_SENSOR("SHT30 values: temp=%.2f C hum=%.2f %%\n",
                       shtTemperatureC,
                       shtHumidityPct);
    }

    Ds18b20Reading ds18b20Reading;
    uint8_t ds18b20Attempts = 0U;
    uint32_t ds18b20ElapsedMs = 0U;
    String ds18b20Error;
    const bool ds18b20SampleValid = readDs18b20ForNpk(ds18b20Reading,
                                                      ds18b20Attempts,
                                                      ds18b20ElapsedMs,
                                                      ds18b20Error);
    if (ds18b20SampleValid) {
        _npkSensor.applyExternalTemperature(data,
                                            ds18b20Reading.temperatureC,
                                            ds18b20Reading.rawTemperature);
        APP_LOG_SENSOR("NPK soil temp source=DS18B20 temp=%.2f C raw=0x%04X\n",
                       static_cast<double>(ds18b20Reading.temperatureC),
                       static_cast<unsigned>(static_cast<uint16_t>(ds18b20Reading.rawTemperature)));
    }

    SoilMoistureReading soilMoistureReading;
    uint8_t soilMoistureAttempts = 0U;
    uint32_t soilMoistureElapsedMs = 0U;
    String soilMoistureError;
    const bool soilMoistureReadOk = readSoilMoistureForNpk(soilMoistureReading,
                                                           soilMoistureAttempts,
                                                           soilMoistureElapsedMs,
                                                           soilMoistureError);
#if SOIL_MOISTURE_PIPELINE_ENABLED
    // Always attach the external reading, including ADC/calibration failures,
    // so Firebase receives the source and explicit invalid/error diagnostics.
    _npkSensor.applyExternalMoisture(data, soilMoistureReading);
    APP_LOG_SENSOR("NPK soil moisture source=soil_moisture_v1_2 read_ok=%d raw=%d voltage=%lu mV percent=%d valid=%d error=%s\n",
                   soilMoistureReadOk ? 1 : 0,
                   soilMoistureReading.raw,
                   static_cast<unsigned long>(soilMoistureReading.voltageMv),
                   soilMoistureReading.percent,
                   soilMoistureReading.sampleValid ? 1 : 0,
                   soilMoistureReading.error.c_str());
#else
    (void)soilMoistureReadOk;
    (void)soilMoistureReading;
#endif

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

bool AppRuntime::openNetworkAndCloud() {
    bool netOk = networkSetup();
    if (!netOk) {
        APP_LOG_NET("Khoi dong mang lan dau chua thanh cong, se vao cua so retry.\n");
    }

    initTimeSync();
    for (uint32_t poll = 1; poll <= (uint32_t)APP_SIM_READY_MAX_POLLS; ++poll) {
        networkMaintain();
        bool hasInternet = networkIsConnected();
        APP_LOG_NET("Phase opening network retry %lu/%u: net=%d diag={%s}\n",
                    (unsigned long)poll,
                    (unsigned)APP_SIM_READY_MAX_POLLS,
                    hasInternet ? 1 : 0,
                    buildUploadDiagSummary(false).c_str());

        bool transportReady = ensureCloudTransportReady(hasInternet, "wake_retry_window", poll == 1);
        if (transportReady) {
            beginFirebaseClientIfNeeded(hasInternet, !_firebaseClientInitialized, "wake_retry_window");
            bool firebaseReady = _firebaseClientInitialized ? _firebasePipeline.ready() : false;
            if (firebaseReady) {
                APP_LOG_NET("Phase opening cloud ready tai lan retry %lu.\n", (unsigned long)poll);
                return true;
            }
        }

        if (poll < (uint32_t)APP_SIM_READY_MAX_POLLS) {
            APP_LOG_NET("Phase opening cloud chua san sang, cho %lu giay roi hoi lai.\n",
                        (unsigned long)(APP_SIM_READY_RETRY_INTERVAL_MS / 1000UL));
            delay(APP_SIM_READY_RETRY_INTERVAL_MS);
        }
    }

    APP_LOG_NET("Phase opening het cua so retry, cloud chua san sang.\n");
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

    if (verboseLog || !report.transportUsable || !report.timeReadyAfter ||
        report.timeSyncFromSimOk || report.timeSyncFromHttpOk) {
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
                                                                _firebaseData);
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

void AppRuntime::sensorTaskLoop() {
    _serialNpk.begin(NPK_BAUDRATE, SERIAL_8N1, NPK_RX_PIN, NPK_TX_PIN);
    _npkSensor.begin(_serialNpk);
    _soilMoistureService.begin();
    _sht30Service.tryInit();
#if DS18B20_PIPELINE_ENABLED
    _ds18b20Service.tryInit();
#endif

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
#if DS18B20_PIPELINE_ENABLED
        if (!_ds18b20Service.ready()) {
            APP_LOG_SENSOR("DS18B20 chua ready, thu init lai.\n");
            _ds18b20Service.tryInit();
        }
#endif

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

        Ds18b20Reading ds18b20Reading;
        uint8_t ds18b20Attempts = 0U;
        uint32_t ds18b20ElapsedMs = 0U;
        String ds18b20Error;
        const bool ds18b20SampleValid = readDs18b20ForNpk(ds18b20Reading,
                                                          ds18b20Attempts,
                                                          ds18b20ElapsedMs,
                                                          ds18b20Error);
        if (ds18b20SampleValid) {
            _npkSensor.applyExternalTemperature(data,
                                                ds18b20Reading.temperatureC,
                                                ds18b20Reading.rawTemperature);
            APP_LOG_SENSOR("NPK soil temp source=DS18B20 temp=%.2f C raw=0x%04X\n",
                           static_cast<double>(ds18b20Reading.temperatureC),
                           static_cast<unsigned>(static_cast<uint16_t>(ds18b20Reading.rawTemperature)));
        }

        SoilMoistureReading soilMoistureReading;
        uint8_t soilMoistureAttempts = 0U;
        uint32_t soilMoistureElapsedMs = 0U;
        String soilMoistureError;
        const bool soilMoistureReadOk = readSoilMoistureForNpk(soilMoistureReading,
                                                               soilMoistureAttempts,
                                                               soilMoistureElapsedMs,
                                                               soilMoistureError);
#if SOIL_MOISTURE_PIPELINE_ENABLED
        // Keep the moisture source in the packet even when the ADC read fails;
        // the service exposes read_ok/error separately from value validity.
        _npkSensor.applyExternalMoisture(data, soilMoistureReading);
        APP_LOG_SENSOR("NPK soil moisture source=soil_moisture_v1_2 read_ok=%d raw=%d voltage=%lu mV percent=%d valid=%d error=%s\n",
                       soilMoistureReadOk ? 1 : 0,
                       soilMoistureReading.raw,
                       static_cast<unsigned long>(soilMoistureReading.voltageMv),
                       soilMoistureReading.percent,
                       soilMoistureReading.sampleValid ? 1 : 0,
                       soilMoistureReading.error.c_str());
#else
        (void)soilMoistureReadOk;
        (void)soilMoistureReading;
#endif

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
                _bootCloudSnapshotPublished = true;
            }
            maintainTimeSync();
            _firebasePipeline.probeTelemetryPathIfNeeded(_firebaseData, utcEpochMsIfSynced());
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
