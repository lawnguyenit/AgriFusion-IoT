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
// APP_RUN_CONTINUOUS: luong van hanh chinh cua node. Hien tai de 1 de chay lien tuc.
// APP_SIM_PURE_TEST_MODE: bat khi chi muon test SIM, bo qua toan bo runtime sensor/cloud.
// APP_SHT30_TEST_MODE: bat khi chi muon test rieng SHT30 qua Sht30Service, bo qua runtime chinh.
// APP_RAW_TRUTH_PROBE_MODE: bat khi can bai test raw transport/time cap thap, khong vao flow app that.
#define APP_RUN_CONTINUOUS 0         // 1 = chay lien tuc, 0 = che do wake-do-gui-ngu
#define APP_SIM_PURE_TEST_MODE 0     // 1 = bo qua AppRuntime, chay che do test SIM thuan de chan doan mang
#define APP_SHT30_TEST_MODE 0        // 1 = bo qua AppRuntime, chay che do test rieng SHT30
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
// APP_FIREBASE_SIM_TRANSPORT_ENABLED:
// 1 = ghi RTDB qua HTTP(S) engine cua modem SIM.
// 0 = tat cloud khi dang o SIM mode.
#define APP_FIREBASE_DATABASE_URL      "https://agri-fusion-iot-default-rtdb.asia-southeast1.firebasedatabase.app" // URL RTDB
#define APP_FIREBASE_API_KEY           "AIzaSyAih-kFW-VkgEKVXnTd7aiFCiUjNy-6j18" // API key Firebase client
#define APP_FIREBASE_LEGACY_TOKEN      "wZehBBnCza75i6iNpcUgKQT463dmHXMbfqRuYVsc" // token ghi RTDB dang dung
#define APP_FIREBASE_SIM_TRANSPORT_ENABLED 1                    // 1 = dung RTDB REST qua HTTP(S) engine cua modem; 0 = chan cloud qua SIM

// Cac path duoi day la schema cloud hien tai.
// Neu doi ten node/path tren RTDB thi sua tai day thay vi sua trong code runtime.
#define APP_RTDB_PATH_NODE_ROOT        "/Node1"             // root du lieu cua node tren RTDB
#define APP_RTDB_PATH_NODE_INFO        "/Node1/info"        // metadata thong tin node
#define APP_RTDB_PATH_NODE_LIVE        "/Node1/live"        // du lieu song / telemetry moi nhat
#define APP_RTDB_PATH_NODE_STATUS      "/Node1/status_events" // log trang thai he thong
#define APP_RTDB_PATH_NODE_TELEMETRY   "/Node1/telemetry"   // root telemetry thuc te cua node
#define APP_RTDB_PATH_NODE_TELEMETRY_PROBE "/Node1/telemetry/_write_probe" // path probe quyen ghi telemetry
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
// Day la nhom QUAN TRONG NHAT de dieu chinh nhip hoat dong:
// - APP_SENSOR_SAMPLE_INTERVAL_MS: bao lau do sensor 1 lan.
// - APP_TELEMETRY_SEQUENCE_SLOTS_PER_DAY: so thu tu goi tin trong 1 ngay.
//   Vi du: 24 = 1 gio/lan, 96 = 15 phut/lan, 288 = 5 phut/lan.
// - APP_NODE_INFO_PUSH_INTERVAL_MS: bao lau cap nhat /info 1 lan.
// - APP_OFFLINE_REPLAY_INTERVAL_MS: bao lau thu day lai du lieu dem khi da co mang.
// - APP_TIME_SYNC_RETRY_MS: bao lau thu dong bo gio lai neu van chua co time hop le.
// - APP_NETWORK_LOOP_DELAY_MS: nhip lap task mang; khong phai chu ky lay mau.
// #define APP_SENSOR_SAMPLE_INTERVAL_MS      (2UL * 60UL * 1000UL) // debug nhanh: 2 phut thuc day 1 lan
#define APP_SENSOR_SAMPLE_INTERVAL_MS      (15UL * 60UL * 1000UL) // van hanh that: 15 phut thuc day 1 lan
#define APP_TELEMETRY_SEQUENCE_SLOTS_PER_DAY (24UL * 4UL)         // 96 slot/ngay = 15 phut/slot
#define APP_SENSOR_RETRY_WINDOW_COUNT      3U                     // moi sensor co toi da 3 co hoi tu phuc hoi truoc khi sang buoc mang
#define APP_SENSOR_RETRY_WINDOW_MS         3000UL                 // moi co hoi retry sensor duoc cap cua so 3 giay
#define APP_NETWORK_LOOP_DELAY_MS          250UL                  // nhip lap task mang/cloud de xu ly queue, reconnect, replay
#define APP_OFFLINE_REPLAY_INTERVAL_MS     30000UL                // moi 30s thu day lai du lieu da dem trong flash
#define APP_NODE_INFO_PUSH_INTERVAL_MS     300000UL               // moi 5 phut cap nhat metadata /info
#define APP_TELEMETRY_PROBE_INTERVAL_MS    30000UL                // moi 30s (toi da) probe quyen ghi telemetry neu can
#define APP_TIME_SYNC_RETRY_MS             60000UL                // moi 60s thu dong bo lai gio neu chua sync
#define APP_STATUS_REFRESH_INTERVAL_MS     300000UL               // moi 5 phut refresh trang thai /live/health du khong doi
#define APP_RUNTIME_DIAG_INTERVAL_MS       60000UL                // moi 60s in heartbeat tong quan len serial
#define APP_FIREBASE_REBEGIN_INTERVAL_MS   15000UL                // toi thieu 15s giua 2 lan Firebase begin/re-begin
#define APP_FIREBASE_NOT_READY_LOG_MS      15000UL                // moi 15s in log "Firebase chua ready" 1 lan
#define APP_TRANSPORT_BOOTSTRAP_INTERVAL_MS 15000UL               // toi thieu 15s giua 2 lan bootstrap transport/time
#define APP_TRANSPORT_DIAG_INTERVAL_MS      60000UL               // moi 60s dump chan doan transport neu cloud van loi
#define APP_TELEMETRY_SUCCESS_DIAG_INTERVAL_MS 60000UL            // moi 60s moi ghi telemetry_debug/channel 1 lan khi upload OK
#define APP_SIM_READY_RETRY_INTERVAL_MS     20000UL               // moi 20s hoi lai SIM/cloud da san sang gui chua
#define APP_SIM_READY_MAX_POLLS             7U                    // toi da 7 lan hoi trong 1 phien thuc (~140s)
#define APP_SLEEP_FAIL_RETRY_INTERVAL_MS    (5UL * 60UL * 1000UL) // neu phien gui fail thi ngu lai 5 phut roi thu tiep

// ================= [TASK / BUFFER] =================
// APP_QUEUE_LENGTH va APP_QUEUE_REPLACE_OLDEST_ON_FULL quyet dinh cach xu ly khi sensor tao mau nhanh hon cloud upload.
// Hien tai uu tien GIU MAU MOI NHAT: khi queue day se bo ban tin cu nhat.
#define APP_SENSOR_PAYLOAD_BUFFER_SIZE     2048U                 // kich thuoc toi da cho 1 payload JSON; tang de tranh roi mau khi packet debug vuot 1.5 KB
#define APP_MESSAGE_KIND_BUFFER_SIZE       24U                   // kich thuoc chuoi phan loai payload
#define APP_QUEUE_LENGTH                   10U                   // so ban tin toi da cho trong queue
#define APP_QUEUE_SEND_WAIT_MS             10UL                  // cho toi da 10ms khi sensor task day 1 packet vao queue
#define APP_QUEUE_RECV_WAIT_MS             100UL                 // cho toi da 100ms moi lan network task doi 1 packet tu queue
#define APP_QUEUE_REPLACE_OLDEST_ON_FULL   1                     // 1 = queue day thi bo packet cu nhat, 0 = bo packet moi vua tao
#define APP_PAYLOAD_KIND_NODE_PACKET       "node_packet_json"    // nhan payload thong thuong
#define APP_PAYLOAD_KIND_SENSOR_ALARM      "sensor_alarm_json"   // nhan payload canh bao cam bien

#define APP_SENSOR_TASK_STACK_SIZE         8192U                 // stack cho task doc sensor
#define APP_NETWORK_TASK_STACK_SIZE        16384U                // stack cho task mang/cloud
#define APP_SENSOR_TASK_PRIORITY           1U                    // uu tien task sensor
#define APP_NETWORK_TASK_PRIORITY          2U                    // uu tien task mang cao hon sensor de rut queue kip
#define APP_SENSOR_TASK_CORE               1U                    // core chay task sensor
#define APP_NETWORK_TASK_CORE              0U                    // core chay task mang

// ================= [SENSOR POLICY] =================
#define APP_NPK_FAIL_ALARM_THRESHOLD       3                     // nguong fail lien tiep de danh dau alarm
#define APP_NPK_UART_RESET_FAIL_INTERVAL   2                     // cu bao nhieu lan fail thi reset lai UART NPK
#define APP_SHT30_RETRY_INIT_MS            10000UL               // thoi gian moi lan thu init lai SHT30
#define APP_SHT30_INIT_ATTEMPTS            3U                    // so lan thu init lien tiep moi khi danh thuc/can force init SHT30
#define APP_SHT30_INIT_RETRY_DELAY_MS      180UL                 // do tre giua cac lan init SHT30 trong 1 dot
#define APP_SHT30_FORCE_REINIT_STREAK      2U                    // bao nhieu chu ky doc loi lien tiep thi danh dau can init lai
#define APP_SHT30_WIRE_CLOCK_HZ            100000UL              // toc do I2C cua SHT30
#define APP_SHT30_WIRE_TIMEOUT_MS          20UL                  // timeout I2C
#define APP_SHT30_POST_WIRE_BEGIN_DELAY_MS 30UL                  // cho ngan sau Wire.begin de bus on dinh
#define APP_SHT30_TEST_INTERVAL_MS         5000UL                // chu ky lap lai bai test SHT30
#define APP_SHT30_TEST_BOOT_PROBES         3U                    // so mau test lien tiep ngay sau boot de bat loi startup
#define APP_SHT30_TEST_BOOT_DELAY_MS       1000UL                // khoang cach giua cac mau boot test SHT30

// ================= [LOG LABELS] =================
#define APP_LOG_SYS_TAG        "[SYS]"      // nhan log he thong
#define APP_LOG_SENSOR_TAG     "[SENSOR]"   // nhan log cam bien
#define APP_LOG_NET_TAG        "[NET]"      // nhan log mang
#define APP_LOG_CLOUD_TAG      "[CLOUD]"    // nhan log Firebase/cloud
#define APP_LOG_OTA_TAG        "[OTA]"      // nhan log cap nhat firmware

// ================= [SIM PINS / MODEM] =================
// Day la nhom tham so de doi nha mang / module / cach cap nguon modem.
// Thuong chi can sua: SIM_APN, SIM_PDP_TYPE, cac chan nguon/PWRKEY, va cac timeout boot neu module kho len.
#define SIM_TX_PIN      17                  // TX cua ESP noi sang RX cua SIM
#define SIM_RX_PIN      16                  // RX cua ESP noi sang TX cua SIM
#define SIM_BAUDRATE    115200              // baudrate UART giao tiep voi SIM
#define SIM_GSM_PIN     ""                  // ma PIN cua SIM neu nha mang yeu cau
#define SIM_APN         "v-internet"        // APN cua nha mang
#define SIM_APN_USER    ""                  // username APN
#define SIM_APN_PASS    ""                  // password APN
#define SIM_PDP_TYPE    "IP"                // kieu PDP context hien tai; co the thu "IPV4V6" neu can

#define SIM_BOOT_WAIT_MS                5000                    // cho sau khi cap nguon modem truoc khi bat dau noi chuyen
#define SIM_AT_READY_RETRY_COUNT        12                      // so lan probe AT truoc khi ket luan modem chua san sang
#define SIM_AT_READY_RETRY_DELAY_MS     250                     // khoang cach giua cac lan probe AT
#define SIM_AT_RESPONSE_TIMEOUT_MS      5000                    // timeout cho 1 lenh AT/1 phan hoi quan trong
#define SIM_DEBUG_RECHECK_DELAY_MS      1000                    // delay khi debug va kiem tra lai SIM
#define SIM_NETWORK_CHECK_INTERVAL_MS   10000                   // moi 10s check lai snapshot mang SIM
#define SIM_RECONNECT_INTERVAL_MS       30000                   // moi 30s thu reconnect packet data neu can
#define SIM_RESTART_COOLDOWN_MS         300000                  // toi thieu 5 phut giua 2 lan restart modem
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
#define SIM_PWRKEY_HOLD_MS              1200UL                  // giu PWRKEY bao lau de danh thuc/bat modem
#define APP_RAW_TRUTH_PROBE_INTERVAL_MS 10000UL                 // chu ky lap lai bai truth probe raw

// ================= [NPK SENSOR] =================
#define NPK_TX_PIN      5                   // TX cua ESP noi sang RX cam bien NPK
#define NPK_RX_PIN      4                   // RX cua ESP noi sang TX cam bien NPK
#define NPK_BAUDRATE    4800                // baudrate Modbus/serial cua NPK

// ================= [SHT30 SENSOR] =================
#define SHT30_SDA_PIN   8                   // chan SDA I2C cua SHT30
#define SHT30_SCL_PIN   9                   // chan SCL I2C cua SHT30
#define SHT30_I2C_ADDR  0x44                // dia chi I2C cua SHT30

#define SHT30_READ_MAX_ATTEMPTS   3         // so lan doc lai SHT30 trong 1 chu ky
#define SHT30_RETRY_DELAY_MS      900       // delay giua cac lan doc lai SHT30
#define SHT30_MAX_WAIT_MS         3000      // tong thoi gian toi da cho viec doc SHT30

#endif
