#pragma once

#include <stddef.h>
#include <stdlib.h>
#include <string.h>

inline bool httpAtLineMatches(const char *line, const char *pattern) {
    if (strcmp(line, pattern) == 0) return true;
    if (strcmp(pattern, "ERROR") == 0 && strncmp(line, "+CME ERROR:", 11) == 0) return true;
    size_t length = strlen(pattern);
    return length > 0 && pattern[length - 1] == ':' && strncmp(line, pattern, length) == 0;
}

// A76xx may acknowledge HTTPREAD with OK BEFORE the length header/data.
// Payload bytes are opaque: neither whitespace nor OK/ERROR are delimiters.
class HttpReadFrame {
public:
    explicit HttpReadFrame(size_t limit) : _limit(limit) {}

    bool feed(char value) {
        if (_done || _failed) return false;
        if (_reading) {
            if (++_received == _length) _reading = false;
            return true;
        }
        if (value == '\r') return false;
        if (value != '\n') {
            if (_used + 1 >= sizeof(_line)) _failed = true;
            else _line[_used++] = value;
            return false;
        }
        _line[_used] = '\0';
        if (strcmp(_line, "ERROR") == 0 || strncmp(_line, "+CME ERROR:", 11) == 0) {
            _failed = true;
        } else if (_haveHeader) {
            if (strcmp(_line, "OK") == 0 || strcmp(_line, "+HTTPREAD: 0") == 0) _done = true;
        } else if (strncmp(_line, "+HTTPREAD:", 10) == 0) {
            const char *number = _line + 10;
            while (*number == ' ') ++number;
            if (strncmp(number, "DATA,", 5) == 0) number += 5;
            while (*number == ' ') ++number;
            char *end = nullptr;
            unsigned long length = strtoul(number, &end, 10);
            while (*end == ' ') ++end;
            if (end == number || *end != '\0' || length > _limit) _failed = true;
            else {
                _haveHeader = true;
                _length = static_cast<size_t>(length);
                _reading = _length > 0;
                _done = _length == 0;
            }
        }
        _used = 0;
        return false;
    }

    bool done() const { return _done; }
    bool failed() const { return _failed; }
    size_t received() const { return _received; }

private:
    size_t _limit, _length = 0, _received = 0, _used = 0;
    char _line[128] = {};
    bool _haveHeader = false, _reading = false, _done = false, _failed = false;
};
