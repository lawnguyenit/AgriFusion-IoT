# OtaBootGuard

Purpose: protect OTA rollout by tracking pending validation and rollback decisions across boots.

Responsibilities:
- Detect pending-validation boots
- Count repeated boots after OTA
- Trigger rollback when validation exceeds the configured limit
- Confirm a healthy OTA after the runtime marks it stable

Used with:
- `OtaStateStore`
- `OtaManager`
- `OtaRtdbReporter`
