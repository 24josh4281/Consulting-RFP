# G2B Environmental Coverage and 17:00 Briefing Report

> **Outcome**: Local implementation and safe validation complete; external credentials remain intentionally unconfigured.
>
> **Date**: 2026-09-18

## Work Completed

- Expanded the 나라장터 **용역** connector's climate profile to include environmental consulting signals.
- Replaced the retired G2B OpenAPI URL with the current official service endpoint and parameter name.
- Added parsing for the official nested item response structure and clear handling of official API errors.
- Changed the daily briefing setting from 18:00 to **17:00 Korea time**.
- Preserved the Friday weekly digest at 18:00 Korea time.
- Updated the active 30-minute Codex heartbeat and Windows task-installation defaults.

## Quality Evidence

- 25 automated tests passed.
- Python modules compiled successfully.
- Both notification PowerShell scripts parsed successfully.
- A no-key request reached the current G2B authentication gate (`SERVICE_KEY_IS_NULL`) rather than the previous retired-route error.
- A notification-cycle dry run collected/reported safely and sent no email.

## Production Readiness

| Capability | State | Dependency |
|---|---|---|
| GIR public notices and public RFP links | Available | None beyond normal public access |
| G2B service notice collection | Configured, waiting | `DATA_GO_KR_SERVICE_KEY` |
| Immediate and daily/weekly email | Configured, blocked | SMTP configuration and one approved test email |
| Daily 17:00 digest condition | Active in Codex heartbeat | Credentials must be ready before a send occurs |

## Recommended Activation Order

1. Put the approved public-data key in the ignored `.env` file as `DATA_GO_KR_SERVICE_KEY=...`.
2. Run `powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\run_live_g2b_check.ps1 -Days 3` and review the resulting dashboard/RFP document list.
3. Configure SMTP in `.env`, run one explicit test email, then allow the 30-minute heartbeat to send new-notice alerts and the 17:00 digest.
4. Review the first 1–2 weeks of environmental candidates before changing keyword rules.

## Residual Risks

- The current scope is G2B **service** notices, not every goods or construction operation.
- Environmental keywords can still surface borderline operational notices; the dashboard's human review step remains required.
- No external key, SMTP credential, Windows task, email, or Git push was performed in this increment.
