# Notification and Official Source Readiness Design Document

> **Summary**: A pragmatic local notification layer that turns collected notices into deduplicated email alerts and scheduled briefings.
>
> **Project**: Climate RFP Tracker
> **Version**: 0.2.0-draft
> **Author**: Codex
> **Date**: 2026-09-18
> **Status**: Approved for implementation by the requested continuation
> **Planning Doc**: `docs/01-plan/features/notification-and-official-source-readiness.plan.md`

---

## Context Anchor

| Key | Value |
|-----|-------|
| **WHY** | Reduce missed qualified opportunities without losing original source evidence or sending duplicate alerts. |
| **WHO** | ESG/climate consulting practitioners using the local tracker. |
| **RISK** | API/SMTP configuration gaps and public portal changes. |
| **SUCCESS** | Testable, deduplicated immediate/daily/weekly messages that only mark delivery after SMTP success. |
| **SCOPE** | Briefing output, SQLite delivery state, SMTP transport, scheduler scripts, and P0 source visibility. |

---

## 1. Overview

### 1.1 Design Goals

- Keep collection, report generation, and mail delivery independent.
- Avoid external dependencies and keep secrets outside Git.
- Use the existing SQLite database so a restart cannot resend successfully delivered mail.
- Allow an email preview/dry-run before any external delivery.

### 1.2 Design Principles

- Official-source-first collection.
- Delivery success is explicit; a failed attempt stays retryable.
- Historical data is not automatically presented as newly detected.
- Human review status never changes automatically.

---

## 2. Architecture Options

| Criteria | Option A: Minimal | Option B: Clean | Option C: Pragmatic |
|----------|:-:|:-:|:-:|
| Approach | Inline SMTP in CLI | New service layers and provider SDK | Separate briefing/notification modules with existing SQLite |
| New files | 1 | 6+ | 3-4 |
| Modified files | 2 | 7+ | 5-6 |
| Complexity | Low | High | Medium |
| Maintainability | Low | High | High |
| External dependency | None | Provider-specific | None |
| Recommendation | Not selected | Later hosted product | **Selected** |

**Selected**: Option C — it gives durable delivery state and clear module boundaries without prematurely replacing the existing local MVP.

### 2.1 Component Diagram

```text
Official API / Official board
            |
        fetchers.py
            |
      SQLite notices + attachments
        |                 |
   briefing.py       notifications.py
        |                 |
 HTML / Markdown        SMTP sender
        \               /
        PowerShell alert-cycle scripts
```

### 2.2 Data Flow

```text
Scheduled run → sync sources → store only relevant notices → create reports/briefing
              → find unnotified eligible rows → render email → SMTP send
              → record successful delivery key
```

The daily scheduler runs at 17:00 Asia/Seoul. The weekly Friday summary remains scheduled for 18:00 Asia/Seoul. The 나라장터 service source reads a limited number of official API pages and applies the environment/climate/GHG/ETS filter locally so keyword changes remain traceable in `configs/keywords.json`.

### 2.3 Dependencies

| Component | Depends On | Purpose |
|-----------|------------|---------|
| `briefing.py` | `storage.py`, `documents.py` | Build consultant-facing action queues. |
| `notifications.py` | `storage.py`, `briefing.py`, stdlib SMTP | Decide what to send and deliver it safely. |
| `run_notification_cycle.ps1` | CLI commands | Orchestrate periodic local operations. |
| `install_notification_tasks.ps1` | Windows Task Scheduler | Register schedules only after a successful test. |

---

## 3. Data Model

### 3.1 Entity Definition

```text
NotificationDelivery
  notification_type: immediate | daily | weekly | test
  notification_key: notice ID or date/week key
  recipient: email address
  status: sent | failed
  subject: rendered subject
  sent_at: local timestamp only after SMTP success
  error: safe exception summary, never a password

NotificationSetting
  setting_key: notification_baseline_at or other operational state
  setting_value: ISO timestamp/value
```

### 3.2 Entity Relationships

```text
notices (1) ── (N) notification_deliveries
notification_settings stores the starting baseline for new-notice alerts
```

### 3.3 Database Schema

```sql
CREATE TABLE notification_deliveries (
  id INTEGER PRIMARY KEY,
  notification_type TEXT NOT NULL,
  notification_key TEXT NOT NULL,
  notice_id INTEGER,
  recipient TEXT NOT NULL,
  subject TEXT NOT NULL,
  status TEXT NOT NULL,
  sent_at TEXT,
  error TEXT NOT NULL DEFAULT '',
  UNIQUE(notification_type, notification_key, recipient)
);
```

---

## 4. CLI Specification

| Command | Purpose | External side effect |
|---------|---------|----------------------|
| `briefing` | Generate HTML/Markdown briefing | Files only |
| `notifications status` | Show SMTP and baseline readiness | None |
| `notifications init` | Establish safe new-alert baseline | SQLite only |
| `notifications dispatch --mode …` | Preview payload and candidate count (the default without `--send`) | None |
| `notifications dispatch --mode … --send` | Send through configured SMTP | Email + SQLite log |
| `notifications dispatch --mode test --send` | Send a clearly labelled setup test | Email + SQLite log |

---

## 5. UI/UX Design

No browser UI is added in this cycle. The user-facing surfaces are the existing reports, the new `briefing.html`, and plain-language CLI output.

---

## 6. Error Handling

| Condition | Handling |
|-----------|----------|
| Missing SMTP configuration | Show exact missing variable names; do not attempt delivery. |
| First alert-cycle run | Set baseline and return without treating pre-existing notices as new. |
| SMTP connection/auth failure | Record a failed attempt, return non-zero, and retain retry eligibility. |
| Already delivered key | Skip quietly and report duplicate prevention. |
| No new eligible notice | Do not send an empty immediate email. |
| Source failure | Existing sync run records the failure; mail cycle stops rather than claiming success. |

---

## 7. Security Considerations

- SMTP password appears only in `.env`, which is ignored by Git.
- No secret appears in HTML, Markdown, console output, delivery rows, or test fixtures.
- TLS uses STARTTLS by default; implicit SSL is configurable for providers that require it.
- Public sources remain the default. Private sources are not activated by the scheduler.

---

## 8. Test Plan

| Area | Scenario | Expected result |
|------|----------|-----------------|
| Keyword filter | A climate-adjacent excluded notice contains `청소`. | It is not considered relevant or stored by fetchers. |
| Baseline | First immediate dispatch runs on pre-existing notices. | Baseline is set; no historical immediate email is sent. |
| De-duplication | Same notice is dispatched twice after one success. | Second run has zero outgoing candidates. |
| Daily key | Daily dispatch repeats on one date. | Only one successful delivery key per recipient/date. |
| Failure | Fake SMTP sender raises. | Failure is recorded and the key remains retryable. |
| Briefing | Mixed notices include documents and a near deadline. | HTML/Markdown expose action count, deadline, and document gaps. |
| Source config | P0 official board entries are listed but remain disabled in shared config. | Default sample test stays deterministic. |

---

## 9. Layer Assignment

| Component | Layer | Location |
|-----------|-------|----------|
| `Notice`, delivery records | Domain/data | `models.py`, `storage.py` |
| Briefing selection/rendering | Application | `briefing.py` |
| SMTP adapter | Infrastructure | `notifications.py` |
| CLI and PowerShell | Presentation/orchestration | `cli.py`, `scripts/` |

---

## 10. Conventions

| Item | Convention Applied |
|------|-------------------|
| Modules | lowercase Python names, standard library first |
| Timestamps | ISO-8601 with Asia/Seoul rendered for user-facing briefings |
| Secrets | environment variables only |
| Errors | concise Korean operator message and safe stored error text |
| Tests | `unittest` plus dependency-injected fake SMTP sender |

---

## 11. Implementation Guide

### 11.1 File Structure

```text
rfp_tracker/
  briefing.py
  notifications.py
  storage.py
  cli.py
scripts/
  run_notification_cycle.ps1
  install_notification_tasks.ps1
```

### 11.2 Implementation Order

1. Add source exclusion configuration and tests.
2. Add briefing generation.
3. Add SQLite notification state/delivery helpers.
4. Add SMTP rendering/delivery and CLI commands.
5. Add runner/scheduler scripts and local configuration examples.
6. Run fixture, dry-run, and failure-path tests.

### 11.3 Session Guide

| Module | Scope Key | Description | Estimated Turns |
|--------|-----------|-------------|:---------------:|
| Noise and briefing | `module-1` | Exclusions and daily report | 1 |
| Delivery engine | `module-2` | Storage, SMTP, CLI, tests | 2 |
| Operations | `module-3` | Source catalog, PowerShell, docs | 1 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-09-18 | Initial pragmatic local-service design | Codex |
