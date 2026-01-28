# Admin Dashboard PRD

**Version:** 1.0  
**Date:** January 24, 2026  
**Status:** In Development

---

## Overview

Add an admin dashboard to the FAA/NRC/DoD agent applications that provides visibility into user activity and submitted feedback. This enables administrators to monitor usage patterns, identify geographic distribution of users, and review feedback submissions.

---

## Goals

1. **Usage Monitoring**: View all daily usage records with user fingerprints, request counts, timestamps, and geographic location
2. **Feedback Review**: Browse submitted feedback with type, message, contact info, and links to logs
3. **Geographic Insights**: Reverse IP lookup to show user location (country/city)

---

## Non-Goals (for this version)

- Pagination (manual refresh only)
- Action buttons (delete, export, etc.)
- Real-time updates (manual refresh)
- Search/filtering
- Analytics/charts

---

## User Stories

### Admin Views Usage Data
As an admin, I want to see a table of all usage records sorted by newest first, so I can monitor who is using the system and where they're located.

**Acceptance Criteria:**
- Table shows: Date, Fingerprint (truncated), Request Count, First Request, Last Request, User Agent, Location (Country/City)
- Sorted by date descending (newest first)
- Manual refresh via browser reload

### Admin Views Feedback
As an admin, I want to see all submitted feedback as cards, so I can review bug reports, feature requests, and contact users if they provided info.

**Acceptance Criteria:**
- Cards show: Type (badge), Message, Timestamp, Contact info (if provided), Link to logs blob
- Sorted by newest first
- Contact info displayed only if provided (name, email, phone, company)

---

## Technical Design

### Backend Changes

#### 1. IP Geolocation Service
New file: `backend/app/services/geolocation.py`

```python
async def get_location_from_ip(ip: str) -> dict:
    """
    Get geographic location from IP address using ip-api.com (free, no key required).
    Returns: {"country": "US", "city": "New York"} or empty dict on failure.
    """
```

- Uses ip-api.com (free tier: 45 requests/minute)
- Falls back gracefully to empty dict on failure
- Caches results to avoid repeated lookups

#### 2. Usage Service Updates
File: `backend/app/services/usage.py`

New method:
```python
async def list_all_usage(self) -> list[dict]:
    """List all usage records across all dates, sorted by date desc."""
```

Updated `increment_usage()` to accept IP and store location:
- Extract IP from X-Forwarded-For header (Azure sets this)
- Call geolocation service
- Store Country/City fields in entity

#### 3. Feedback Service Updates  
File: `backend/app/services/feedback.py`

New method:
```python
async def list_all_feedback(self) -> list[dict]:
    """List all feedback records, sorted by newest first."""
```

#### 4. Admin Router
New file: `backend/app/routers/admin.py`

Endpoints:
- `GET /admin/usage` - Returns all usage records (protected by verify_admin_token)
- `GET /admin/feedback` - Returns all feedback records (protected by verify_admin_token)

### Frontend Changes

#### 1. Admin Dashboard Component
New file: `frontend/src/AdminDashboard.tsx`

- Tabbed interface: "Usage" | "Feedback"
- Usage tab: Table with sortable columns
- Feedback tab: Card layout with type badges
- Manual refresh via F5/browser reload

#### 2. App.tsx Updates
- Detect admin mode and show AdminDashboard instead of ChatInterface
- Pass auth token for API calls

#### 3. CSS Styles
Add to `frontend/src/styles.css`:
- Admin dashboard container styles
- Tab navigation styles
- Table styles for usage data
- Card styles for feedback
- Type badges (bug/feature/other)

---

## Data Schema

### DailyUsage Table (Azure Table Storage)
| Field | Type | Description |
|-------|------|-------------|
| PartitionKey | string | Date (YYYY-MM-DD) |
| RowKey | string | Fingerprint ID |
| RequestCount | int | Number of requests |
| FirstRequestAt | datetime | First request timestamp |
| LastRequestAt | datetime | Last request timestamp |
| UserAgent | string | Browser user agent |
| IPAddress | string | User IP address (new) |
| Country | string | Country from IP lookup (new) |
| City | string | City from IP lookup (new) |

### Feedback Table (Azure Table Storage)
| Field | Type | Description |
|-------|------|-------------|
| PartitionKey | string | Date (YYYY-MM-DD) |
| RowKey | string | Feedback UUID |
| Type | string | bug/feature/other |
| Message | string | Feedback text |
| Fingerprint | string | User fingerprint |
| LogsBlobUrl | string | Link to logs in blob storage |
| UserAgent | string | Browser user agent |
| CreatedAt | datetime | Submission timestamp |
| ContactName | string | Optional contact name |
| ContactEmail | string | Optional contact email |
| ContactPhone | string | Optional contact phone |
| ContactCompany | string | Optional contact company |

---

## API Specification

### GET /admin/usage
**Auth:** Bearer token with is_admin=true

**Response:**
```json
{
  "usage": [
    {
      "date": "2026-01-24",
      "fingerprint": "abc123...",
      "request_count": 15,
      "first_request_at": "2026-01-24T10:00:00Z",
      "last_request_at": "2026-01-24T14:30:00Z",
      "user_agent": "Mozilla/5.0...",
      "country": "United States",
      "city": "New York"
    }
  ]
}
```

### GET /admin/feedback
**Auth:** Bearer token with is_admin=true

**Response:**
```json
{
  "feedback": [
    {
      "id": "uuid-here",
      "date": "2026-01-24",
      "type": "bug",
      "message": "Something broke...",
      "fingerprint": "abc123...",
      "logs_url": "https://...",
      "created_at": "2026-01-24T10:00:00Z",
      "contact": {
        "name": "John Doe",
        "email": "john@example.com",
        "phone": null,
        "company": "Acme Corp"
      }
    }
  ]
}
```

---

## Implementation Checklist

- [x] Create `backend/app/services/geolocation.py`
- [x] Update `backend/app/services/usage.py` - add list_all_usage, IP/location tracking
- [x] Update `backend/app/services/feedback.py` - add list_all_feedback
- [x] Create `backend/app/routers/admin.py`
- [x] Update `backend/app/main.py` - include admin router
- [x] Create `frontend/src/AdminDashboard.tsx`
- [x] Update `frontend/src/App.tsx` - render AdminDashboard for admins
- [x] Add admin dashboard styles to `frontend/src/styles.css`
- [x] Add `httpx` to backend dependencies (already present)

---

## Security Considerations

- All admin endpoints protected by `verify_admin_token` dependency
- Admin tokens require valid admin code from environment variable
- IP addresses stored for legitimate admin use (usage monitoring)
- No PII beyond what user voluntarily provides in feedback contact info

---

## Future Enhancements (Out of Scope)

- Pagination for large datasets
- Export to CSV/Excel
- Date range filtering
- Real-time updates via WebSocket
- Analytics charts (requests over time, geographic distribution)
- Feedback actions (mark resolved, reply to user)
