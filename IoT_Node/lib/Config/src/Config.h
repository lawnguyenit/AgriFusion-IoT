#ifndef CONFIG_H
#define CONFIG_H

#if __has_include("Config.private.h")
  #include "Config.private.h"
#else
  #include "Config.private.example.h"
#endif

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
// Current deployment profile: wake, measure, send/buffer, then deep-sleep.
// APP_RUN_CONTINUOUS can still be enabled for a continuous bench profile.
// APP_RUN_CONTINUOUS: 1 = chay lien tuc, 0 = wake-do-gui-ngu.
// APP_SIM_PURE_TEST_MODE: bat khi chi muon test SIM, bo qua toan bo runtime sensor/cloud.
// APP_SHT30_TEST_MODE: bat khi chi muon test rieng SHT30 qua Sht30Service, bo qua runtime chinh.
// APP_DS18B20_TEST_MODE: bat khi chi muon test rieng DS18B20 qua OneWire, bo qua runtime chinh.
// APP_SOIL_MOISTURE_TEST_MODE: bat khi chi muon test moisture sensor v1.2 analog.
// APP_ALL_SENSORS_TEST_MODE: bat khi test serial-only toan bo NPK, moisture, DS18B20, SHT30.
// APP_RAW_TRUTH_PROBE_MODE: bat khi can bai test raw transport/time cap thap, khong vao flow app that.
#define APP_RUN_CONTINUOUS 0         // 1 = chay lien tuc, 0 = che do wake-do-gui-ngu
#define APP_SIM_PURE_TEST_MODE 0     // 1 = bo qua AppRuntime, chay che do test SIM thuan de chan doan mang
#define APP_SHT30_TEST_MODE 0        // 1 = bo qua AppRuntime, chay che do test rieng SHT30
#define APP_DS18B20_TEST_MODE 0      // 1 = bo qua AppRuntime, chay che do test rieng DS18B20
#define APP_SOIL_MOISTURE_TEST_MODE 0 // 1 = bo qua AppRuntime, chay che do test moisture rieng
#define APP_ALL_SENSORS_TEST_MODE 0   // production AppRuntime path
#define APP_RAW_TRUTH_PROBE_MODE 0   // 1 = chay harness raw transport/time, 0 = de du phong cho app runtime sau nay

#if (APP_SIM_PURE_TEST_MODE + APP_SHT30_TEST_MODE + APP_DS18B20_TEST_MODE + APP_SOIL_MOISTURE_TEST_MODE + APP_ALL_SENSORS_TEST_MODE + APP_RAW_TRUTH_PROBE_MODE) > 1
  #error "Chi duoc bat mot che do diagnostic/test tai mot thoi diem"
#endif

// ================= [NODE IDENTITY] =================
#define APP_NODE_SLOT_KEY              "Node2"              // key dinh danh node trong app/cloud
#define APP_NODE_ID                    "Node2"              // id node dung trong payload va cloud
#define APP_NODE_NAME                  "Vuon sau rieng A"   // ten hien thi cua node
#define APP_NODE_SITE_ID               "Binh Phu, Vinh Long" // vi tri/cum trien khai
#define APP_NODE_DEVICE_UID            "esp32s3_node2"      // uid thiet bi phan biet voi cac node khac
#define APP_NODE_POWER_TYPE            "solar_battery"      // kieu nguon cap de dua len metadata
#define APP_NODE_TIMEZONE              "Asia/Ho_Chi_Minh"   // timezone dang text de luu metadata
#define APP_NODE_TZ_CONFIG             "ICT-7"              // chuoi cau hinh timezone cho NTP
#define APP_TELEMETRY_RETENTION_DAYS   30                   // so ngay metadata/telemetry duoc danh dau luu tru
#define APP_BOARD_MODEL                "ESP32-S3"           // model board hien tai
#define APP_SIM_MODULE_MODEL           "A7682S"             // model module SIM hien tai
#define APP_CONFIG_VERSION             "cfg_v2"             // version config runtime duoc build cung firmware
#define APP_CALIBRATION_VERSION        "calib_v2"           // phien ban calibration cong khai, khong mo ta cach sensor tao EC

// Canonical sensor registry ids/types used in schema v2.
#define APP_SENSOR_ID_SHT30            "air_sht30_01"
#define APP_SENSOR_ID_SOIL_7IN1        "soil_7in1_01"
#define APP_SENSOR_TYPE_SHT30          "air_temp_humidity"
#define APP_SENSOR_TYPE_SOIL_7IN1      "soil_multi_sensor"

// ================= [FIREBASE / RTDB] =================
// APP_FIREBASE_SIM_TRANSPORT_ENABLED:
// 1 = ghi RTDB qua HTTP(S) engine cua modem SIM.
// 0 = tat cloud khi dang o SIM mode.
#define APP_FIREBASE_SIM_TRANSPORT_ENABLED 1                    // 1 = dung RTDB REST qua HTTP(S) engine cua modem; 0 = chan cloud qua SIM

// Cac path duoi day la schema cloud hien tai.
// Neu doi ten node/path tren RTDB thi sua tai day thay vi sua trong code runtime.
#define APP_RTDB_PATH_NODE_ROOT        "/Node2"             // root du lieu cua node tren RTDB
#define APP_RTDB_PATH_NODE_INFO        "/Node2/info"        // metadata tinh do admin ghi tay
#define APP_RTDB_PATH_NODE_LATEST      "/Node2/latest/current" // ban ghi moi nhat, tuong thich latest/current cua Node1
#define APP_RTDB_PATH_NODE_LATEST_META "/Node2/latest/meta" // metadata dieu phoi latest cho Backend/Layer0
#define APP_RTDB_PATH_NODE_TELEMETRY   "/Node2/telemetry"   // root telemetry thuc te cua node
#define APP_RTDB_PATH_NODE_TELEMETRY_PROBE "/debug/Node2/telemetry_probe" // path probe/debug khong chen vao canonical telemetry
#define APP_RTDB_PATH_NODE_DEBUG_ROOT  "/debug/Node2"       // root debug/ops phu tro
#define APP_RTDB_PATH_NODE_DEBUG_STATUS "/debug/Node2/status" // snapshot trang thai runtime de debug
#define APP_RTDB_PATH_NODE_DEBUG_TELEMETRY "/debug/Node2/telemetry" // debug channel cho publish/replay
#define APP_RTDB_PATH_NODE_NPK_TEST     "/debug/Node2/npk_test/latest" // ban ghi test canonical NPK, khong vao telemetry chinh
#define APP_OFFLINE_RAW_FILE           "/offline_data.txt"  // file dem khi mat mang
// Production khong ghi snapshot/trang thai vao nhanh /debug. Bat lai tam
// thoi khi can chan doan cloud; serial log van hoat dong theo DEBUG_MODE.
#define APP_RTDB_DEBUG_PUBLISH_ENABLED 0                    // 0 = tat ghi RTDB debug, 1 = cho phep ghi debug

// ================= [EDGE METADATA] =================
#define APP_EDGE_SYSTEM_NPK            "soil_npk_edge"      // ten nhom he thong cho cam bien NPK
#define APP_EDGE_SYSTEM_ID_NPK         "edge_npk"           // id he thong NPK trong payload
#define APP_EDGE_SYSTEM_SHT            "air_climate_edge"   // ten nhom he thong cho SHT30
#define APP_EDGE_SYSTEM_ID_SHT         "edge_sht30"         // id he thong SHT30 trong payload

// ================= [OTA] =================
#define APP_RTDB_PATH_OTA_STATUS       "/ops/Node1/ota_state" // path ghi trang thai OTA hien tai
#define APP_RTDB_PATH_OTA_HISTORY      "/debug/Node1/ota_events" // path luu lich su su kien OTA
#define APP_RTDB_PATH_OTA_COMMAND      "/control/Node1/ota_commands" // path doc lenh OTA tu cloud

#define APP_OTA_POLL_INTERVAL_MS       60000UL              // chu ky kiem tra lenh OTA
#define APP_OTA_CONFIRM_HEALTH_MS      60000UL              // thoi gian node phai chay on truoc khi confirm OTA
#define APP_OTA_MAX_PENDING_BOOTS      3UL                  // so lan boot toi da khi OTA dang cho xac nhan

// ================= [TASK / APP TIMING] =================
// Day la nhom QUAN TRONG NHAT de dieu chinh nhip hoat dong:
// - APP_SENSOR_SAMPLE_INTERVAL_MS: bao lau do sensor 1 lan.
// - APP_TELEMETRY_SEQUENCE_SLOTS_PER_DAY: so thu tu goi tin trong 1 ngay.
//   Vi du: 24 = 1 gio/lan, 96 = 15 phut/lan, 288 = 5 phut/lan.
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
#define APP_TELEMETRY_PROBE_INTERVAL_MS    30000UL                // moi 30s (toi da) probe quyen ghi telemetry neu can
#define APP_TIME_SYNC_RETRY_MS             60000UL                // moi 60s thu dong bo lai gio neu chua sync
#define APP_STATUS_REFRESH_INTERVAL_MS     300000UL               // moi 5 phut refresh debug status du khong doi
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
#define APP_SENSOR_PAYLOAD_BUFFER_SIZE     4096U                 // kich thuoc du cho node packet + raw/error diagnostics trong continuous queue
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
#define APP_SHT30_WIRE_CLOCK_HZ            10000UL               // low-speed I2C da dung o phase 1, phu hop day dai
#define APP_SHT30_WIRE_TIMEOUT_MS          20UL                  // timeout I2C
#define APP_SHT30_POST_WIRE_BEGIN_DELAY_MS 100UL                 // phase 1 cho bus on dinh sau Wire.begin
#define APP_SHT30_SOFT_RESET_WAIT_MS       10UL                  // cho sau lenh soft reset 0x30A2
#define APP_SHT30_MEASUREMENT_WAIT_MS      20UL                  // cho conversion sau lenh 0x2400
#define APP_SHT30_RETRY_SETTLE_DELAY_MS    20UL                  // cho them truoc retry sau reset
#define APP_SHT30_TEST_INTERVAL_MS         5000UL                // chu ky lap lai bai test SHT30
#define APP_SHT30_TEST_BOOT_PROBES         10U                   // so lan init+probe bat buoc lien tiep trong 1 dot
#define APP_SHT30_TEST_BOOT_DELAY_MS       300UL                 // khoang cach ngan giua cac lan init lien tiep
#define APP_SHT30_TEST_RAW_READ_COUNT      6U                    // so lan doc raw lien tiep sau khi bus phan hoi
#define APP_SHT30_TEST_RAW_READ_DELAY_MS   500UL                 // khoang cach giua cac raw read
#define APP_SHT30_TEST_SCAN_FULL_BUS       1                     // 1 = scan 0x03..0x77, 0 = chi ping 0x44/0x45
#define APP_SHT30_TEST_ALT_ADDR            0x45                  // dia chi thay the chi dung de chan doan

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
#define SIM_APN         "m9-itelecom"       // APN cua nha mang iTel
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
#define NPK_BAUDRATE    9600                // baudrate Modbus/serial da xac nhan qua matrix
#define NPK_MODBUS_SLAVE_ID 1U              // dia chi slave da xac nhan co phan hoi
#define NPK_REG_PH       0x0006U             // holding register pH da xac nhan co frame hop le
#define NPK_REG_NPK      0x001EU             // holding register bat dau N/P/K da xac nhan co frame hop le
#define NPK_REG_NPK_COUNT 3U                 // N, P, K
// Node2 production dung map sparse da xac nhan. Map phase 1 van duoc giu lai
// trong thu vien/matrix de tai kiem chung khi thay sensor profile khac, nhung
// khong probe trong moi wake cycle de tranh mat them thoi gian/pin.
#define NPK_LEGACY_FULL_MAP_ENABLED 0
#define NPK_LEGACY_FULL_MAP_START   0x0000U
#define NPK_LEGACY_FULL_MAP_COUNT   7U

// ================= [NPK DERIVED VALUES] =================
// Node2 khong phan hoi o cac thanh ghi EC/nhiet/do am rieng. Khi N/P/K da
// doc thanh cong, dung he so fit tu Layer1 de ghi EC proxy truc tiep vao
// npk.ec. Phan output cong khai giu cung hinh dang EC cua giai doan 1.
#define NPK_EC_INFERENCE_ENABLED              1
#define NPK_EC_INFERENCE_FORMULA_VERSION      "layer1_node1_multivariate_v1"
#define NPK_EC_INFERENCE_INTERCEPT            104.537608f
#define NPK_EC_INFERENCE_N_COEFFICIENT        0.33430017f
#define NPK_EC_INFERENCE_P_COEFFICIENT        0.92924061f
#define NPK_EC_INFERENCE_K_COEFFICIENT        0.99130859f

// Khi mot kenh co frame hop le nhung kenh khac (vi du pH) khong dat validity,
// van giu cac gia tri da xac nhan trong sensor_record.values; kenh khong hop
// le duoc ghi null va trang thai van nam trong read_status.
#define APP_PUBLISH_PARTIAL_SENSOR_VALUES     1

// Day la mien du lieu Node1 dung de danh dau canh bao khi Node2 nam ngoai
// mien hieu chinh. Khong chan viec tinh EC; chi de hien thi trong log/payload.
#define NPK_EC_CALIBRATION_N_MIN              1
#define NPK_EC_CALIBRATION_N_MAX              195
#define NPK_EC_CALIBRATION_P_MIN              50
#define NPK_EC_CALIBRATION_P_MAX              496
#define NPK_EC_CALIBRATION_K_MIN              42
#define NPK_EC_CALIBRATION_K_MAX              492

// Thiet bi hien tai khong co frame nhiet/do am dat rieng. Humidity van giu
// bang 0 de giu schema on dinh; DS18B20 co the bo sung lai soil temperature.
#define NPK_UNSUPPORTED_SOIL_CLIMATE_AS_ZERO  1

// ================= [SHT30 SENSOR] =================
#define SHT30_SDA_PIN   6                   // chan SDA I2C cua SHT30
#define SHT30_SCL_PIN   7                   // chan SCL I2C cua SHT30
#define SHT30_I2C_ADDR  0x44                // dia chi I2C cua SHT30

#define SHT30_READ_MAX_ATTEMPTS   3         // so lan doc lai SHT30 trong 1 chu ky
#define SHT30_RETRY_DELAY_MS      900       // delay giua cac lan doc lai SHT30
#define SHT30_MAX_WAIT_MS         3000      // tong thoi gian toi da cho viec doc SHT30

// ================= [MOISTURE SENSOR V1.2] =================
// Assumption for this temporary test: capacitive analog module with VCC/GND/AOUT.
// GPIO1 is an unused ESP32-S3 ADC input in the current Node2 pin allocation.
#define SOIL_MOISTURE_ADC_PIN             1U
#define SOIL_MOISTURE_TEST_INTERVAL_MS    1000UL
#define SOIL_MOISTURE_SAMPLE_COUNT        32U
#define SOIL_MOISTURE_SAMPLE_GAP_MS       2U
// Provisional relative profile, not field calibration or VWC. The official
// example uses 520/260 on a 10-bit Arduino ADC. These are scaled to 12-bit
// ESP32 ADC values (approximately 1041/2082) and their direction follows the
// observed unit, whose raw value increased when placed in water. The observed
// 920/2525 values are not used as calibration endpoints.
#define SOIL_MOISTURE_CALIBRATION_IS_DEFAULT 1
#define SOIL_MOISTURE_CALIBRATION_PROFILE "manufacturer_example_scaled_12bit_direction_adjusted"
#define SOIL_MOISTURE_CALIBRATION_SOURCE  "manufacturer_two_point_relative_provisional"
#define SOIL_MOISTURE_MANUFACTURER_DRY_10BIT 520
#define SOIL_MOISTURE_MANUFACTURER_WET_10BIT 260
#define SOIL_MOISTURE_AIR_ADC             1041
#define SOIL_MOISTURE_WATER_ADC           2082
#define SOIL_MOISTURE_PIPELINE_ENABLED    1
#define SOIL_MOISTURE_CALIBRATION_TARGET_DEPTH_CM 10.0f
#define SOIL_MOISTURE_INSTALL_DEPTH_CM_MIN 10.0f
#define SOIL_MOISTURE_INSTALL_DEPTH_CM_MAX 15.0f
#define APP_ALL_SENSORS_TEST_INTERVAL_MS  5000UL

// ================= [DS18B20 SENSOR] =================
// GPIO21 la GPIO I/O thuong, khong trung UART NPK (4/5), I2C SHT30 (6/7),
// hay UART SIM (16/17) tren profile ESP32-S3-DevKitC-1 hien tai.
#define DS18B20_DATA_PIN              21
#define DS18B20_PIPELINE_ENABLED      1
#define DS18B20_TEST_INTERVAL_MS      3000UL
#define DS18B20_CONVERSION_WAIT_MS    750UL
#define DS18B20_RETRY_INIT_MS         10000UL
#define DS18B20_READ_MAX_ATTEMPTS     1U
#define DS18B20_RETRY_DELAY_MS        100UL
#define DS18B20_MAX_WAIT_MS           2000UL
#define DS18B20_MAX_DEVICES           4U
#define DS18B20_USE_INTERNAL_PULLUP   1
#define DS18B20_USE_STRONG_PULLUP     1
#define DS18B20_BUS_PRECHARGE_US      20U
#define DS18B20_SINGLE_DROP_FALLBACK   1

#endif
