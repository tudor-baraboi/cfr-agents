#!/usr/bin/env python3
"""
Check trial token usage from the Azure backend.
Run this script to see remaining requests for each trial code.
"""

from typing import Optional
import httpx
import sys

API_URL = "https://faa-agent-api.azurewebsites.net"
TRIAL_CODES = ["TRIAL-TEST01", "TRIAL-TEST02", "TRIAL-TEST03", "SONIC-GOOSE"]


def check_usage(code: str) -> Optional[dict]:
    """Check usage for a single trial code."""
    try:
        response = httpx.post(
            f"{API_URL}/auth/validate-code",
            json={"code": code},
            timeout=10.0,
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            # Code exhausted
            return {"code": code, "requests_used": "EXHAUSTED", "requests_remaining": 0}
        else:
            return {"code": code, "error": response.text}
    except Exception as e:
        return {"code": code, "error": str(e)}


def main():
    print("\n=== Trial Token Usage ===\n")
    print(f"{'Code':<15} {'Used':<8} {'Remaining':<12} {'Limit':<8}")
    print("-" * 45)
    
    for code in TRIAL_CODES:
        result = check_usage(code)
        if result and "error" not in result:
            used = result.get("requests_used", "?")
            remaining = result.get("requests_remaining", "?")
            # Calculate limit from used + remaining
            if isinstance(used, int) and isinstance(remaining, int):
                limit = used + remaining
            else:
                limit = "?"
            print(f"{code:<15} {used:<8} {remaining:<12} {limit:<8}")
        else:
            error = result.get("error", "Unknown error") if result else "Failed"
            print(f"{code:<15} ERROR: {error}")
    
    print()


if __name__ == "__main__":
    main()
