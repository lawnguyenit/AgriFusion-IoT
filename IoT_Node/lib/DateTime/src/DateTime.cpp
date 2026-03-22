#include "DateTime.h"

#include <time.h>
#include <sys/time.h>

#include "Config.h"

#define TINY_GSM_MODEM_A7672X
#include <TinyGsmClient.h>
extern TinyGsm modem;

bool syncTimeFromSIM() {
    CUS_DBG("[TIME] Dang lay gio tu mang di dong...");

    String timeStr = modem.getGSMDateTime(DATE_FULL);
    if (timeStr.length() < 10) {
        CUS_DBGLN(" -> Loi: Khong lay duoc gio!");
        return false;
    }

    int year = timeStr.substring(0, 2).toInt() + 2000;
    int month = timeStr.substring(3, 5).toInt();
    int day = timeStr.substring(6, 8).toInt();
    int hour = timeStr.substring(9, 11).toInt();
    int min = timeStr.substring(12, 14).toInt();
    int sec = timeStr.substring(15, 17).toInt();

    struct tm tmv = {};
    tmv.tm_year = year - 1900;
    tmv.tm_mon = month - 1;
    tmv.tm_mday = day;
    tmv.tm_hour = hour;
    tmv.tm_min = min;
    tmv.tm_sec = sec;

    time_t t = mktime(&tmv);
    struct timeval now = {.tv_sec = t, .tv_usec = 0};
    settimeofday(&now, NULL);

    CUS_DBGF(" -> Da dong bo: %02d/%02d/%d %02d:%02d:%02d\n", day, month, year, hour, min, sec);
    return true;
}

String getCurrentTimeStr() {
    time_t now;
    struct tm timeinfo;
    time(&now);
    localtime_r(&now, &timeinfo);

    char buffer[30];
    snprintf(buffer, sizeof(buffer), "%04d-%02d-%02d %02d:%02d:%02d",
             timeinfo.tm_year + 1900, timeinfo.tm_mon + 1, timeinfo.tm_mday,
             timeinfo.tm_hour, timeinfo.tm_min, timeinfo.tm_sec);

    return String(buffer);
}
