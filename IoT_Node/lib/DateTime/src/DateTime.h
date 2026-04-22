#ifndef DATE_TIME_H
#define DATE_TIME_H

#include <Arduino.h>

bool syncTimeFromSIM();
bool syncTimeFromHttpHeader(const String &header);
bool syncTimeFromHttpDate();
bool timeLooksSane();
String getCurrentTimeStr();

#endif
