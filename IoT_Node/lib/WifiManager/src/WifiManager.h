#ifndef WIFIMANAGER_H
#define WIFIMANAGER_H

#include <Arduino.h>
#include <WiFi.h> // Thư viện Wifi chuẩn cho ESP32

// ================= [CẤU HÌNH WIFI] =================
// Thay đổi tên và mật khẩu Wifi của bạn tại đây
#define WIFI_SSID "YOUR_WIFI_SSID" // local value excluded from backup
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD" // local value excluded from backup

// Thời gian chờ kết nối tối đa khi khởi động (giây)
#define WIFI_TIMEOUT_MS 20000 

// ================= [KHAI BÁO HÀM] =================
bool setupWifi();       // Hàm khởi động và kết nối lần đầu
void checkWifi(); // Hàm kiểm tra trạng thái kết nối Wifi
void printWifiInfo();   // Hàm in thông tin mạng (IP, MAC, RSSI)

#endif
