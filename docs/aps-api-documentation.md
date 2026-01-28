# ADAMS Public Search (APS) API Documentation

**Application:** ADAMS Public Search (APS)  
**Organization:** U.S. Nuclear Regulatory Commission (NRC)  
**Version:** 1.0 (December 2025)  
**Replaces:** Web-Based ADAMS (WBA) API (deprecated February 2026)

---

## Overview

The ADAMS Public Search API is a RESTful web service for accessing publicly available NRC documents from ADAMS (Agency-wide Documents Access and Management System). This API replaces the legacy WBA API.

### Key Differences from WBA API

| Feature | WBA API (Deprecated) | APS API (New) |
|---------|---------------------|---------------|
| Base URL | `http://adams.nrc.gov/wba/services/search/advanced/nrc` | `https://adams-api.nrc.gov/aps/api/search` |
| Protocol | HTTP | HTTPS |
| Response Format | XML | JSON |
| Authentication | None | Subscription Key Required |
| Query Format | Pseudo-JSON in URL parameter | JSON POST body |

---

## Authentication

### Registration Required

1. Navigate to the API Developer Portal: https://adams-api-developer.nrc.gov/
2. Click "Sign Up" and create an account with your email address
3. Verify your email and log in

### Subscription Key

1. After logging in, browse the Products section via the Top Menu
2. Select "ADAMS Public Search API (ADAMS APS API)"
3. Enter a name for your subscription and click "Subscribe"
4. Use the generated key in the `Ocp-Apim-Subscription-Key` header

---

## API Endpoints

### Base URL

```
https://adams-api.nrc.gov/aps/api/search
```

### 1. Get Document

Retrieve a single document and all metadata by Accession Number.

**Request:**
```http
GET https://adams-api.nrc.gov/aps/api/search/{accessionNumber}
Ocp-Apim-Subscription-Key: {your_api_subscription_key}
Accept: application/json
```

**Parameters:**
- `accessionNumber` (path, required): Unique NRC accession number (e.g., ML12345A678)

**Response:**
```json
{
  "document": {
    "Id": "12345",
    "Name": "Inspection Report",
    "AccessionNumber": "ML12345A678",
    "DocumentTitle": "Reactor Inspection Summary",
    "AuthorName": ["NRC Staff"],
    "DocumentDate": "2025-09-01",
    "DocumentType": ["Inspection Report"],
    "Url": "https://...",
    "content": "Base64 or inline text content",
    "EstimatedPageCount": "42"
  }
}
```

### 2. Search Document Library

Execute Boolean-style searches with AND/OR operators and property filters.

**Request:**
```http
POST https://adams-api.nrc.gov/aps/api/search
Ocp-Apim-Subscription-Key: {your_api_subscription_key}
Content-Type: application/json

{
  "q": "search terms",
  "filters": [...],
  "anyFilters": [...],
  "legacyLibFilter": true,
  "mainLibFilter": true,
  "sort": "DocumentDate",
  "sortDirection": 1,
  "skip": 0
}
```

**Request Body Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Full-text search query |
| `filters` | array | Property filters for AND operations (all must be true) |
| `anyFilters` | array | Property filters for OR operations (any can be true) |
| `legacyLibFilter` | boolean | Include legacy library (pre-1999 documents) |
| `mainLibFilter` | boolean | Include main library (documents since Nov 1999) |
| `sort` | string | Field to sort by (e.g., `DocumentDate`) |
| `sortDirection` | integer | `0` = Ascending, `1` = Descending |
| `skip` | integer | Number of items to skip for pagination (default: 0) |

---

## Filter Objects

### Text Filters

For most document properties:

```json
{
  "field": "DocumentType",
  "value": "Inspection Report",
  "operator": "equals"
}
```

**Text Operators:**
| Operator | API Value | Description |
|----------|-----------|-------------|
| Contains | `contains` | Field contains the search term |
| Does Not Contain | `notcontains` | Field does not contain the search term |
| Starts With | `starts` | Field starts with the value |
| Does Not Start With | `notstarts` | Field does not start with the value |
| Equals | `equals` | Exact match |
| Does Not Equal | `notequals` | Does not match exactly |

### Date Filters

For `DocumentDate` and `DateAddedTimestamp`:

```json
{
  "field": "DocumentDate",
  "value": "(DocumentDate ge '2024-01-01')"
}
```

**Date Operators:**
| Operator | Syntax | Example |
|----------|--------|---------|
| On or After | `ge` | `(DocumentDate ge '2024-01-01')` |
| On or Before | `le` | `(DocumentDate le '2024-12-31')` |
| Equals | `eq` | `(DateAddedTimestamp eq '2024-01-01')` |
| Between | `ge` + `le` | `(DocumentDate ge '2024-01-01') and (DocumentDate le '2024-12-31')` |

**Date Format:** `YYYY-MM-DD`

---

## Document Properties

| Property | Description |
|----------|-------------|
| `AccessionNumber` | Unique identifier for each document |
| `DocumentTitle` | Title of the document |
| `AuthorName` | One or more authors (array) |
| `AuthorAffiliation` | Organization of the author |
| `AddresseeName` | Recipient name if available |
| `AddresseeAffiliation` | Recipient organization |
| `DocumentDate` | Date of the document |
| `DocumentType` | Type (e.g., Inspection Report, Letter) |
| `Keyword` | Keywords associated with the document |
| `DocketNumber` | NRC-assigned docket number |
| `DateAddedTimestamp` | Date added to ADAMS Public Library |
| `EstimatedPageCount` | Estimated length |
| `Url` | Direct URI to the document resource |

---

## Example Queries

### Search for Part 21 Reports

```json
{
  "q": "",
  "filters": [
    {"field": "DocumentType", "value": "Part 21", "operator": "contains"}
  ],
  "anyFilters": [],
  "legacyLibFilter": false,
  "mainLibFilter": true,
  "sort": "DocumentDate",
  "sortDirection": 1,
  "skip": 0
}
```

### Search for Recent Inspection Reports

```json
{
  "q": "safety valve",
  "filters": [
    {"field": "DocumentType", "value": "Inspection Report", "operator": "equals"},
    {"field": "DocumentDate", "value": "(DocumentDate ge '2024-01-01')"}
  ],
  "anyFilters": [],
  "legacyLibFilter": false,
  "mainLibFilter": true,
  "sort": "DocumentDate",
  "sortDirection": 1,
  "skip": 0
}
```

### Search by Docket Number

```json
{
  "q": "",
  "filters": [
    {"field": "DocketNumber", "value": "05000424", "operator": "contains"}
  ],
  "anyFilters": [],
  "legacyLibFilter": false,
  "mainLibFilter": true,
  "sort": "DocumentDate",
  "sortDirection": 1,
  "skip": 0
}
```

---

## Support

- **Developer Portal:** https://adams-api-developer.nrc.gov/
- **Email:** APSSupport.Resource@nrc.gov

---

## Migration from WBA API

### Required Changes

1. **Authentication:** Register and obtain a subscription key
2. **URL:** Change from `adams.nrc.gov/wba/...` to `adams-api.nrc.gov/aps/api/search`
3. **Request Method:** Change from GET with URL params to POST with JSON body
4. **Response Format:** Parse JSON instead of XML
5. **Query Format:** Convert pseudo-JSON URL params to proper JSON body

### WBA to APS Operator Mapping

| WBA Operator | APS Operator |
|--------------|--------------|
| `eq`, `ends` | `equals` |
| `not` | `notequals` |
| `starts` | `starts` |
| `not_starts` | `notstarts` |
| `infolder`, `contains` | `contains` |
| `not_contains` | `notcontains` |
