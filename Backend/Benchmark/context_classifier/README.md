# Context Classifier

## Mục đích

`context_classifier/` hiện là tree legacy của giai đoạn benchmark augmented/context-specific.

Nó được giữ lại để:

- đọc historical run cũ
- đối chiếu với giai đoạn còn dùng synthetic augmentation
- tái sử dụng một số tooling report/scientific artifact khi cần

## Trạng thái hiện tại

- không còn là family train active chính
- flow active `real-only` đã được đưa về `direct_benchmark/`
- `binary`, `tri_class`, `four_class` không còn bị chia tách theo family này

## Input / Output

Historical inputs/outputs trong tree này vẫn được giữ nguyên trên đĩa.

Refactor hiện tại không xóa các run cũ.

## Giới hạn

- nhiều script trong tree này vẫn phản ánh logic augmented cũ
- chỉ nên dùng khi cần đối chiếu historical artifact, không nên dùng làm lane train active mới
