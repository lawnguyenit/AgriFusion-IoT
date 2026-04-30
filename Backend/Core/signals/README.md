# Core signals

Thư mục này chứa các feature sinh tín hiệu sau khi dữ liệu đã được chuẩn hóa bởi
`Core/processors`.

## Vai trò

- `processors`: đọc raw payload, chuẩn hóa field, tính memory window và continuity.
- `signals`: đọc snapshot canonical của Layer 2 và sinh tín hiệu diễn giải.
- `fuzzy_signals`: so giá trị hiện tại với normal range/threshold, sinh risk score,
  trend semantic và tích lũy áp lực theo rule.

`Benchmark/rules/fuzzy_signals` chỉ còn là wrapper dùng lại module này, để logic rule
không bị nhân đôi ở hai nơi.
