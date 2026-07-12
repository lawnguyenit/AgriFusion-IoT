# Core Infrastructure

## Purpose

`Backend/Core/infrastructure` contains shared technical components used
by Core stages.

This folder is for infrastructure that may be reused by multiple Core
stages. It is not a pipeline stage by itself.

## Active Contents

```text
infrastructure/
`-- firebase_rtdb.py
```

## Boundary

- place shared adapters here
- keep component-specific orchestration and storage logic outside, in the
  owning stage area such as `layer0/`
