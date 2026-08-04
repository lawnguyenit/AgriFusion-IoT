# Phase C — Native Label Assignment

```yaml
status: PARTIAL
authority: LABEL_AUTHORITY
next_consumer: Evaluation
label_authority: true_when_release_published
```

## Nhiệm vụ chính

Phase C là phase đầu tiên được phép tạo label authority:

```text
Layer1 E1 canonical evidence
  + frozen B2 contract
  → continuity
  → derived evidence
  → rule evaluation
  → point resolution
  → temporal resolution
  → Point/Temporal Assignment
```

Phase C không tự chọn lại Q/K, không fit threshold, không đọc E2/E3 sensitive
payload trong E1 release, không ghép feature Dataset Views và không quyết định
train-ready cuối cùng.
