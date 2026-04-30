# Layer 1 Rules

Mục tiêu của thư mục này là biến sample đầu vào của `npk`, `sht30`, `meteo` thành các signal có thể debug và tái lập.

## Đọc file theo thứ tự nào

Không nên đọc `reference.py` từ trên xuống ngay từ đầu. Cách nhanh hơn:

1. Đọc `config.py` để biết rule nào tồn tại và ngưỡng của nó.
2. Đọc một wrapper như `sht30.py` để biết source đó gọi engine với config nào.
3. Chạy `debug.py` để xem output rút gọn.
4. Chỉ mở `reference.py` khi cần sửa công thức fuzzy, trend hoặc accumulation.

## Vai trò từng file

```text
config.py      Lưu tham số rule, alias field, window và ruleset version.
reference.py   Engine dùng chung: normalize, fuzzy, trend, accumulation.
npk.py         API xử lý riêng cho NPK.
sht30.py       API xử lý riêng cho SHT30.
meteo.py       API xử lý riêng cho Meteo.
debug.py       Helper để in nhanh kết quả cần xem khi debug.
```

## Debug nhanh một sample

```python
from Backend.Benchmark.rules.layer1.debug import (
    evaluate_source_sample,
    summarize_result,
    explain_signal,
)

result = evaluate_source_sample(
    "sht30",
    {
        "sht_temp_c": 31,
        "sht_hum_pct": 90,
        "ts": 1000,
    },
)

print(summarize_result(result))
print(explain_signal(result, "air_humidity_wet_leaning"))
```

## Cách đọc output

Một signal có 4 phần chính:

```text
rule           Tham số rule được dùng để tính.
value          Giá trị hiện tại sau khi normalize input.
fuzzy          Mức lệch khỏi vùng bình thường và risk score.
trend          Xu hướng so với sample trước và các window 3h/8h/12h/24h.
accumulation   Tích lũy áp lực theo thời gian.
```

Các field debug quan trọng:

```text
ruleset_version          Version của bộ rule đang dùng.
debug.rule_names         Danh sách rule đã chạy.
debug.field_aliases      Cách map input thô sang field chuẩn.
debug.history_sample_count
debug.normalized_record_count
```

## Khi kết quả sai thì kiểm tra ở đâu

```text
Sai value/perception       Kiểm tra alias trong config.py.
Sai ngưỡng/risk            Kiểm tra SignalRule trong config.py.
Sai trend                  Kiểm tra history có ts đúng không.
Sai accumulation           Kiểm tra khoảng thời gian và sample_count trong output.
Sai riêng một source       Kiểm tra wrapper npk.py/sht30.py/meteo.py.
Sai công thức chung        Kiểm tra reference.py.
```
