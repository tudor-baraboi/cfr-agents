# PRD: FingerprintJS Daily Quota System

**Date:** January 24, 2026  
**Status:** In Progress

## Overview

Replace trial codes with FingerprintJS visitor identification and Azure Table Storage for persistent daily quota tracking. Each visitor gets 15 free queries per day (resets at midnight UTC). Admin access via `?admin=ADMIN-TUDOR` URL parameter. Display remaining quota as subtle text above the input box.

## Implementation Steps

### 1. Add dependencies
- Add `@fingerprintjs/fingerprintjs` to `frontend/package.json`
- Add `azure-data-tables>=12.4.0` to `backend/requirements.txt`

### 2. Create Azure Table usage tracker
- Add new `backend/app/services/usage.py` with `UsageTracker` class
- Use Azure Table Storage (`DailyUsage` table)
- Schema: `PartitionKey=YYYY-MM-DD`, `RowKey=fingerprint`, `RequestCount`, timestamps
- Reuse existing `faaagentcache` storage account connection string

### 3. Add fingerprint auth endpoint
- In `auth.py`, create `POST /auth/fingerprint` that accepts `{visitor_id}`
- Check daily quota from Azure Table
- Return JWT with `fingerprint` claim and usage stats
- Update `config.py` with `daily_request_limit: int = 15`

### 4. Update WebSocket for fingerprint auth
- In `main.py`, extract `fingerprint` from JWT
- Check/increment daily quota via `UsageTracker`
- Send `quota_update` event after each turn
- Keep admin bypass logic

### 5. Create fingerprint utility in frontend
- Add `frontend/src/fingerprint.ts`
- Initialize FingerprintJS open source
- Cache visitor ID in sessionStorage
- Export `getVisitorId()` async function

### 6. Replace Login with auto-auth + admin param
- In `Login.tsx`, auto-authenticate using fingerprint on mount
- Show code entry form only when `?admin=ADMIN-TUDOR` URL param present
- Update `App.tsx` to parse URL param

### 7. Update types and WebSocket handler
- In `types.ts` and `websocket.ts`, handle `quota_update` event
- Update `requestsUsed`/`requestsRemaining` in real-time

### 8. Add quota display above input
- In `App.tsx`, show subtle text like "12 of 15 queries remaining today" above message input
- Hide for admin users
- Show "Come back tomorrow!" when exhausted

### 9. Remove old trial code infrastructure
- Clean up `TRIAL_CODES` usage
- Remove `code_usage`/`generated_codes` tables from `database.py`
- Remove generate-code endpoint
- Keep `ADMIN_CODES` for admin auth

## Technical Details

### Azure Table Schema

| Property | Type | Description |
|----------|------|-------------|
| `PartitionKey` | string | Date in format `YYYY-MM-DD` |
| `RowKey` | string | FingerprintJS visitor ID |
| `RequestCount` | int | Number of requests made today |
| `FirstRequestAt` | datetime | Timestamp of first request today |
| `LastRequestAt` | datetime | Timestamp of most recent request |

### JWT Token Structure (New)

```json
{
  "fingerprint": "visitor_id_here",
  "is_admin": false,
  "exp": "...",
  "iat": "..."
}
```

### WebSocket Events (New)

```json
{
  "type": "quota_update",
  "requests_used": 5,
  "requests_remaining": 10
}
```

## Design Decisions

1. **FingerprintJS Open Source** - Free, ~60% accuracy. Acceptable for free tier, can upgrade to Pro if abuse occurs.
2. **Admin access via URL param** - `?admin=ADMIN-TUDOR` shows code entry form. Security through obscurity + actual admin code validation.
3. **Quota display placement** - Subtle text above input box, non-intrusive but visible.
4. **Azure Table Storage** - Persistent across deployments, uses existing storage account.
