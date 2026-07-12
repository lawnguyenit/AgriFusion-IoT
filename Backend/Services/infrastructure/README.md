# Services Infrastructure

## Purpose

`Backend/Services/infrastructure` contains shared technical components
used by service areas.

This folder is for infrastructure that may be reused by multiple service
components. It is not a pipeline stage by itself.

## Active Contents

```text
infrastructure/
`-- firebase_rtdb.py
```

## Boundary

- place shared adapters here
- keep component-specific orchestration and storage logic outside, in the
  owning service area such as `layer0_ingestion/`
