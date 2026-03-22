#ifndef WIFIMANAGER_H
#define WIFIMANAGER_H

#include <Arduino.h>
#include <WiFi.h> // Thư viện Wifi chuẩn cho ESP32

// ================= [CẤU HÌNH WIFI] =================
// Thay đổi tên và mật khẩu Wifi của bạn tại đây
#define WIFI_SSID       "3 DUOI"
#define WIFI_PASSWORD   "44440000"

// Thời gian chờ kết nối tối đa khi khởi động (giây)
#define WIFI_TIMEOUT_MS 20000 

// ================= [KHAI BÁO HÀM] =================
bool setupWifi();       // Hàm khởi động và kết nối lần đầu
void checkWifi(); // Hàm kiểm tra trạng thái kết nối Wifi
void printWifiInfo();   // Hàm in thông tin mạng (IP, MAC, RSSI)

#endif
