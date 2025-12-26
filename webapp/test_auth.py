#!/usr/bin/env python3
"""
Test script for API authentication
Tests that external requests require API key while internal requests are exempted.
"""

import requests
import sys
import os


def test_health_endpoint():
    """Health endpoints should be accessible without authentication"""
    print("\n1. Testing health endpoint (should be accessible without auth)...")
    response = requests.get("http://localhost:8067/api/health")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("   ✓ Health endpoint is accessible")
        return True
    else:
        print("   ✗ Health endpoint failed")
        return False


def test_protected_endpoint_no_key():
    """Protected endpoints should reject requests without API key"""
    print("\n2. Testing protected endpoint without API key (should be rejected)...")
    response = requests.get("http://localhost:8067/api/conversations")
    print(f"   Status: {response.status_code}")
    if response.status_code == 401:
        print("   ✓ Request correctly rejected (401 Unauthorized)")
        return True
    else:
        print(f"   ✗ Unexpected status code: {response.status_code}")
        print(f"   Response: {response.text}")
        return False


def test_protected_endpoint_invalid_key():
    """Protected endpoints should reject requests with invalid API key"""
    print("\n3. Testing protected endpoint with invalid API key (should be rejected)...")
    headers = {"X-API-Key": "invalid-key"}
    response = requests.get("http://localhost:8067/api/conversations", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code == 403:
        print("   ✓ Request correctly rejected (403 Forbidden)")
        return True
    else:
        print(f"   ✗ Unexpected status code: {response.status_code}")
        print(f"   Response: {response.text}")
        return False


def test_protected_endpoint_valid_key():
    """Protected endpoints should accept requests with valid API key"""
    api_key = os.getenv("API_KEY", "your-secret-api-key-change-me")
    print(f"\n4. Testing protected endpoint with valid API key (should be accepted)...")
    print(f"   Using API key: {api_key[:10]}...")
    headers = {"X-API-Key": api_key}
    response = requests.get("http://localhost:8067/api/conversations", headers=headers)
    print(f"   Status: {response.status_code}")
    if response.status_code in [200, 404]:  # 404 is ok if no data exists
        print("   ✓ Request accepted with valid API key")
        return True
    else:
        print(f"   ✗ Unexpected status code: {response.status_code}")
        print(f"   Response: {response.text}")
        return False


def main():
    print("=" * 60)
    print("API Authentication Test Suite")
    print("=" * 60)
    print("\nMake sure the backend is running on http://localhost:8067")
    print("Set API_KEY environment variable or use default from docker-compose.yml")

    results = []
    results.append(("Health endpoint accessible", test_health_endpoint()))
    results.append(("No API key rejected", test_protected_endpoint_no_key()))
    results.append(("Invalid API key rejected", test_protected_endpoint_invalid_key()))
    results.append(("Valid API key accepted", test_protected_endpoint_valid_key()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(result[1] for result in results)
    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! 🎉")
        sys.exit(0)
    else:
        print("Some tests failed! ❌")
        sys.exit(1)


if __name__ == "__main__":
    main()
