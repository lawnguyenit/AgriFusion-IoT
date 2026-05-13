# V2

## Mục đích

- Consume embedding/artifact sinh từ `pretrain` khi source thuộc `Layer2`.
- Dùng để benchmark riêng cho các schema `exp1..exp5` mà không làm bẩn `v1`.

## Input

- Embedding/pretrain artifact từ:
  - `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\pretrain`
- Source fuzzy tương ứng:
  - `layer2_exp1`
  - `layer2_exp2`
  - `layer2_exp3`
  - `layer2_exp4`
  - `layer2_exp5`

## Output

- `D:\AgriFusion-IoT\Backend\Benchmark\pretrain_supervised\v2\outputs\<run_id>\`

## Command

- Chưa có command downstream chuẩn ở bước này.
- Trước hết cần chọn rõ:
  - model head nào
  - label policy nào
  - có fine-tune encoder hay chỉ train head

## Giả định xử lý

- `v2` chỉ consume pretrain output của đúng schema `Layer2`.
- Không dùng chung checkpoint `v1` nếu feature schema đã đổi.

## Rủi ro hoặc giới hạn hiện tại

- Mới scaffold contract, chưa có pipeline downstream đầy đủ như `v1`.
