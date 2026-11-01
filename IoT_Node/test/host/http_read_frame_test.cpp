#include "../../lib/SimHttpClient/src/HttpReadFrame.h"
#include <cassert>
#include <iostream>
#include <string>

static std::string decode(const std::string &wire, size_t limit, bool complete = true) {
    HttpReadFrame frame(limit);
    std::string body;
    for (char byte : wire) if (frame.feed(byte)) body += byte;
    assert(frame.done() == complete);
    assert(!frame.failed());
    return body;
}

int main() {
    assert(!httpAtLineMatches("HTTP/1.1 200 OK", "OK"));
    assert(!httpAtLineMatches("X-Result: ERROR", "ERROR"));
    assert(httpAtLineMatches("OK", "OK"));
    assert(httpAtLineMatches("+CME ERROR: 3", "ERROR"));
    assert(httpAtLineMatches("+HTTPACTION: 0,200,2215", "+HTTPACTION:"));
    // A76xx manual: initial OK is an acknowledgement, not end of response.
    assert(decode("\r\nOK\r\n+HTTPREAD: 4\r\nnull\r\n+HTTPREAD: 0\r\n", 512) == "null");
    assert(decode("+HTTPREAD: DATA,4\r\nnull\r\nOK\r\n", 4) == "null");
    std::string opaque = " \r\nOK ERROR +HTTPREAD: 0\r\n ";
    assert(decode("+HTTPREAD: " + std::to_string(opaque.size()) + "\r\n" + opaque + "\r\nOK\r\n", 512) == opaque);
    assert(decode("OK\r\n+HTTPREAD: 9\r\nnull", 512, false) == "null");
    assert(decode("+HTTPREAD: 4\r\nnull", 512, false) == "null");
    assert(decode("OK\r\n", 512, false).empty());
    assert(decode("+HTTPREAD: 0\r\n", 512).empty());
    for (const std::string &wire : {"+HTTPREAD: 513\r\n", "+HTTPREAD: garbage\r\n", "ERROR\r\n"}) {
        HttpReadFrame frame(512);
        for (char byte : wire) frame.feed(byte);
        assert(frame.failed());
    }
    // Spaces, quotes and multibyte UTF-8 can straddle modem chunk boundaries.
    std::string json = "{\"value\":\"" + std::string(500, 'a') + " OK ERROR ";
    json += "\xC4\x91";
    json += std::string(1700, 'b') + "\"}";
    json[511] = json[512] = ' ';
    std::string joined;
    for (size_t pos = 0; pos < json.size(); pos += 512) {
        std::string part = json.substr(pos, 512);
        joined += decode("OK\r\n+HTTPREAD: " + std::to_string(part.size()) + "\r\n" + part + "\r\n+HTTPREAD: 0\r\n", 512);
    }
    assert(joined == json);
    // A modem may return fewer bytes than requested; offset follows actual data.
    assert(decode("+HTTPREAD: 2\r\n{}\r\nOK\r\n", 512) == "{}");
    std::cout << "HTTPREAD framing cases passed (byte-by-byte input and multi-chunk JSON).\n";
}
