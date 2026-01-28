# CLS Web Services API Documentation

**Application:** Clause Logic Service (CLS)  
**Organization:** Department of Defense (DoD) - OUSD(A&S)/DPC  
**Version:** 3.0 (May 20, 2022)  
**Prepared by:** Peraton

---

## Overview

The Clause Logic Service (CLS) Web Services API enables external Contract Writing Systems (CWS) to interface with CLS for managing government contract clause documents. The API supports asynchronous workflows where the CWS initiates events and CLS responds synchronously.

### Typical Workflow

1. **Reserve** - Check/create placeholder for a clause document
2. **Register** - Submit Auto Answer payload to create the document
3. **Status** - Poll until document processing is complete
4. **Retrieve** - Download the completed clause document

---

## Base URLs

| Environment | URL |
|-------------|-----|
| Test | `https://cls-test.fedmall.mil/clsws` |
| Production | `https://cls.fedmall.mil/clsws` |

**Protocol:** HTTPS only

---

## Authentication

Authentication uses basic authentication (username/password) to establish the system's identity, which is then exchanged for a JSON Web Token (JWT). The JWT is passed via web service calls to maintain the authenticated session.

---

## API Endpoints

### 1. Reserve Document

Checks for the existence of a document in CLS. If none exists, creates a placeholder. If one exists, returns a warning that future actions will overwrite it.

| Property | Value |
|----------|-------|
| **Method** | POST |
| **URL** | `/api/AutoAnswer/document/reserve` |
| **Content-Type** | application/json |

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `user_id` | Yes | Unique ID of the CLS user |
| `system_id` | Yes | Unique ID of the CWS (e.g., `CON-IT-AF`) |
| `document_id` | Yes | Document PIID (Procurement Instrument Identifier) |

**Example Request:**
```http
POST https://cls-test.fedmall.mil/clsws/api/AutoAnswer/document/reserve?user_id=123654789&system_id=CON-IT-AF&document_id=ADOCID18Z0001
```

**Responses:**

| HTTP Code | App Code | Condition | Message |
|-----------|----------|-----------|---------|
| 200 | 201 | Success | OK: Document reserved in Clause Logic |
| 200 | 400 | Empty user_id/system_id/document_id | Bad Request |
| 200 | 400 | Document already exists | Bad Request: Attempt to reserve document that already exists for user |
| 200 | 400 | Invalid document_id format | Bad Request: Invalid Document Id Length / Invalid First Two Characters / etc. |
| 200 | 401 | User not found | Unauthorized: [user_id] User not found in Clause Logic |
| 200 | 403 | User doesn't own document | Forbidden: User does not own Clause Logic Document |

---

### 2. Register Document

Creates a CLS document with Auto Answer information. The Auto Answer JSON payload must be included in the request body.

| Property | Value |
|----------|-------|
| **Method** | POST |
| **URL** | `/api/AutoAnswer/document/register` |
| **Content-Type** | application/json |

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `user_id` | Yes | Unique ID of the CLS user |
| `system_id` | Yes | Unique ID of the CWS |
| `document_id` | Yes | Document PIID |

**Request Body:** Auto Answer JSON payload (see schema documentation)

**Example Request:**
```http
POST https://cls-test.fedmall.mil/clsws/api/AutoAnswer/document/register?user_id=123654789&system_id=CON-IT-AF&document_id=ADOCID18Z0001
Content-Type: application/json

{
  "ClauseLogicAutoAnswer": {
    "OriginatorDetails": {
      "SchemaVersionUsed": 1.0,
      "DoDSystem": {
        "DITPRNumber": "0102",
        "SystemAdministratorDoDAAC": "A01234",
        "SystemVersion": "3.2.3"
      }
    },
    "AutoAnswerDetails": [
      {
        "DocumentId": {
          "DoDInstrumentNumber": {
            "EnterpriseIdentifier": "A0",
            "Year": 18,
            "ProcurementInstrumentTypeCode": "A",
            "SerializedIdentifier": "0001"
          }
        },
        "AwardType": "Blanket Purchase Agreement",
        "EstimatedCost": 265000
      }
    ]
  }
}
```

**Responses:**

| HTTP Code | App Code | Condition | Message |
|-----------|----------|-----------|---------|
| 200 | 200 | Success | Document created |
| 200 | 400 | Empty required params | Bad Request |
| 200 | 400 | Duplicate document | Bad Request: Multiple documents exist with same ID |
| 200 | 401 | User not found | Unauthorized: [user_id] User not found in Clause Logic |
| 200 | 403 | User doesn't own document | Forbidden: User does not own Clause Logic Document |

---

### 3. Check Document Status

Returns the processing status of a CLS document. Use this to determine when a document is ready for retrieval.

| Property | Value |
|----------|-------|
| **Method** | GET |
| **URL** | `/api/AutoAnswer/document/status` |

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `user_id` | Yes | Unique ID of the CLS user |
| `system_id` | No | Unique ID of the CWS |
| `document_id` | Yes | Document PIID |

**Example Request:**
```http
GET https://cls-test.fedmall.mil/clsws/api/AutoAnswer/document/status?user_id=123654789&system_id=CON-IT-AF&document_id=ADOCID18Z0001
```

**Responses:**

| HTTP Code | App Code | Condition | Message |
|-----------|----------|-----------|---------|
| 200 | 200 | Document ready | CLS Document is ready for download |
| 204 | 204 | Document not ready | CLS Document is not ready for download |
| 200 | 400 | Empty user_id/document_id | Bad Request |
| 200 | 400 | Duplicate documents | Bad Request: Multiple documents exist with same ID |
| 200 | 401 | User not found | Unauthorized: [user_id] User not found in Clause Logic |
| 200 | 403 | User doesn't own document | Forbidden: User does not own Clause Logic Document |

---

### 4. Retrieve Document

Downloads the completed clause document as XML (based on CLS Response schema).

| Property | Value |
|----------|-------|
| **Method** | GET |
| **URL** | `/api/AutoAnswer/document/retrieve` |

**Query Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `user_id` | Yes | Unique ID of the CLS user |
| `system_id` | No | Unique ID of the CWS |
| `document_id` | Yes | Document PIID |

**Example Request:**
```http
GET https://cls-test.fedmall.mil/clsws/api/AutoAnswer/document/retrieve?user_id=123654789&system_id=CON-IT-AF&document_id=ADOCID18Z0001
```

**Responses:**

| HTTP Code | App Code | Condition | Message |
|-----------|----------|-----------|---------|
| 200 | 200 | Success | Returns XML clause document |
| 200 | 400 | Empty user_id/document_id | Bad Request |
| 200 | 400 | Document not ready | Bad Request: CLS Document is not ready |
| 200 | 401 | User not found | Unauthorized: [user_id] User not found in Clause Logic |
| 200 | 403 | User doesn't own document | Forbidden: User does not own Clause Logic Document |
| 200 | 404 | Document doesn't exist | Not Found: Document is not available |

---

## Document ID Formats (PIID)

The Document ID follows the Procurement Instrument Identifier (PIID) format:

### Base Documents (Awards, Solicitations, Task Orders, Delivery Orders)

- **Format:** 13 alphanumeric characters
- **Example:** `ADOCID18Z0001`

### Modifications

- **Format:** Base Document ID + hyphen + 6-character modification number
- **Modification number format:**
  - 1st digit: `A` or `P`
  - 2nd-3rd digits: `0-9` or `A-Z` (except `I` and `O`)
  - 4th-6th digits: `0-9`
- **Example:** `ADOCID18Z0001-P00001`

### Amendments

- **Format:** Base Document ID + hyphen + 4-digit amendment number
- **Amendment number format:** `0000-9999` (must retain leading zeros)
- **Example:** `ADOCID18Z0001-0001`

---

## Payload Validation

When a CWS submits a payload, CLS validates it in stages:

### 1. Required Element Validation

- All required elements are evaluated first
- If any fail, a complete report of failed elements is returned
- No document is created; the reserved document ID is released

### 2. Optional Element Validation

- Evaluated only after all required elements pass
- Failing optional elements are dropped (not added to document)
- User must answer dropped questions manually in CLS UI

### 3. Conditional Element Validation

- Evaluated after optional elements
- Failing conditional elements are dropped
- User must answer dropped questions manually in CLS UI

---

## HTTP Response Codes

| Code | Status | Description |
|------|--------|-------------|
| 200 | OK | Request successful (check application status code for details) |
| 201 | Created | Resource successfully created |
| 204 | Accepted | Request accepted but processing not complete |
| 400 | Bad Request | Invalid request (malformed syntax, validation error) |
| 401 | Unauthorized | Authentication required or failed |
| 403 | Forbidden | Valid request but server refusing action (permissions) |
| 404 | Not Found | Resource not found |
| 500 | Internal Server Error | Unexpected server error |
| 503 | Service Unavailable | Server temporarily unavailable |

---

## Acronyms

| Acronym | Definition |
|---------|------------|
| API | Application Program Interface |
| CLS | Clause Logic Service |
| CWS | Contract Writing System |
| DoD | Department of Defense |
| HTTPS | Hypertext Transport Protocol Secure |
| JWT | JSON Web Token |
| PIID | Procurement Instrument Identifier |
| UI | User Interface |
| WS | Web Service |
| XML | Extensible Markup Language |

---

## Related Documentation

- **Auto Answer Technical Specification Reference Document** - Contains JSON payload schema details (version 1.2.x)
- **CLS Response Schema** - Defines the XML format for retrieved documents
