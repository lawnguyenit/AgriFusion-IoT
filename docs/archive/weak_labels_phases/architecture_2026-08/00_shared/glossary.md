# Phần chung — Glossary

| Thuật ngữ | Nghĩa |
|---|---|
| `canonical record` | Observation sau Layer1 normalization |
| `environment` | Nhóm protocol/telemetry như E1, E2, E3 |
| `evidence` | Giá trị quan sát hoặc derived value cho rule |
| `Q05/Q10/Q15/Q20` | Quantile candidate, không phải label |
| `threshold value` | Giá trị số sinh ra từ một Q candidate |
| `low run` | Chuỗi observation thỏa LOW và strict continuity |
| `K` | Số observation liên tiếp cần cho persistence candidate |
| `anchor` | Observation đủ dependency history để đánh giá target |
| `RuleFiring` | Một rule được đánh giá trên một sample |
| `Resolution` | Kết quả kết hợp nhiều RuleFiring |
| `Assignment` | Label assignment có semantic và provenance |
| `semantic contract` | Bộ quyết định đã freeze cho Phase C |
| `train-ready` | Kết quả sau khi Evaluation ghép label, feature, fold/purge |

`low run` và `anchor` là khái niệm phân tích thời gian; chúng chưa tự động là
hiện tượng vật lý hoặc nhãn cuối.
