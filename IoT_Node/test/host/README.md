# HTTPREAD framing regression checks

Compile and run `http_read_frame_test.cpp` on a host C++ compiler (C++14 or later).
The test includes the actual production decoder without Arduino mocks.

From a Visual Studio x64 Native Tools prompt at repository root:

```bat
cl /nologo /EHsc /std:c++14 /W4 /WX /Fe:IoT_Node\.pio\host\http_read_frame_test.exe /Fo:IoT_Node\.pio\host\http_read_frame_test.obj IoT_Node\test\host\http_read_frame_test.cpp
IoT_Node\.pio\host\http_read_frame_test.exe
```

Create the ignored `.pio/host` output directory first. With GCC or Clang, compile
the same source using `-std=c++14 -Wall -Wextra -Werror` and run the result.

Cases also reject HTTP status/header text as AT terminal tokens. Cases include initial OK before data, DATA headers, zero trailers, trailing OK,
opaque OK/ERROR text, exact whitespace at 512-byte boundaries, UTF-8, long JSON,
short chunks, truncated frames, errors and invalid/oversize declarations. Input
arrives one byte at a time. Physical UART/SHT30/Firebase validation is separate.
