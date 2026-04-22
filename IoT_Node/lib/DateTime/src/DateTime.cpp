#include "DateTime.h"

#include <time.h>
#include <sys/time.h>

#include "Config.h"
#include "SimA7680C.h"
#include "SimHttpClient.h"
#include "SimSocketTransport.h"

namespace {
bool isValidSimClock(const String &timeStr) {
    if (timeStr.length() < 17) {
        return false;
    }

    int year = timeStr.substring(0, 2).toInt();
    int month = timeStr.substring(3, 5).toInt();
    int day = timeStr.substring(6, 8).toInt();
    int hour = timeStr.substring(9, 11).toInt();
    int minute = timeStr.substring(12, 14).toInt();
    int second = timeStr.substring(15, 17).toInt();

    return year >= 24 && year <= 45 &&
           month >= 1 && month <= 12 &&
           day >= 1 && day <= 31 &&
           hour >= 0 && hour <= 23 &&
           minute >= 0 && minute <= 59 &&
           second >= 0 && second <= 59;
}

bool applyTime(int year, int month, int day, int hour, int min, int sec) {
    struct tm tmv = {};
    tmv.tm_year = year - 1900;
    tmv.tm_mon = month - 1;
    tmv.tm_mday = day;
    tmv.tm_hour = hour;
    tmv.tm_min = min;
    tmv.tm_sec = sec;

    time_t t = mktime(&tmv);
    if (t <= 0) {
        return false;
    }

    struct timeval now = {.tv_sec = t, .tv_usec = 0};
    settimeofday(&now, nullptr);
    return true;
}

int monthFromHttpToken(const String &token) {
    if (token == "Jan") return 1;
    if (token == "Feb") return 2;
    if (token == "Mar") return 3;
    if (token == "Apr") return 4;
    if (token == "May") return 5;
    if (token == "Jun") return 6;
    if (token == "Jul") return 7;
    if (token == "Aug") return 8;
    if (token == "Sep") return 9;
    if (token == "Oct") return 10;
    if (token == "Nov") return 11;
    if (token == "Dec") return 12;
    return 0;
}

String extractHttpDateLine(const String &header) {
    int start = header.indexOf("Date:");
    if (start < 0) {
        return "";
    }
    int end = header.indexOf('\n', start);
    String line = end >= 0 ? header.substring(start, end) : header.substring(start);
    line.trim();
    return line;
}

bool parseHttpDateLine(const String &line,
                       int &year,
                       int &month,
                       int &day,
                       int &hour,
                       int &minute,
                       int &second) {
    if (!line.startsWith("Date:")) {
        return false;
    }

    String body = line.substring(5);
    body.trim();

    int comma = body.indexOf(',');
    if (comma >= 0) {
        body = body.substring(comma + 1);
        body.trim();
    }

    int p1 = body.indexOf(' ');
    if (p1 < 0) return false;
    int p2 = body.indexOf(' ', p1 + 1);
    if (p2 < 0) return false;
    int p3 = body.indexOf(' ', p2 + 1);
    if (p3 < 0) return false;
    int p4 = body.indexOf(' ', p3 + 1);
    if (p4 < 0) return false;

    day = body.substring(0, p1).toInt();
    month = monthFromHttpToken(body.substring(p1 + 1, p2));
    year = body.substring(p2 + 1, p3).toInt();
    String timePart = body.substring(p3 + 1, p4);

    if (month == 0 || year < 2024) {
        return false;
    }

    int c1 = timePart.indexOf(':');
    int c2 = timePart.indexOf(':', c1 + 1);
    if (c1 < 0 || c2 < 0) {
        return false;
    }

    hour = timePart.substring(0, c1).toInt();
    minute = timePart.substring(c1 + 1, c2).toInt();
    second = timePart.substring(c2 + 1).toInt();

    return day >= 1 && day <= 31 &&
           hour >= 0 && hour <= 23 &&
           minute >= 0 && minute <= 59 &&
           second >= 0 && second <= 59;
}
}  // namespace

bool syncTimeFromSIM() {
    CUS_DBG("[TIME] Dang lay gio tu dong ho mang cua modem...");

    String timeStr = simReadNetworkTimeRaw();
    if (!isValidSimClock(timeStr)) {
        CUS_DBGF(" -> Bo qua CCLK invalid: %s\n", timeStr.c_str());
        return false;
    }

    int year = timeStr.substring(0, 2).toInt() + 2000;
    int month = timeStr.substring(3, 5).toInt();
    int day = timeStr.substring(6, 8).toInt();
    int hour = timeStr.substring(9, 11).toInt();
    int min = timeStr.substring(12, 14).toInt();
    int sec = timeStr.substring(15, 17).toInt();

    if (!applyTime(year, month, day, hour, min, sec)) {
        CUS_DBGLN(" -> Khong apply duoc CCLK vao he thong.");
        return false;
    }

    CUS_DBGF(" -> Da dong bo tu CCLK: %02d/%02d/%d %02d:%02d:%02d\n",
             day, month, year, hour, min, sec);
    return true;
}

bool syncTimeFromHttpHeader(const String &header) {
    String dateLine = extractHttpDateLine(header);
    int year = 0;
    int month = 0;
    int day = 0;
    int hour = 0;
    int minute = 0;
    int second = 0;

    if (!parseHttpDateLine(dateLine, year, month, day, hour, minute, second)) {
        CUS_DBGF("[TIME] Khong parse duoc Date header: %s\n", dateLine.c_str());
        return false;
    }

    if (!applyTime(year, month, day, hour, minute, second)) {
        CUS_DBGLN("[TIME] Khong apply duoc HTTP Date vao he thong.");
        return false;
    }

    CUS_DBGF("[TIME] Da dong bo tu HTTP Date: %02d/%02d/%d %02d:%02d:%02d UTC\n",
             day, month, year, hour, minute, second);
    return true;
}

bool syncTimeFromHttpDate() {
    CUS_DBG("[TIME] Dang lay gio tu HTTP Date header...");

    SimHttpClient http;
    SimHttpRequest request;
    request.method = SimHttpMethod::Get;
    request.url = APP_SIM_HTTP_PROBE_URL;
    request.readHeader = true;
    request.readBody = false;
    request.actionTimeoutMs = 30000;

    SimHttpResponse response;
    if (!http.perform(request, response)) {
        CUS_DBGF(" -> Loi probe HTTP modem: %s / %s\n",
                 response.stage.c_str(),
                 response.detail.c_str());
        return false;
    }

    return syncTimeFromHttpHeader(response.header);
}

bool timeLooksSane() {
    time_t now = time(nullptr);
    return now >= 1700000000;
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
