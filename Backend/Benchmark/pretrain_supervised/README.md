# Pretrain Supervised Benchmark

## Mục đích

- Giữ toàn bộ flow `embedding pretrain -> downstream supervised` theo version độc lập.
- Mỗi `vN` ăn đúng output của `pretrain` trên schema fuzzy layer tương ứng.

## Layout

- `pretrain/`
  - canonical embedding stage
- `v1/`
  - downstream cho embedding sinh từ `L1`
- `v2/`
  - downstream benchmark runner cho embedding sinh từ `L2`, có output riêng theo `exp1..exp5`
- `v3/`
  - downstream cho embedding sinh từ `L3`
- `v4/`
  - downstream cho embedding sinh từ `L4`

## Contract

- `v1`
  - consume output của `pretrain` khi source là `layer1`
- `v2`
  - consume output của `pretrain` khi source là `layer2_exp1..exp5`
  - tách artifact theo `run -> experiments -> expN -> models`
- `v3`
  - consume output của `pretrain` khi source là `layer3`
- `v4`
  - consume output của `pretrain` khi source là `layer4`

## Giả định xử lý

- Mỗi version giữ schema riêng, không sửa đè schema version cũ.
- Nếu schema input đổi mạnh, pretrain version tương ứng cũng phải đổi contract.
- Downstream version không đọc raw CSV trực tiếp từ fuzzy layer; nó đọc embedding/artifact từ pretrain matching version.

## Rủi ro hoặc giới hạn hiện tại

- `v2/v3/v4` mới được scaffold theo contract; hiện mới có `v1` downstream chạy đầy đủ.
- `tabnet/` chỉ còn vai trò compatibility alias cho command cũ.
