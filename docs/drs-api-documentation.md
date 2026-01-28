# DRS API Technical Documentation

**Application:** Dynamic Regulatory System (DRS)  
**Interface:** External Applications  
**Version:** 6.0 (Release 21)  
**Last Updated:** August 7, 2025

---

## Revision History

| Version | Description | Date |
|---------|-------------|------|
| 1.0 | Initial version | 02/09/2022 |
| 2.0 | Release 7 Changes | 05/19/2022 |
| 3.0 | Release 15 Changes | 04/11/2024 |
| 4.0 | Release 15.a - Updates to include 'docLastModifiedDateSortOrder' as a request parameter | 05/23/2024 |
| 5.0 | Release 16 – DRS API to download files | 07/18/2024 |
| 6.0 | Release 21 – DRS API to include metadata filters | 08/07/2025 |

---

## 1.0 Overview

This document presents the details for retrieving regulatory and guidance documents from Dynamic Regulatory System (DRS) by external applications.

## 2.0 Scope

The scope of this document is to provide technical details of DRS API for external applications.

### 2.1 Dynamic Regulatory System (DRS)

DRS is a comprehensive knowledge center of regulatory and guidance material from the Office of Aviation Safety (AVS) and beyond. It provides one central location for aviation regulations and guidance materials.

DRS combines numerous document types from a dozen repositories into a single searchable application. The system includes pending, current and historical versions of all documents along with their revision history. And to ensure you have the most current documents, it is updated every 24 hours.

---

## 3.0 Interface Details

### 3.1 API URLs

| HTTP Method | URL |
|-------------|-----|
| GET | `https://drs.faa.gov/api/drs/data-pull/<doctypeName>` |
| GET | `https://drs.faa.gov/api/drs/data-pull/download/<id>` |
| GET | `https://drs.faa.gov/api/drs/data-pull/get-other-attachment-details/<id>` |
| POST | `https://drs.faa.gov/api/drs/data-pull/<doctypeName>/filtered` |

### 3.2 API Key

| Header Parameter | Value |
|------------------|-------|
| `x-api-key` | To request an API key, please visit the DRS API page in the DRS Help & Training section and click on "Request / Renew API Key", then follow the steps outlined. |

---

## 3.3 API Endpoints to Retrieve Documents

The following API endpoints are used to retrieve document-related data from the Dynamic Regulatory System (DRS) for a specified document type.

- The first API retrieves document metadata.
- The second and third APIs use information returned from the first API to download document attachments or retrieve additional attachment details.
- The fourth API allows metadata-based filtering in the request, returning only documents that match the specified criteria.

---

### 3.3.1 Retrieve Document Metadata

| Property | Value |
|----------|-------|
| **API URL** | `https://drs.faa.gov/api/drs/data-pull/<doctypeName>` |
| **Method** | GET |

#### Request Parameters

**Header:**
```json
{
  "x-api-key": "{key}"
}
```

**Input parameters:**
- **Path variable:** `doctypeName`
- **Request Parameters:** `offset` (optional), `docLastModifiedDate` (optional), `docLastModifiedDateSortOrder` (optional)

#### Parameter Details

**1. Document Type Name (path parameter)**

Use Document Type name as path parameter in the API URL.

```
https://drs.faa.gov/api/drs/data-pull/AC
```

**2. Offset Parameter**

The `offset` is an optional field. The DRS API will return the first 750 documents by default if an "offset" is not received in the request. If an offset is provided in the request parameter, the API skips the documents till the offset value and returns next 750 documents starting from the "offset value +1".

```
https://drs.faa.gov/api/drs/data-pull/AC                  # Returns first 750
https://drs.faa.gov/api/drs/data-pull/AC?offset=750       # Skip first 750, returns 751-1500
https://drs.faa.gov/api/drs/data-pull/AC?offset=1500      # Skip first 1500, returns 1501-2250
```

**3. docLastModifiedDate Parameter**

This optional field is used to retrieve documents added or updated after the requested date.

The `docLastModifiedDate` value is included in the DRS API response, but by default, the response data is not sorted by this date. Instead, documents are sorted according to the default sort order configuration of the DRS browse screen for that document type.

```
https://drs.faa.gov/api/drs/data-pull/AC?docLastModifiedDate=2021-05-09T14:38:11.964Z&offset=0
```

Returns first 750 documents that have `docLastModifiedDate > 2021-05-09T14:38:11.964Z`

**4. docLastModifiedDateSortOrder Parameter**

This optional field allows you to retrieve documents sorted by their last modified date. Accepted values are `ASC` or `DESC`.

```
https://drs.faa.gov/api/drs/data-pull/AC?docLastModifiedDateSortOrder=DESC&offset=0
https://drs.faa.gov/api/drs/data-pull/AC?docLastModifiedDateSortOrder=ASC&offset=0
https://drs.faa.gov/api/drs/data-pull/AC?docLastModifiedDate=2021-05-09T14:38:11.964Z&offset=0&docLastModifiedDateSortOrder=DESC
```

If this request parameter is not provided, the documents will be sorted according to the default sort order configuration of the DRS browse screen for that document type.

> **Note:** To apply additional filters, please refer to API URL-4

#### CURL Request Examples

**Get first 750 documents from document type "AC":**
```bash
curl --location --request GET \
  'https://drs.faa.gov/api/drs/data-pull/AC?offset=0' \
  --header 'x-api-key: xxx' > AC_external_only.json
```

**Get first 750 documents from document type "AC" added or updated after a specific date:**
```bash
curl --location --request GET \
  'https://drs.faa.gov/api/drs/data-pull/AC?docLastModifiedDate=2021-05-09T14:38:11.964Z&offset=0' \
  --header 'x-api-key: xxx' > AC_external_only.json
```

#### Response - Success

HTTP Code 200

```json
{
  "summary": {
    "doctypeName": "AC",
    "drsDoctypeName": "Advisory Circulars (AC)",
    "count": 750,
    "hasMoreItems": true,
    "totalItems": 1765,
    "offset": 0,
    "sortBy": "drs:documentNumber",
    "sortByOrder": "ASC"
  },
  "documents": [..list of documents…]
}
```

**Summary Section Fields:**

| Field | Description |
|-------|-------------|
| `doctypeName` | Requested Document Type name |
| `drsDoctypeName` | Document Type name used in DRS application |
| `count` | Number of documents returned in the response (Maximum 750 in each call) |
| `hasMoreItems` | Boolean flag indicates whether more documents are available |
| `totalItems` | Total number of documents available |
| `offset` | Offset value from the request |
| `sortBy` | Metadata field name used for sorting while retrieving documents |
| `sortByOrder` | The sort order used for sorting while retrieving documents |

**Documents Array:**

The `documents` array contains entries where each entry represents a document with metadata names and their corresponding values. A metadata name is a string, and its value can be: text, array of text values, or date. All metadata fields of type date will use the format `YYYY-MM-DD`.

**Common Fields (all document types):**

| Field | Description |
|-------|-------------|
| `docLastModifiedDate` | The date and time (in UTC) when the document was last modified. Can be used as a request filter. |
| `documentGuid` | Unique Id for the document in DRS |
| `documentURL` | Unique URL for the document in DRS |

#### Response - Error

If the provided API key is invalid, the API will return a **403 Forbidden** response code.

**Other possible error responses:**

1. Invalid document type:
```json
{
  "errorMessage": "The doctype <document type name> is not present in DRS"
}
```

2. Internal-only document type requested with external API key:
```json
{
  "errorMessage": "Could not process the request. The doctype <document type name> is internal only doctype"
}
```

3. System error:
```json
{
  "errorMessage": "Unable to retrieve documents due to system error, Please try after some time or contact DRS application team."
}
```

---

### 3.3.2 Download Files

| Property | Value |
|----------|-------|
| **API URL** | `https://drs.faa.gov/api/drs/data-pull/download/<id>` |
| **Method** | GET |

#### Request Parameters

**Header:**
```json
{
  "x-api-key": "{key}"
}
```

Use the same key used for retrieving the document metadata (API URL – 1).

**Input parameters:**
- **Path variable:** `id` of the file to be downloaded

The response from the first API (API URL – 1) includes the following fields for each document's metadata details. These fields are only present if a valid file exists for download:

| Field | Description |
|-------|-------------|
| `mainDocumentDownloadURL` | API Endpoint URL for File Download |
| `mainDocumentFileName` | File Name |

The `mainDocumentDownloadURL` provides the API endpoint for downloading the main document file.

#### CURL Request Example

```bash
curl -k --location --request GET \
  'https://drs.faa.gov/api/drs/data-pull/download/<id>' \
  --header 'x-api-key: xxx' > FileName
```

#### Response - Success

HTTP Code 200. The response body is a byte stream.

#### Response - Error

If the provided API key is invalid, the API will return a **403 Forbidden** response code.

Other possible error responses: `404 Not Found`, `504 Gateway Timeout`, or `500 Internal Server Error`.

> **Note:** Consider incorporating retry logic to manage `504 Gateway Timeout` occurrences.

---

### 3.3.3 Get Additional Attachment Details

| Property | Value |
|----------|-------|
| **API URL** | `https://drs.faa.gov/api/drs/data-pull/get-other-attachment-details/<id>` |
| **Method** | GET |

#### Request Parameters

**Header:**
```json
{
  "x-api-key": "{key}"
}
```

Use the same key used for retrieving the document metadata (API URL – 1).

**Input parameters:**
- **Path variable:** file id of the primary document file

The response from the first API (API URL – 1) includes the following fields to determine if this document has valid additional attachments:

| Field | Description |
|-------|-------------|
| `hasMoreAttachments` | `true` or `false` |
| `otherAttachmentDetailsUrl` | URL to get other attachment details (only present if attachments exist) |

If `hasMoreAttachments` is `false`, the document has no additional attachments, and the `otherAttachmentDetailsUrl` field will be absent.

If `hasMoreAttachments` is `true`, use the `otherAttachmentDetailsUrl` to retrieve details about additional attachments, including their download URLs and file names. Then use API URL – 2 to download these attachments.

#### CURL Request Example

```bash
curl -k --location --request GET \
  'https://drs.faa.gov/api/drs/data-pull/get-other-attachment-details/<id>' \
  --header 'x-api-key: xxx' > other-attachments.json
```

#### Response - Success

HTTP Code 200.

If the API key is designated for external-only documents and the document contains internal-only additional attachments, those attachments will not be included in the response.

#### Response - Error

If the provided API key is invalid, the API will return a **403 Forbidden** response code.

System error:
```json
{
  "errorMessage": "Unable to retrieve documents due to system error, Please try after some time or contact DRS application team."
}
```

---

### 3.3.4 Retrieve Document Metadata with Filters

| Property | Value |
|----------|-------|
| **API URL** | `https://drs.faa.gov/api/drs/data-pull/<doctypeName>/filtered` |
| **Method** | POST |

#### Request Parameters

**Header:**
```json
{
  "x-api-key": "{key}"
}
```

**Path Variable:** `doctypeName`
- Required: Yes
- Description: The document type name to retrieve metadata for.

**Request Body:**
- Required: Yes
- Payload: Must be a valid JSON object. It can be an empty JSON `{}`, or include one or more of the following optional fields:

```json
{
  "offset": "<int value>",
  "docLastModifiedDate": "<date-time>",
  "sortOrder": "<DESC or ASC>",
  "documentFilters": {
    "<metadata key>": ["<value1>", "<value2>", "..."],
    "<another metadata key>": ["<value1>", "<value2>"],
    "<date metadata key>": ["<from date>", "<to date>"]
  }
}
```

#### Example Payload for PMA Document Type

```json
{
  "offset": 0,
  "docLastModifiedDate": "2021-12-21T14:04:31.062Z",
  "sortOrder": "DESC",
  "documentFilters": {
    "drs:status": ["Current", "Historical"],
    "drs:pmaNumber": ["PQ04418CE"],
    "drs:pmaSupDate": ["2020-01-01", "2025-07-31"]
  }
}
```

#### Parameter Details

**1. Document Type Name (path parameter)**

```
https://drs.faa.gov/api/drs/data-pull/PMA/filtered
```

**2. Using the offset Parameter**

Optional field. Works the same as in API URL-1.

```json
{}
```
Returns 750 documents.

```json
{
  "offset": 750
}
```
Skips the first 750 documents and returns the next 750 (starting from 751).

**3. Using the docLastModifiedDate Parameter**

Optional field. Used to retrieve documents added or updated after the requested date.

```json
{
  "offset": 0,
  "docLastModifiedDate": "2021-05-09T14:38:11.964Z"
}
```
Returns first 750 documents with `docLastModifiedDate > 2021-05-09T14:38:11.964Z`.

**4. Using the sortOrder Parameter**

Optional field. Accepted values are `ASC` or `DESC`.

```json
{
  "offset": 0,
  "sortOrder": "DESC"
}
```
Returns first 750 documents sorted by `docLastModifiedDate` in descending order.

**5. Using the documentFilters Parameter**

Optional field. Allows you to retrieve documents that match specific metadata filters.

Each filter is specified as a key-value pair:
- **Key** = metadata field name
- **Value** = array of filter values

```json
{
  "offset": 0,
  "docLastModifiedDate": "2021-12-21T14:04:31.062Z",
  "sortOrder": "DESC",
  "documentFilters": {
    "drs:status": ["Current", "Historical"],
    "drs:pmaNumber": ["PQ04418CE"],
    "drs:pmaSupDate": ["2020-01-01", "2025-07-31"]
  }
}
```

This request will:
- Return the first 750 documents
- Only include documents with a `docLastModifiedDate` after `2021-12-21T14:04:31.062Z`
- Sort results by `docLastModifiedDate` in descending order
- Filter documents that:
  - Have a `drs:status` of `Current` or `Historical`
  - Have a `drs:pmaNumber` value of `PQ04418CE`
  - Have a `drs:pmaSupDate` between `2020-01-01` and `2025-07-31`

#### Rules for Using Metadata Filters

- Each metadata field must be passed as a list (array), even if only one value is provided.
  ```json
  "drs:status": ["Current"]
  "drs:status": ["Current", "Historical"]
  ```

- For date-type metadata fields, the array must contain exactly two values:
  - The first is the start date
  - The second is the end date
  - Format: `YYYY-MM-DD`
  ```json
  "drs:pmaSupDate": ["2020-01-01", "2025-07-31"]
  ```

#### Rules for Using Keyword Search Filters

In addition to metadata fields specific to the selected document type, the filter also supports keyword search within document content.

To enable keyword search, pass `Keyword` as the key and provide a list of terms to search for.

```json
{
  "offset": 0,
  "documentFilters": {
    "drs:status": ["Current", "Historical"],
    "Keyword": ["ASTM International", "Shearography"]
  }
}
```

This request will filter documents that:
- Have a `drs:status` of `Current` or `Historical`
- Have documents that contain `ASTM International` or `Shearography` anywhere in the document content

#### Validation Rules for documentFilters

| Rule | Description |
|------|-------------|
| **Unsupported Filter Key** | Metadata filter keys must be defined for the requested document type. Unrecognized or unsupported keys will cause the request to be rejected. |
| **Maximum Number of Filters** | The total number of filters must not exceed 5. |
| **Maximum Values Per Filter** | Each filter can include multiple values but must not exceed 10. |
| **Empty Filter Values** | Filters with no usable value (null, empty, or whitespace-only) will be ignored. If all filters are empty after cleaning, the entire documentFilters section is treated as null. |
| **Date Filter Format** | Date filters must be a list of exactly two valid dates in `YYYY-MM-DD` format. |
| **Invalid Date Values** | If either the start or end date is invalid or unparseable, the request will be rejected. |
| **Invalid Filter Value Type** | If the value is not an array, the request will be rejected. Date filters must not be passed as plain strings. |
| **Post-Cleaning Empty Filter** | After removing null/empty values, if a filter has no values left, it will be skipped. If all filters become empty, the entire documentFilters section is removed from the request. |

#### Response - Success

HTTP Code 200. Response data is the same as the first API's response data.

#### Response - Error

If the provided API key is invalid, the API will return a **403 Forbidden** response code.

If the documentFilters validation fails, the API will return a **400 Bad Request** code:
```json
{
  "errorMessage": "One or more filters provided are invalid or not applicable for the requested document type. Please review the filter names and their values."
}
```

Other possible error responses (same as API URL-1):
- Invalid document type
- Internal-only document type with external API key
- System error

---

## 4.0 Additional Details

DRS provides a detailed spreadsheet of all Document Types available along with their metadata field names. The spreadsheet contains:

1. Document Type Name in API request (a short name for the document type)
2. Document Type name in DRS
3. Metadata names for the Document Type that are sent in the response
4. Metadata names for the Document Type that are used in DRS application
5. Metadata value data type (can be Text or Date or Array of values)

---

## Quick Reference

### Document Types

Common document types include:
- `AC` - Advisory Circulars
- `AD` - Airworthiness Directives
- `TSO` - Technical Standard Orders
- `Order` - FAA Orders
- `PMA` - Parts Manufacturer Approval

### Base URL

```
https://drs.faa.gov/api/drs
```

### Authentication

All requests require the `x-api-key` header.

### Pagination

- Default: 750 documents per request
- Use `offset` parameter to paginate
- Check `hasMoreItems` in response to determine if more documents exist

### Rate Limiting

Consider implementing retry logic for `504 Gateway Timeout` errors.
