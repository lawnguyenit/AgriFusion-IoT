# agrifusion.cloud

## Purpose

`src/agrifusion/cloud` contains shared technical components used
by the ingest stage.

This folder is for infrastructure that may be reused by multiple
stages. It is not a pipeline stage by itself.

## Active Contents

```text
cloud/
`-- firebase_rtdb.py
```

## Boundary

- place shared adapters here
- keep component-specific orchestration and storage logic outside, in the
  owning stage area such as `ingest/`
