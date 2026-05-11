# Giải thích `Series`, `index` và `to_numpy()`

Ví dụ:

```python
indexed = pd.Series(pd.to_numeric(series, errors="coerce").to_numpy(), index=datetime_index)
```

## Mục đích của dòng này

- Lấy giá trị số từ `series`
- Bỏ `index` cũ của `series`
- Gắn lại `index` thời gian mới là `datetime_index`

## `Series` là gì

`Series` trong pandas là một dãy dữ liệu 1 chiều có `index` đi kèm.

Nó có thể đóng vai trò:

- một cột dữ liệu
- một dòng dữ liệu

Tùy ngữ cảnh:

- `obj["col"]` thường trả về một `Series`
- `obj.loc[row]` cũng có thể trả về một `Series`
- `obj.iloc[pos]` cũng có thể trả về một `Series`

## `index` là gì

`index` là nhãn định danh cho từng phần tử trong `Series`.

Nó không phải giá trị dữ liệu chính, mà là metadata đi kèm để:

- ghép dữ liệu
- sắp xếp dữ liệu
- rolling theo thời gian
- align theo nhãn

## Vì sao cần `to_numpy()`

Nếu truyền một `Series` trực tiếp vào `pd.Series(...)`, pandas có thể cố giữ hoặc align theo `index` cũ.

Khi dùng:

```python
pd.to_numeric(series, errors="coerce").to_numpy()
```

ta đang nói với pandas rằng:

- chỉ lấy giá trị thuần
- bỏ toàn bộ `index` cũ
- tránh align nhầm theo nhãn cũ

Sau đó `index=datetime_index` sẽ là index thật sự được dùng trong phép tính mới.

## Có `to_numpy()` và không có `to_numpy()`

### Có `to_numpy()`

```python
indexed = pd.Series(
    pd.to_numeric(series, errors="coerce").to_numpy(),
    index=datetime_index,
)
```

Kết quả:

- giá trị được giữ theo thứ tự
- `index` cũ bị bỏ
- `datetime_index` được gắn lại sạch sẽ

### Không có `to_numpy()`

```python
indexed = pd.Series(pd.to_numeric(series, errors="coerce"), index=datetime_index)
```

Pandas có thể hiểu đây là một `Series` có `index` riêng và cố align theo nhãn cũ.  
Trong bài toán rolling theo thời gian, điều này dễ làm lệch ý đồ xử lý.

## Trong `rolling_time_slope`

Hàm `rolling_time_slope` nhận:

- một `Series` giá trị
- một `timestamp_index`

Sau đó pandas sẽ:

- quét từng cửa sổ thời gian
- truyền từng window vào callback `_fit(window)`
- tính slope cho window đó

Đoạn này:

```python
x = (numeric_window.index - numeric_window.index[0]).total_seconds() / 3600.0
```

có nghĩa là:

- lấy các mốc thời gian trong window
- đổi về số giờ tương đối
- mốc đầu window là `0.0`

## Điều cần nhớ

- `Series` không tự là dòng hay cột, nó chỉ là chuỗi 1 chiều
- `index` là nhãn đi kèm với chuỗi đó
- `to_numpy()` dùng để bỏ index cũ, giữ lại giá trị thuần
- `datetime_index` mới là index có ý nghĩa cho phép tính rolling theo thời gian

## Ghi chú cho người đọc sau

Nếu cần debug:

- xem `series` ban đầu có index gì
- xem `datetime_index` đã đúng thứ tự chưa
- kiểm tra output có bị align sai hoặc `NaN` bất thường không
- nhớ rằng `to_numpy()` không làm mất dữ liệu, nó chỉ bỏ nhãn cũ
