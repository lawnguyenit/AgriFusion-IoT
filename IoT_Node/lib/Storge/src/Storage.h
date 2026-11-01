#ifndef STORGE_H
#define STORGE_H 
#include <Arduino.h>
void setupStorage();
bool storageFileExists(const char *path);
bool saveOfflineData(String dataJson);
void processOfflineData();  

#endif
