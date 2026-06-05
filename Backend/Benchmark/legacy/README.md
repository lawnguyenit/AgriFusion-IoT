# Legacy

## Mục đích

Namespace này đánh dấu các benchmark family không còn nằm trong active architecture.

Theo định hướng hiện tại, các nhánh sau được xem là legacy:

- `pretrain_supervised/`
- `tabpfn_benchmark/`
- `ft_transformer_benchmark/` với vai trò benchmark family riêng

## Quy ước sử dụng

- Không thêm dependency active mới trỏ vào các family legacy.
- Không dùng legacy code làm owner cho model, label policy, artifact helper hoặc split policy active.
- Historical outputs và code cũ vẫn được giữ nguyên để đối chiếu hoặc đọc artifact cũ khi cần.

## Giới hạn hiện tại

- Ở vòng refactor này, một số tree legacy vẫn được giữ nguyên đường dẫn vật lý để tránh làm gãy toàn bộ historical tooling và import path cũ ngoài scope active.
- Trạng thái legacy được enforced chủ yếu bằng dependency cleanup, README, và shared owner mới trong `shared/` và `models/`.
