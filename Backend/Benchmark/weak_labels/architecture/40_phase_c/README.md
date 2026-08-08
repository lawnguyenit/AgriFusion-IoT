# Phase C — Native Label Assignment

```yaml
status: IMPLEMENTED_NATIVE_RELEASE
authority: LABEL_AUTHORITY
next_consumer: Evaluation
label_authority: true_when_release_published
```

## Nhiệm vụ chính

Phase C là phase đầu tiên được phép tạo label authority. Baseline E1 native
release đã được materialize:

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
train-ready cuối cùng. Release hiện tại có 3291 E1 records, với Point,
Same-Y 3h/8h và Temporal 3h/8h assignments.

Bản draft giải thích chi tiết nine-channel input → derived evidence →
RuleFiring → Resolution → Assignment nằm trong artifact output của semantic
map generator (`semantic_label_draft.md`, `semantic_label_flow.mmd`,
`semantic_label_summary.json`).
