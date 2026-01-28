# PRD: User Feedback System

## Overview

Add a user feedback system that allows users to report bugs, request features, or provide general feedback. Feedback is stored in Azure Table Storage with logs attached via Azure Blob Storage.

## Goals

1. **Simple UX** - Single button in header opens a modal, minimal required fields
2. **Capture context** - Auto-attach browser logs for debugging
3. **Optional contact** - Users can optionally provide contact info if they want follow-up
4. **Persistent storage** - Azure Table + Blob (not ephemeral /tmp)
5. **Link to fingerprint** - Associate feedback with user for context

## User Flow

1. User clicks 💬 button in header
2. Modal opens with:
   - Type dropdown: Bug / Feature Request / Other
   - Message textarea (required)
   - Collapsible "Contact me (optional)" section with name, email, phone, company
3. User fills in feedback and optionally contact info
4. User clicks Submit
5. System auto-attaches all browser logs
6. Success message shown, modal closes

## Technical Design

### Backend

#### FeedbackService (`backend/app/services/feedback.py`)

```python
class FeedbackService:
    TABLE_NAME = "Feedback"
    BLOB_CONTAINER = "feedback-logs"
    
    async def submit_feedback(
        fingerprint: str,
        feedback_type: str,  # bug | feature | other
        message: str,
        logs: list[dict],
        user_agent: str,
        contact: dict | None = None,  # {name, email, phone, company}
    ) -> str:  # Returns feedback ID
```

**Flow:**
1. Generate UUID for feedback
2. Upload logs to blob: `feedback-logs/{date}/{uuid}.json`
3. Store metadata in Feedback table with blob URL reference
4. Return feedback ID

#### Table Schema (`Feedback`)

| Field | Type | Description |
|-------|------|-------------|
| PartitionKey | string | Date `YYYY-MM-DD` |
| RowKey | string | UUID |
| Type | string | bug / feature / other |
| Message | string | User's feedback text |
| Fingerprint | string | Browser fingerprint |
| LogsBlobUrl | string | URL to blob with full logs |
| ContactName | string? | Optional |
| ContactEmail | string? | Optional |
| ContactPhone | string? | Optional |
| ContactCompany | string? | Optional |
| UserAgent | string | Browser info |
| CreatedAt | string | ISO timestamp |

#### Feedback Router (`backend/app/routers/feedback.py`)

```
POST /feedback/submit
Authorization: Bearer <token>

{
  "type": "bug" | "feature" | "other",
  "message": "string",
  "logs": [...],
  "userAgent": "string",
  "contact": {
    "name": "string?",
    "email": "string?", 
    "phone": "string?",
    "company": "string?"
  }
}

Response: { "id": "uuid", "message": "Feedback submitted successfully" }
```

### Frontend

#### FeedbackModal Component (`frontend/src/FeedbackModal.tsx`)

Props:
- `isOpen: boolean`
- `onClose: () => void`
- `token: string`

State:
- `type: 'bug' | 'feature' | 'other'`
- `message: string`
- `showContact: boolean`
- `contact: { name, email, phone, company }`
- `isSubmitting: boolean`
- `error: string | null`

Behavior:
- Auto-attaches `logger.getLogs()` on submit
- Shows success toast and closes on success
- Shows error message on failure

#### Header Changes

Replace existing 📋 logs button with 💬 feedback button that opens FeedbackModal.

### Cleanup

Delete `backend/app/routers/logs.py` - the /tmp-based logs endpoint is broken on Azure (ephemeral storage).

## Implementation Steps

1. Create `backend/app/services/feedback.py` - FeedbackService class
2. Create `backend/app/routers/feedback.py` - POST /feedback/submit endpoint
3. Update `backend/app/main.py` - Add feedback router, remove logs router
4. Delete `backend/app/routers/logs.py` - Remove broken endpoint
5. Create `frontend/src/FeedbackModal.tsx` - Modal component
6. Update `frontend/src/App.tsx` - Replace logs button with feedback button
7. Update `frontend/src/styles.css` - Add modal styles

## Success Criteria

- [ ] User can submit feedback with type and message
- [ ] User can optionally add contact info
- [ ] Logs are stored in Azure Blob Storage
- [ ] Feedback metadata stored in Azure Table Storage
- [ ] Feedback linked to user fingerprint
- [ ] Works on FAA, NRC, and DoD agents (shared code)
