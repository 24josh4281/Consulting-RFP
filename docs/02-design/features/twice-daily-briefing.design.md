# Twice-Daily Climate RFP Briefing Design

> **Date**: 2026-09-21

## Delivery Model

```text
notifications.local.json: daily_send_times = [10:00, 17:00]
        │
        ├── Windows task / monitor at 10:00 → --mode daily --daily-slot 10:00
        └── Windows task / monitor at 17:00 → --mode daily --daily-slot 17:00
        │
SQLite delivery keys: YYYY-MM-DD-1000 / YYYY-MM-DD-1700
```

Each slot has its own delivery key and subject line. The existing per-recipient delivery log remains the authoritative duplicate check. Immediate alerts and the Friday 18:00 weekly digest are unchanged.

## Compatibility and Safety

- Older local files with `daily_send_at` continue to work as a one-slot schedule.
- With more than one configured slot, a command must name `--daily-slot`; this prevents an accidental send at an unclear time.
- No scheduler is installed and no real email is sent as part of this implementation. The existing SMTP readiness gate remains in force.
