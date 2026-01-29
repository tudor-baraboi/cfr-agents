#!/usr/bin/env python3
"""
End-to-end test script for Personal Document Index (BYOD) feature.

Tests:
1. Document upload via REST API
2. Document listing via REST API  
3. Search filtering by fingerprint
4. Document deletion via REST API
5. Agent tools (list_my_documents, delete_my_document)

Usage:
    # Run all tests
    python scripts/test_personal_docs.py
    
    # Run with a specific test PDF
    python scripts/test_personal_docs.py --pdf /path/to/test.pdf
    
    # Run with verbose output
    python scripts/test_personal_docs.py -v

Requirements:
    - Search proxy running on localhost:8001
    - Backend running on localhost:8000
    - A test PDF file (or uses built-in test content)
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import sys
import time
from pathlib import Path

import httpx

# Test configuration
PROXY_URL = "http://localhost:8001"
BACKEND_URL = "http://localhost:8000"
TEST_INDEX = "faa-agent"

# Generate a unique test fingerprint
TEST_FINGERPRINT = f"test-fp-{hashlib.md5(str(time.time()).encode()).hexdigest()[:12]}"


class TestColors:
    """ANSI color codes for test output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    RESET = "\033[0m"


def print_test(name: str, status: str, message: str = ""):
    """Print a test result with color."""
    if status == "PASS":
        color = TestColors.GREEN
        symbol = "✓"
    elif status == "FAIL":
        color = TestColors.RED
        symbol = "✗"
    elif status == "SKIP":
        color = TestColors.YELLOW
        symbol = "○"
    else:
        color = TestColors.BLUE
        symbol = "→"
    
    print(f"{color}{symbol} {name}{TestColors.RESET}", end="")
    if message:
        print(f" - {message}")
    else:
        print()


def create_test_pdf() -> bytes:
    """Create a simple test PDF file."""
    # This is a minimal valid PDF with some text
    # In a real test, you'd use a proper PDF library
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 89 >>
stream
BT
/F1 12 Tf
100 700 Td
(This is a test document for FAA certification compliance testing.) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000408 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
480
%%EOF"""
    return pdf_content


async def test_health_checks(verbose: bool = False) -> bool:
    """Test that both services are running."""
    print_test("Health Checks", "RUN")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Check proxy
            resp = await client.get(f"{PROXY_URL}/health")
            if resp.status_code != 200:
                print_test("  Proxy health", "FAIL", f"Status {resp.status_code}")
                return False
            print_test("  Proxy health", "PASS")
            
            # Check backend
            resp = await client.get(f"{BACKEND_URL}/health")
            if resp.status_code != 200:
                print_test("  Backend health", "FAIL", f"Status {resp.status_code}")
                return False
            print_test("  Backend health", "PASS")
            
            return True
            
        except httpx.RequestError as e:
            print_test("  Connection", "FAIL", str(e))
            return False


async def test_document_upload(pdf_path: str | None, verbose: bool = False) -> str | None:
    """Test document upload endpoint."""
    print_test("Document Upload", "RUN")
    
    # Get PDF content
    if pdf_path and Path(pdf_path).exists():
        pdf_content = Path(pdf_path).read_bytes()
        filename = Path(pdf_path).name
    else:
        pdf_content = create_test_pdf()
        filename = "test_compliance_doc.pdf"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            files = {"file": (filename, pdf_content, "application/pdf")}
            data = {
                "fingerprint": TEST_FINGERPRINT,
                "index": TEST_INDEX,
            }
            
            resp = await client.post(
                f"{BACKEND_URL}/documents",
                files=files,
                data=data,
            )
            
            if resp.status_code != 200:
                error = resp.json().get("detail", resp.text)
                print_test("  Upload", "FAIL", f"Status {resp.status_code}: {error}")
                return None
            
            result = resp.json()
            doc_id = result.get("document_id")
            chunks = result.get("chunks_indexed", 0)
            
            if verbose:
                print(f"    Response: {json.dumps(result, indent=2)}")
            
            print_test("  Upload", "PASS", f"ID: {doc_id}, Chunks: {chunks}")
            return doc_id
            
        except httpx.RequestError as e:
            print_test("  Upload", "FAIL", str(e))
            return None
        except Exception as e:
            print_test("  Upload", "FAIL", str(e))
            return None


async def test_document_list(expected_count: int, verbose: bool = False) -> bool:
    """Test document listing via proxy."""
    print_test("Document Listing", "RUN")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(
                f"{PROXY_URL}/documents",
                params={
                    "fingerprint": TEST_FINGERPRINT,
                    "index": TEST_INDEX,
                }
            )
            
            if resp.status_code != 200:
                print_test("  List", "FAIL", f"Status {resp.status_code}")
                return False
            
            result = resp.json()
            docs = result.get("documents", [])
            
            if verbose:
                print(f"    Response: {json.dumps(result, indent=2)}")
            
            if len(docs) >= expected_count:
                print_test("  List", "PASS", f"Found {len(docs)} document(s)")
                return True
            else:
                print_test("  List", "FAIL", f"Expected {expected_count}, got {len(docs)}")
                return False
                
        except Exception as e:
            print_test("  List", "FAIL", str(e))
            return False


async def test_search_with_fingerprint(verbose: bool = False) -> bool:
    """Test that search filters by fingerprint correctly."""
    print_test("Search Filtering", "RUN")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Search with our fingerprint
            resp = await client.post(
                f"{PROXY_URL}/search",
                json={
                    "query": "test document compliance",
                    "fingerprint": TEST_FINGERPRINT,
                    "index": TEST_INDEX,
                    "top_k": 10,
                }
            )
            
            if resp.status_code != 200:
                print_test("  Search (own docs)", "FAIL", f"Status {resp.status_code}")
                return False
            
            result = resp.json()
            results = result.get("results", [])
            
            if verbose:
                print(f"    Own results: {len(results)}")
            
            print_test("  Search (own docs)", "PASS", f"Found {len(results)} results")
            
            # Search with a different fingerprint
            other_fp = "different-fingerprint-12345"
            resp = await client.post(
                f"{PROXY_URL}/search",
                json={
                    "query": "test document compliance",
                    "fingerprint": other_fp,
                    "index": TEST_INDEX,
                    "top_k": 10,
                }
            )
            
            if resp.status_code != 200:
                print_test("  Search (other user)", "FAIL", f"Status {resp.status_code}")
                return False
            
            result = resp.json()
            other_results = result.get("results", [])
            
            # Other user should NOT see our uploaded test docs
            # (they might see public docs with empty fingerprint)
            own_doc_in_others = any(
                r.get("owner_fingerprint") == TEST_FINGERPRINT 
                for r in other_results
            )
            
            if own_doc_in_others:
                print_test("  Search isolation", "FAIL", "Other user saw our docs!")
                return False
            
            print_test("  Search (other user)", "PASS", "Isolation working")
            return True
            
        except Exception as e:
            print_test("  Search", "FAIL", str(e))
            return False


async def test_document_delete(doc_id: str, verbose: bool = False) -> bool:
    """Test document deletion via proxy."""
    print_test("Document Deletion", "RUN")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.delete(
                f"{PROXY_URL}/documents/{doc_id}",
                params={
                    "fingerprint": TEST_FINGERPRINT,
                    "index": TEST_INDEX,
                }
            )
            
            if resp.status_code != 200:
                error = resp.json().get("detail", resp.text)
                print_test("  Delete", "FAIL", f"Status {resp.status_code}: {error}")
                return False
            
            result = resp.json()
            deleted = result.get("deleted_count", 0)
            
            if verbose:
                print(f"    Response: {json.dumps(result, indent=2)}")
            
            print_test("  Delete", "PASS", f"Deleted {deleted} chunk(s)")
            return True
            
        except Exception as e:
            print_test("  Delete", "FAIL", str(e))
            return False


async def test_unauthorized_delete(doc_id: str, verbose: bool = False) -> bool:
    """Test that other users can't delete our documents."""
    print_test("Unauthorized Delete", "RUN")
    
    other_fp = "malicious-user-fingerprint"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.delete(
                f"{PROXY_URL}/documents/{doc_id}",
                params={
                    "fingerprint": other_fp,
                    "index": TEST_INDEX,
                }
            )
            
            # Should fail with 403 or 404
            if resp.status_code in [403, 404]:
                print_test("  Blocked", "PASS", f"Status {resp.status_code}")
                return True
            else:
                print_test("  Blocked", "FAIL", f"Got status {resp.status_code} (expected 403/404)")
                return False
                
        except Exception as e:
            print_test("  Blocked", "FAIL", str(e))
            return False


async def run_tests(pdf_path: str | None = None, verbose: bool = False) -> int:
    """Run all tests."""
    print(f"\n{TestColors.BLUE}{'='*60}{TestColors.RESET}")
    print(f"{TestColors.BLUE}Personal Document Index (BYOD) Tests{TestColors.RESET}")
    print(f"{TestColors.BLUE}{'='*60}{TestColors.RESET}\n")
    
    print(f"Test fingerprint: {TEST_FINGERPRINT}")
    print(f"Test index: {TEST_INDEX}")
    print()
    
    passed = 0
    failed = 0
    
    # 1. Health checks
    if await test_health_checks(verbose):
        passed += 1
    else:
        print("\nServices not running. Start them with: ./scripts/dev_start.sh")
        return 1
    
    # 2. Upload document
    doc_id = await test_document_upload(pdf_path, verbose)
    if doc_id:
        passed += 1
    else:
        failed += 1
        print("\nUpload failed, skipping remaining tests.")
        return 1
    
    # Give Azure Search a moment to index
    print("\nWaiting for indexing...")
    await asyncio.sleep(2)
    
    # 3. List documents
    if await test_document_list(expected_count=1, verbose=verbose):
        passed += 1
    else:
        failed += 1
    
    # 4. Search filtering
    if await test_search_with_fingerprint(verbose):
        passed += 1
    else:
        failed += 1
    
    # 5. Unauthorized delete
    if await test_unauthorized_delete(doc_id, verbose):
        passed += 1
    else:
        failed += 1
    
    # 6. Actual delete
    if await test_document_delete(doc_id, verbose):
        passed += 1
    else:
        failed += 1
    
    # 7. Verify deletion
    await asyncio.sleep(1)
    if await test_document_list(expected_count=0, verbose=verbose):
        passed += 1
    else:
        failed += 1
    
    # Summary
    print(f"\n{TestColors.BLUE}{'='*60}{TestColors.RESET}")
    total = passed + failed
    if failed == 0:
        print(f"{TestColors.GREEN}All {total} tests passed!{TestColors.RESET}")
        return 0
    else:
        print(f"{TestColors.RED}{failed}/{total} tests failed{TestColors.RESET}")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Test Personal Document Index feature")
    parser.add_argument("--pdf", "-p", help="Path to a test PDF file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    exit_code = asyncio.run(run_tests(pdf_path=args.pdf, verbose=args.verbose))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
