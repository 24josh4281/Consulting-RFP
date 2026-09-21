# Twice-Daily Climate RFP Briefing Plan

> **Objective**: Deliver the climate, GHG, ETS, and environmental-consulting briefing at **10:00** and **17:00 Korea time** each day, without allowing one delivery to suppress the other.
>
> **Date**: 2026-09-21

## Current Situation

The tracker previously stored one daily send time and used a date-only delivery key. A successful 10:00 delivery would therefore make a 17:00 delivery appear to be a duplicate.

## Plan

1. Replace the one-time daily setting with a list of daily time slots: `10:00` and `17:00`.
2. Record daily deliveries with a date-and-slot key, while retaining old single-time local configuration compatibility.
3. Require an explicit daily slot whenever two slots are configured.
4. Register two separate Windows tasks and update the 30-minute monitoring automation to call the correct slot.
5. Verify with automated tests and parser checks only; do not send live email or call an external source API during this schedule change.

## Success Criteria

- Both 10:00 and 17:00 daily briefings can be sent on the same date.
- Re-running the same slot is skipped by SQLite delivery state.
- The scheduler exposes separate 10:00 and 17:00 tasks.
- SMTP readiness and human approval remain required before any real email is sent.
