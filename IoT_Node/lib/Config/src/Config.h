#ifndef CONFIG_H
#define CONFIG_H

// ================= [C???U H??NH CH??? ?????] =================
#define DEBUG_MODE 1
// ESP32-S3 in this project uses native USB CDC for the monitor port.
#define DEBUG_PORT Serial

// Chon kenh mang chinh: 0 = WiFi, 1 = SIM 4G (A7680C)
#define USE_SIM_NETWORK 1

#if DEBUG_MODE
// In log ra Serial Monitor
  #define CUS_DBG(...) DEBUG_PORT.print(__VA_ARGS__)
  #define CUS_DBGLN(...) DEBUG_PORT.println(__VA_ARGS__)
  #define CUS_DBGF(...) DEBUG_PORT.printf(__VA_ARGS__)
#else 
// Gửi log lên server từ xa 
  #define CUS_DBG(...)
  #define CUS_DBGLN(...)
  #define CUS_DBGF(...)
#endif
// ================== [CHÂN KẾT NỐI] ===================
//Chân module sim SIMA7680C
#define SIM_TX_PIN      17
#define SIM_RX_PIN      16
#define SIM_BAUDRATE    115200
#define SIM_GSM_PIN     ""
#define SIM_APN         "v-internet"
#define SIM_APN_USER    ""
#define SIM_APN_PASS    ""

// SIM power-saving/reconnect policy (debug-friendly)
#define SIM_BOOT_WAIT_MS                5000
#define SIM_AT_READY_RETRY_COUNT        12
#define SIM_AT_READY_RETRY_DELAY_MS     250
#define SIM_NETWORK_CHECK_INTERVAL_MS   10000
#define SIM_RECONNECT_INTERVAL_MS       30000
#define SIM_RESTART_COOLDOWN_MS         300000

//Chân kết nối cảm biến NPK
#define NPK_TX_PIN      5   // chân vàng
#define NPK_RX_PIN      4   //chân xanh
#define NPK_BAUDRATE    4800 

//Chân kết nối cảm biến SHT30
#define SHT30_SDA_PIN   8 // chân vàng 
#define SHT30_SCL_PIN   9 // chân trắng
#define SHT30_I2C_ADDR  0x44

// SHT30 retry policy (bounded retry, no infinite wait)
#define SHT30_READ_MAX_ATTEMPTS   5
#define SHT30_RETRY_DELAY_MS      120
#define SHT30_MAX_WAIT_MS         1200

#endif
