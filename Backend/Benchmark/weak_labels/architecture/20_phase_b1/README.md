# Phase B1 — Q×K Candidate Decision Pack

```yaml
status: PARTIAL
authority: CANDIDATE_ONLY
next_consumer: B2
label_authority: false
```

## Nhiệm vụ chính

B1 đọc candidate từ Phase A và phân tích tác động của threshold Q kết hợp với
persistence K.

```text
Q candidate
  → LOW flags
  → low runs
  → K candidates
  → Q×K geometry
  → fold/support projection
  → Decision Pack
```

B1 không tự chọn `primary Q/K` và không tạo label release.

## Giới hạn hiện tại

Q×K geometry và fold-support đã có. Anchor/purge safety và distribution audit
đầy đủ cho B2 vẫn là phần cần hoàn thiện.
