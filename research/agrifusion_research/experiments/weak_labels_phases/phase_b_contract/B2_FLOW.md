# Phase B2 — Review và Freeze

```text
B1 Decision Pack
    + Phase A threshold lineage
    + Anchor/purge safety audit
    + Q×K×fold distribution audit
    + Human review decision
            ↓
        B2 preflight
            ↓ fail closed nếu thiếu/không đạt
    Semantic contract assembly
            ↓
    NativeContract.load validation
            ↓
    Atomic publication
            ↓
    Frozen child Protocol Registry
            ↓
    Phase C được phép đọc contract
```

B2 không tạo point/temporal labels, không fit threshold, không chạy model và
không đọc E2/E3 sensitive payload. Q/K, ontology, resolver, derived evidence,
continuity, window và support policy đều phải đến từ input đã review; B2 không
được tự điền mặc định.

Nếu B1 chưa cung cấp anchor safety hoặc distribution audit, B2 tạo staging
status `CONTRACT_FREEZE_BLOCKED` và không tạo frozen contract hay child registry.
