#include "Storage.h"
#include "Config.h" // Bắt buộc phải có để dùng chế độ DEBUG
#include <FS.h>
#include <LittleFS.h>
#include <Arduino.h>
void setupStorage() {
    // Mount file system
    if(!LittleFS.begin(true)) { // true = format nếu lỗi
        CUS_DBGLN("[STORAGE] Chua co LittleFS -> Dang Format tao moi...");
        return;
    }
    CUS_DBGLN("[STORAGE] LittleFS Mount OK");
}

bool storageFileExists(const char *path) {
    if (!path || !*path) {
        return false;
    }

    File file = LittleFS.open(path, FILE_READ);
    if (!file) {
        return false;
    }

    file.close();
    return true;
}

bool saveOfflineData(String dataJson) {
    File file = LittleFS.open("/offline_data.txt", FILE_APPEND); 
    if(!file){
        CUS_DBGLN("[STORAGE] LOI: Khong mo duoc file de ghi!");
        return false;
    }
    
    file.println(dataJson); 
    file.close();
    
    CUS_DBGLN("[STORAGE] -> Da luu data vao Flash ");
    return true;
}

void processOfflineData() {
    // Kiểm tra xem file có tồn tại không
    if (!storageFileExists("/offline_data.txt")) {
        CUS_DBGLN("[STORAGE] Khong co file offline de xu ly.");
        return;
    }

    // Mở file để đọc
    File file = LittleFS.open("/offline_data.txt", FILE_READ);
    CUS_DBGLN("[STORAGE] Phat hien du lieu cu -> Dang gui bu...");
    
    while(file.available()){
        String line = file.readStringUntil('\n');
        
        // --- ĐOẠN NÀY SAU NÀY SẼ GỌI HÀM MQTT ĐỂ GỬI ---
        CUS_DBGF("[STORAGE] Re-sending: %s\n", line.c_str());
        // mqttClient.publish("topic/data", line.c_str());
        
        delay(100);
    }
    file.close();
    
    // Gửi xong thì xóa file đi cho sạch bộ nhớ
    LittleFS.remove("/offline_data.txt");
    CUS_DBGLN("[STORAGE] -> Da gui het va xoa file offline.");
}
