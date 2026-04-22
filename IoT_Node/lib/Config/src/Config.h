#ifndef CONFIG_H
#define CONFIG_H

// ================= [DEBUG] =================
#define DEBUG_MODE 1                  // 1 = bat log debug, 0 = tat log debug
#define DEBUG_PORT Serial0            // cong serial dung de in log debug
#define DEBUG_BAUDRATE 115200         // toc do serial debug

#if DEBUG_MODE
  #define CUS_DBG(...) DEBUG_PORT.print(__VA_ARGS__)        // in log khong xuong dong
  #define CUS_DBGLN(...) DEBUG_PORT.println(__VA_ARGS__)    // in log va xuong dong
  #define CUS_DBGF(...) DEBUG_PORT.printf(__VA_ARGS__)      // in log theo dinh dang printf
#else
  #define CUS_DBG(...)
  #define CUS_DBGLN(...)
  #define CUS_DBGF(...)
#endif

// ================= [NETWORK SELECT] =================
// 0 = WiFi, 1 = SIM 4G
#define USE_SIM_NETWORK 1            // chon kieu mang chinh cho node

// ================= [APP MODE] =================
// Current deployment profile: keep the node running continuously.
// Deep-sleep mode can be added later after field power profiling is stable.
#define APP_RUN_CONTINUOUS 1         // 1 = chay lien tuc, 0 = du phong cho che do sleep
#define APP_SIM_PURE_TEST_MODE 0     // 1 = bo qua AppRuntime, chay che do test SIM thuan de chan doan mang
#define APP_RAW_TRUTH_PROBE_MODE 0   // 1 = chay harness raw transport/time, 0 = de du phong cho app runtime sau nay

// ================= [NODE IDENTITY] =================
#define APP_NODE_SLOT_KEY              "Node1"              // key dinh danh node trong app/cloud
#define APP_NODE_ID                    "Node1"              // id node dung trong payload va cloud
#define APP_NODE_NAME                  "Vuon sau rieng A"   // ten hien thi cua node
#define APP_NODE_SITE_ID               "Binh Phu, Vinh Long" // vi tri/cum trien khai
#define APP_NODE_DEVICE_UID            "esp32s3_node1"      // uid thiet bi phan biet voi cac node khac
#define APP_NODE_POWER_TYPE            "solar_battery"      // kieu nguon cap de dua len metadata
#define APP_NODE_TIMEZONE              "Asia/Ho_Chi_Minh"   // timezone dang text de luu metadata
#define APP_NODE_TZ_CONFIG             "ICT-7"              // chuoi cau hinh timezone cho NTP
#define APP_TELEMETRY_RETENTION_DAYS   30                   // so ngay metadata/telemetry duoc danh dau luu tru

// ================= [FIREBASE / RTDB] =================
#define APP_FIREBASE_DATABASE_URL      "https://agri-fusion-iot-default-rtdb.asia-southeast1.firebasedatabase.app" // URL RTDB
#define APP_FIREBASE_API_KEY           "AIzaSyAih-kFW-VkgEKVXnTd7aiFCiUjNy-6j18" // API key Firebase client
#define APP_FIREBASE_LEGACY_TOKEN      "wZehBBnCza75i6iNpcUgKQT463dmHXMbfqRuYVsc" // token ghi RTDB dang dung
#define APP_FIREBASE_SIM_TRANSPORT_ENABLED 1                    // 1 = dung RTDB REST qua HTTP(S) engine cua modem; 0 = chan cloud qua SIM

#define APP_RTDB_PATH_NODE_ROOT        "/Node1"             // root du lieu cua node tren RTDB
#define APP_RTDB_PATH_NODE_INFO        "/Node1/info"        // metadata thong tin node
#define APP_RTDB_PATH_NODE_LIVE        "/Node1/live"        // du lieu song / telemetry moi nhat
#define APP_RTDB_PATH_NODE_STATUS      "/Node1/status_events" // log trang thai he thong
#define APP_OFFLINE_RAW_FILE           "/offline_data.txt"  // file dem khi mat mang

// ================= [EDGE METADATA] =================
#define APP_EDGE_SYSTEM_NPK            "soil_npk_edge"      // ten nhom he thong cho cam bien NPK
#define APP_EDGE_SYSTEM_ID_NPK         "edge_npk"           // id he thong NPK trong payload
#define APP_EDGE_SYSTEM_SHT            "air_climate_edge"   // ten nhom he thong cho SHT30
#define APP_EDGE_SYSTEM_ID_SHT         "edge_sht30"         // id he thong SHT30 trong payload

// ================= [OTA] =================
#define APP_RTDB_PATH_OTA_STATUS       "/ota/status"        // path ghi trang thai OTA hien tai
#define APP_RTDB_PATH_OTA_HISTORY      "/ota/history"       // path luu lich su su kien OTA
#define APP_RTDB_PATH_OTA_COMMAND      "/ota/command"       // path doc lenh OTA tu cloud

#define APP_OTA_POLL_INTERVAL_MS       60000UL              // chu ky kiem tra lenh OTA
#define APP_OTA_CONFIRM_HEALTH_MS      60000UL              // thoi gian node phai chay on truoc khi confirm OTA
#define APP_OTA_MAX_PENDING_BOOTS      3UL                  // so lan boot toi da khi OTA dang cho xac nhan

// ================= [TASK / APP TIMING] =================
// #define APP_SENSOR_SAMPLE_INTERVAL_MS      (15UL * 60UL * 1000UL) // chu ky do va gui du lieu
#define APP_SENSOR_SAMPLE_INTERVAL_MS      (60000UL) // chu ky do va gui du lieu
#define APP_NETWORK_LOOP_DELAY_MS          250UL                  // do tre moi vong lap task mang
#define APP_OFFLINE_REPLAY_INTERVAL_MS     30000UL                // chu ky thu day lai du lieu da dem
#define APP_NODE_INFO_PUSH_INTERVAL_MS     300000UL               // chu ky cap nhat metadata node
#define APP_TELEMETRY_PROBE_INTERVAL_MS    30000UL                // chu ky probe/khao sat path telemetry
#define APP_TIME_SYNC_RETRY_MS             60000UL                // chu ky thu dong bo lai NTP
#define APP_STATUS_REFRESH_INTERVAL_MS     300000UL               // chu ky refresh trang thai du khong doi
#define APP_RUNTIME_DIAG_INTERVAL_MS       60000UL                // chu ky in heartbeat chan doan tong quan
#define APP_FIREBASE_REBEGIN_INTERVAL_MS   15000UL                // khoang cach toi thieu giua 2 lan begin/re-begin Firebase
#define APP_FIREBASE_NOT_READY_LOG_MS      15000UL                // chu ky in log khi Firebase van chua ready
#define APP_TRANSPORT_BOOTSTRAP_INTERVAL_MS 15000UL               // khoang cach toi thieu giua 2 lan bootstrap transport/time cho cloud
#define APP_TRANSPORT_DIAG_INTERVAL_MS      60000UL               // chu ky toi thieu giua 2 lan dump chan doan raw transport khi cloud van loi

// ================= [TASK / BUFFER] =================
#define APP_SENSOR_PAYLOAD_BUFFER_SIZE     1536U                 // kich thuoc toi da cho 1 payload JSON
#define APP_MESSAGE_KIND_BUFFER_SIZE       24U                   // kich thuoc chuoi phan loai payload
#define APP_QUEUE_LENGTH                   10U                   // so ban tin toi da cho trong queue
#define APP_QUEUE_SEND_WAIT_MS             10UL                  // thoi gian cho khi day ban tin vao queue
#define APP_QUEUE_RECV_WAIT_MS             100UL                 // thoi gian cho khi doc ban tin tu queue
#define APP_PAYLOAD_KIND_NODE_PACKET       "node_packet_json"    // nhan payload thong thuong
#define APP_PAYLOAD_KIND_SENSOR_ALARM      "sensor_alarm_json"   // nhan payload canh bao cam bien

#define APP_SENSOR_TASK_STACK_SIZE         8192U                 // stack cho task doc sensor
#define APP_NETWORK_TASK_STACK_SIZE        16384U                // stack cho task mang/cloud
#define APP_SENSOR_TASK_PRIORITY           1U                    // uu tien task sensor
#define APP_NETWORK_TASK_PRIORITY          2U                    // uu tien task mang cao hon sensor
#define APP_SENSOR_TASK_CORE               1U                    // core chay task sensor
#define APP_NETWORK_TASK_CORE              0U                    // core chay task mang

// ================= [SENSOR POLICY] =================
#define APP_NPK_FAIL_ALARM_THRESHOLD       3                     // nguong fail lien tiep de danh dau alarm
#define APP_NPK_UART_RESET_FAIL_INTERVAL   2                     // cu bao nhieu lan fail thi reset lai UART NPK
#define APP_SHT30_RETRY_INIT_MS            10000UL               // thoi gian moi lan thu init lai SHT30

// ================= [LOG LABELS] =================
#define APP_LOG_SYS_TAG        "[SYS]"      // nhan log he thong
#define APP_LOG_SENSOR_TAG     "[SENSOR]"   // nhan log cam bien
#define APP_LOG_NET_TAG        "[NET]"      // nhan log mang
#define APP_LOG_CLOUD_TAG      "[CLOUD]"    // nhan log Firebase/cloud
#define APP_LOG_OTA_TAG        "[OTA]"      // nhan log cap nhat firmware

// ================= [SIM PINS / MODEM] =================
#define SIM_TX_PIN      17                  // TX cua ESP noi sang RX cua SIM
#define SIM_RX_PIN      16                  // RX cua ESP noi sang TX cua SIM
#define SIM_BAUDRATE    115200              // baudrate UART giao tiep voi SIM
#define SIM_GSM_PIN     ""                  // ma PIN cua SIM neu nha mang yeu cau
#define SIM_APN         "v-internet"        // APN cua nha mang
#define SIM_APN_USER    ""                  // username APN
#define SIM_APN_PASS    ""                  // password APN
#define SIM_PDP_TYPE    "IP"                // kieu PDP context hien tai; co the thu "IPV4V6" neu can

#define SIM_BOOT_WAIT_MS                5000                    // thoi gian cho SIM on dinh sau khi cap nguon
#define SIM_AT_READY_RETRY_COUNT        12                      // so lan thu AT truoc khi ket luan SIM chua san sang
#define SIM_AT_READY_RETRY_DELAY_MS     250                     // do tre giua cac lan thu AT
#define SIM_AT_RESPONSE_TIMEOUT_MS      5000                    // timeout cho 1 lenh AT
#define SIM_DEBUG_RECHECK_DELAY_MS      1000                    // delay khi debug va kiem tra lai SIM
#define SIM_NETWORK_CHECK_INTERVAL_MS   10000                   // chu ky kiem tra trang thai mang SIM
#define SIM_RECONNECT_INTERVAL_MS       30000                   // chu ky thu reconnect du lieu
#define SIM_RESTART_COOLDOWN_MS         300000                  // thoi gian toi thieu giua 2 lan restart modem
#define SIM_PURE_TEST_INTERVAL_MS       5000UL                  // chu ky lap lai bai test SIM thuan
#define SIM_TEST_SOCKET_TIMEOUT_MS      5000UL                  // timeout cho moi bai test socket/http
#define SIM_TEST_DNS_HOST               "neverssl.com"          // dich test qua DNS
#define SIM_TEST_DNS_PORT               80                      // cong test HTTP qua DNS
#define APP_SIM_HTTP_PROBE_URL          "http://neverssl.com/"  // URL probe bang HTTP engine cua modem de xac nhan transport nen
#define SIM_VERBOSE_AT_QUERY_LOG        0                       // 1 = in tung lenh AT trong snapshot; 0 = chi in tom tat
#define SIM_VERBOSE_PROBE_DETAIL        0                       // 1 = in chi tiet probe/raw transport; 0 = chi in dong tom tat
#define SIM_ENABLE_FORENSIC_DUMP        0                       // 1 = khi fail se dump forensic AT day du
#define SIM_TEST_NETOPEN_RETRY_COUNT    2                       // so lan thu dong/mo lai NETOPEN trong 1 probe raw
#define SIM_TEST_NETOPEN_RETRY_DELAY_MS 500UL                   // do tre giua cac lan thu NETOPEN
#define SIM_TEST_RAW_HTTP_RETRY_COUNT   2                       // so lan thu lai toan bo bai test raw HTTP
#define SIM_TEST_TRY_IPV4V6_PROFILE     1                       // 1 = khi profile IP that bai thi thu them profile IPV4V6
#define SIM_SUPPLY_EN_PIN               1                       // chan bat nguon buck/modem; -1 neu khong can dieu khien
#define SIM_SUPPLY_EN_ACTIVE_HIGH       1                       // muc kich hoat cho chan bat nguon modem
#define SIM_PWRKEY_PIN                  -1                      // chan PWRKEY neu can; -1 neu module auto boot
#define SIM_PWRKEY_ACTIVE_HIGH          1                       // muc kich hoat cho PWRKEY
#define SIM_PWRKEY_HOLD_MS              1200UL                  // thoi gian giu PWRKEY de bat modem
#define APP_RAW_TRUTH_PROBE_INTERVAL_MS 10000UL                 // chu ky lap lai bai truth probe raw

// ================= [NPK SENSOR] =================
#define NPK_TX_PIN      5                   // TX cua ESP noi sang RX cam bien NPK
#define NPK_RX_PIN      4                   // RX cua ESP noi sang TX cam bien NPK
#define NPK_BAUDRATE    4800                // baudrate Modbus/serial cua NPK

// ================= [SHT30 SENSOR] =================
#define SHT30_SDA_PIN   8                   // chan SDA I2C cua SHT30
#define SHT30_SCL_PIN   9                   // chan SCL I2C cua SHT30
#define SHT30_I2C_ADDR  0x44                // dia chi I2C cua SHT30

#define SHT30_READ_MAX_ATTEMPTS   5         // so lan doc lai SHT30 trong 1 chu ky
#define SHT30_RETRY_DELAY_MS      120       // delay giua cac lan doc lai SHT30
#define SHT30_MAX_WAIT_MS         1200      // tong thoi gian toi da cho viec doc SHT30

#endif
