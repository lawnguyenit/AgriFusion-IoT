# Phase B1 — Q×K Candidate Decision Pack

```yaml
status: IMPLEMENTED_CANDIDATE_PACK_REVIEW_REQUIRED
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
  → Q×K intrinsic geometry
  → anchor dependency/purge safety
  → boundary audit
  → post-admissibility distribution
  → Decision Pack
```

B1 không tự chọn `primary Q/K` và không tạo label release.

## Giới hạn hiện tại

Q×K geometry, interval-safe anchor/purge audit, boundary simulation và
post-admissibility distribution audit đã có. B1 vẫn không tự dịch boundary,
không tự chọn primary Q/K và chưa tạo label authority; B2/human review là nơi
quyết định tiếp theo.
