# Pretrain Supervised

## Mục đích

`pretrain_supervised/` hiện là family legacy.

Nó được giữ lại để:

- tra cứu historical experiments
- đọc output cũ
- đối chiếu với giai đoạn trước khi kiến trúc benchmark được rút gọn

Nó không còn là dependency owner cho:

- model active
- label policy active
- split policy active
- artifact helper active

## Input

- historical benchmark datasets và checkpoint cũ của chính family này

## Output

- historical pretrain/downstream outputs đã tồn tại sẵn trong tree này

Refactor hiện tại không xóa các output đó.

## Command

Không có command active nào mới nên được trỏ vào family này.

Nếu cần đọc lại run cũ, dùng đúng script historical tương ứng và chấp nhận rằng contract có thể khác contract active hiện tại.

## Giả định

- family này chỉ còn phục vụ audit, so sánh và tham chiếu lịch sử
- active modules phải dùng `Backend/Benchmark/shared` và `Backend/Benchmark/models` thay vì import ngược vào đây

## Rủi ro / giới hạn

- đường dẫn vật lý vẫn được giữ nguyên ở vòng này để tránh phá historical tooling ngoài scope active
- nhiều README/script con trong tree này vẫn phản ánh kiến trúc cũ và chưa được dọn toàn bộ
