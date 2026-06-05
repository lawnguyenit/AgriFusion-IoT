# TabPFN Benchmark

## Mục đích

`tabpfn_benchmark/` hiện là family legacy.

Nó được giữ lại chỉ để:

- đọc lại historical TabPFN experiments
- đối chiếu artifact cũ với kiến trúc benchmark mới

`TabPFN` không còn nằm trong active experiment suite.

## Input

- historical tabular benchmark datasets và checkpoint/config cũ của family này

## Output

- historical run folders và report folders đã tồn tại sẵn trong tree này

Refactor hiện tại không xóa các output đó.

## Command

Không có command active nào mới nên được thêm cho family này.

## Giả định

- active context/direct benchmark chỉ còn dùng `xgboost`, `tabnet_classifier`, `ft_transformer_classifier`
- mọi dependency active mới phải tránh import vào `tabpfn_benchmark`

## Rủi ro / giới hạn

- historical tooling trong tree này vẫn phản ánh contract cũ
- physical move sang namespace legacy riêng chưa được làm trong vòng này để tránh phá historical usage ngoài flow active
