#ifndef CONFIG_H
#define CONFIG_H

// ================= [DEBUG] =================
#define DEBUG_MODE 1
#define DEBUG_PORT Serial0
#define DEBUG_BAUDRATE 115200

#if DEBUG_MODE
  #define CUS_DBG(...) DEBUG_PORT.print(__VA_ARGS__)
  #define CUS_DBGLN(...) DEBUG_PORT.println(__VA_ARGS__)
  #define CUS_DBGF(...) DEBUG_PORT.printf(__VA_ARGS__)
#else
  #define CUS_DBG(...)
  #define CUS_DBGLN(...)
  #define CUS_DBGF(...)
#endif

// ================= [NETWORK SELECT] =================
// 0 = WiFi, 1 = SIM 4G
#define USE_SIM_NETWORK 1

// ================= [APP MODE] =================
// Current deployment profile: keep the node running continuously.
// Deep-sleep mode can be added later after field power profiling is stable.
#define APP_RUN_CONTINUOUS 1

// ================= [NODE IDENTITY] =================
#define APP_NODE_SLOT_KEY              "Node1"
#define APP_NODE_ID                    "Node1"
#define APP_NODE_NAME                  "Vuon sau rieng A"
#define APP_NODE_SITE_ID               "farm_a_zone_1"
#define APP_NODE_DEVICE_UID            "esp32s3_node1"
#define APP_NODE_POWER_TYPE            "solar_battery"
#define APP_NODE_TIMEZONE              "Asia/Ho_Chi_Minh"
#define APP_NODE_TZ_CONFIG             "ICT-7"
#define APP_TELEMETRY_RETENTION_DAYS   30

// ================= [FIREBASE / RTDB] =================
#define APP_FIREBASE_DATABASE_URL      "https://agri-fusion-iot-default-rtdb.asia-southeast1.firebasedatabase.app"
#define APP_FIREBASE_API_KEY           "AIzaSyAih-kFW-VkgEKVXnTd7aiFCiUjNy-6j18"
#define APP_FIREBASE_LEGACY_TOKEN      "wZehBBnCza75i6iNpcUgKQT463dmHXMbfqRuYVsc"

#define APP_RTDB_PATH_NODE_ROOT        "/Node1"
#define APP_RTDB_PATH_NODE_INFO        "/Node1/info"
#define APP_RTDB_PATH_NODE_LIVE        "/Node1/live"
#define APP_RTDB_PATH_NODE_STATUS      "/Node1/status_events"
#define APP_OFFLINE_RAW_FILE           "/offline_data.txt"

// ================= [EDGE METADATA] =================
#define APP_EDGE_SYSTEM_NPK            "soil_npk_edge"
#define APP_EDGE_SYSTEM_ID_NPK         "edge_npk_01"
#define APP_EDGE_SYSTEM_SHT            "air_climate_edge"
#define APP_EDGE_SYSTEM_ID_SHT         "edge_sht30_01"

// ================= [OTA] =================
#define APP_RTDB_PATH_OTA_STATUS       "/ota/status"
#define APP_RTDB_PATH_OTA_HISTORY      "/ota/history"
#define APP_RTDB_PATH_OTA_COMMAND      "/ota/command"

#define APP_OTA_POLL_INTERVAL_MS       60000UL
#define APP_OTA_CONFIRM_HEALTH_MS      60000UL
#define APP_OTA_MAX_PENDING_BOOTS      3UL

// ================= [TASK / APP TIMING] =================
#define APP_SENSOR_SAMPLE_INTERVAL_MS      (15UL * 60UL * 1000UL)
#define APP_NETWORK_LOOP_DELAY_MS          250UL
#define APP_OFFLINE_REPLAY_INTERVAL_MS     30000UL
#define APP_NODE_INFO_PUSH_INTERVAL_MS     300000UL
#define APP_TELEMETRY_PROBE_INTERVAL_MS    30000UL
#define APP_TIME_SYNC_RETRY_MS             60000UL
#define APP_STATUS_REFRESH_INTERVAL_MS     300000UL

// ================= [TASK / BUFFER] =================
#define APP_SENSOR_PAYLOAD_BUFFER_SIZE     1536U
#define APP_MESSAGE_KIND_BUFFER_SIZE       24U
#define APP_QUEUE_LENGTH                   10U
#define APP_QUEUE_SEND_WAIT_MS             10UL
#define APP_QUEUE_RECV_WAIT_MS             100UL
#define APP_PAYLOAD_KIND_NODE_PACKET       "node_packet_json"
#define APP_PAYLOAD_KIND_SENSOR_ALARM      "sensor_alarm_json"

#define APP_SENSOR_TASK_STACK_SIZE         8192U
#define APP_NETWORK_TASK_STACK_SIZE        16384U
#define APP_SENSOR_TASK_PRIORITY           1U
#define APP_NETWORK_TASK_PRIORITY          2U
#define APP_SENSOR_TASK_CORE               1U
#define APP_NETWORK_TASK_CORE              0U

// ================= [SENSOR POLICY] =================
#define APP_NPK_FAIL_ALARM_THRESHOLD       3
#define APP_NPK_UART_RESET_FAIL_INTERVAL   2
#define APP_SHT30_RETRY_INIT_MS            10000UL

// ================= [LOG LABELS] =================
#define APP_LOG_SYS_TAG        "[SYS]"
#define APP_LOG_SENSOR_TAG     "[SENSOR]"
#define APP_LOG_NET_TAG        "[NET]"
#define APP_LOG_CLOUD_TAG      "[CLOUD]"
#define APP_LOG_OTA_TAG        "[OTA]"

// ================= [SIM PINS / MODEM] =================
#define SIM_TX_PIN      17
#define SIM_RX_PIN      16
#define SIM_BAUDRATE    115200
#define SIM_GSM_PIN     ""
#define SIM_APN         "v-internet"
#define SIM_APN_USER    ""
#define SIM_APN_PASS    ""

#define SIM_BOOT_WAIT_MS                5000
#define SIM_AT_READY_RETRY_COUNT        12
#define SIM_AT_READY_RETRY_DELAY_MS     250
#define SIM_AT_RESPONSE_TIMEOUT_MS      5000
#define SIM_DEBUG_RECHECK_DELAY_MS      1000
#define SIM_NETWORK_CHECK_INTERVAL_MS   10000
#define SIM_RECONNECT_INTERVAL_MS       30000
#define SIM_RESTART_COOLDOWN_MS         300000

// ================= [NPK SENSOR] =================
#define NPK_TX_PIN      5
#define NPK_RX_PIN      4
#define NPK_BAUDRATE    4800

// ================= [SHT30 SENSOR] =================
#define SHT30_SDA_PIN   8
#define SHT30_SCL_PIN   9
#define SHT30_I2C_ADDR  0x44

#define SHT30_READ_MAX_ATTEMPTS   5
#define SHT30_RETRY_DELAY_MS      120
#define SHT30_MAX_WAIT_MS         1200

#endif
