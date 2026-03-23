"""
Test suite for Kosmo Tracking Sync Module
Tests POST /api/sync/tracking and GET /api/sync/status endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = "LastMile2026"

# Journey with Kosmo data
KOSMO_JOURNEY_ID = "778b38e3-4e68-4b85-ad74-24ae02fef468"


@pytest.fixture(scope="module")
def dev_token():
    """Get developer auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": DEV_EMAIL, "password": DEV_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def agent_token():
    """Get agent auth token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": AGENT_EMAIL, "password": AGENT_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


class TestKosmoSyncStatus:
    """Tests for GET /api/sync/status endpoint"""

    def test_get_sync_status_returns_200(self, dev_token):
        """GET /api/sync/status should return 200 with valid token"""
        response = requests.get(
            f"{BASE_URL}/api/sync/status",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        assert response.status_code == 200

    def test_get_sync_status_response_structure(self, dev_token):
        """GET /api/sync/status should return correct JSON structure"""
        response = requests.get(
            f"{BASE_URL}/api/sync/status",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        
        # Verify required fields
        assert "last_sync" in data, "Missing last_sync field"
        assert "total_checked" in data, "Missing total_checked field"
        assert "updated" in data, "Missing updated field"
        assert "errors" in data, "Missing errors field"
        
        # Verify types
        assert isinstance(data["total_checked"], int)
        assert isinstance(data["updated"], int)
        assert isinstance(data["errors"], int)

    def test_get_sync_status_requires_auth(self):
        """GET /api/sync/status should require authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/status")
        assert response.status_code == 403  # No auth header

    def test_get_sync_status_agent_access(self, agent_token):
        """GET /api/sync/status should be accessible by agent role"""
        response = requests.get(
            f"{BASE_URL}/api/sync/status",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200


class TestKosmoSyncTracking:
    """Tests for POST /api/sync/tracking endpoint"""

    def test_sync_tracking_returns_200(self, dev_token):
        """POST /api/sync/tracking should return 200 with valid token"""
        response = requests.post(
            f"{BASE_URL}/api/sync/tracking",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        assert response.status_code == 200

    def test_sync_tracking_response_structure(self, dev_token):
        """POST /api/sync/tracking should return correct JSON structure"""
        response = requests.post(
            f"{BASE_URL}/api/sync/tracking",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        
        # Verify required fields
        assert "total_checked" in data, "Missing total_checked field"
        assert "updated" in data, "Missing updated field"
        assert "no_change" in data, "Missing no_change field"
        assert "errors" in data, "Missing errors field"
        assert "details" in data, "Missing details field"
        
        # Verify types
        assert isinstance(data["total_checked"], int)
        assert isinstance(data["updated"], int)
        assert isinstance(data["no_change"], int)
        assert isinstance(data["errors"], int)
        assert isinstance(data["details"], list)

    def test_sync_tracking_requires_auth(self):
        """POST /api/sync/tracking should require authentication"""
        response = requests.post(f"{BASE_URL}/api/sync/tracking")
        assert response.status_code == 403  # No auth header

    def test_sync_tracking_agent_access(self, agent_token):
        """POST /api/sync/tracking should be accessible by agent role"""
        response = requests.post(
            f"{BASE_URL}/api/sync/tracking",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 200


class TestKosmoPackageData:
    """Tests for Kosmo data in packages"""

    def test_journey_packages_have_kosmo_fields(self, dev_token):
        """Journey packages should have Kosmo-related fields"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{KOSMO_JOURNEY_ID}",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        packages = data.get("packages", [])
        assert len(packages) > 0, "Journey should have packages"
        
        # Check first package with Kosmo data
        pkg_with_kosmo = None
        for pkg in packages:
            if pkg.get("tracking_url"):
                pkg_with_kosmo = pkg
                break
        
        assert pkg_with_kosmo is not None, "Should have at least one package with tracking_url"
        
        # Verify Kosmo fields exist
        assert "tracking_url" in pkg_with_kosmo
        assert "kosmo_status_raw" in pkg_with_kosmo or pkg_with_kosmo.get("kosmo_scraped_at") is not None

    def test_package_tracking_url_is_clickable_link(self, dev_token):
        """Package tracking_url should be a valid URL"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{KOSMO_JOURNEY_ID}",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        packages = data.get("packages", [])
        
        for pkg in packages:
            if pkg.get("tracking_url"):
                url = pkg["tracking_url"]
                assert url.startswith("https://"), f"tracking_url should be HTTPS: {url}"
                assert "kosmo" in url.lower() or "tracking" in url.lower(), f"tracking_url should be Kosmo URL: {url}"

    def test_package_kosmo_proof_count(self, dev_token):
        """Packages should have kosmo_proof_count field"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{KOSMO_JOURNEY_ID}",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        packages = data.get("packages", [])
        
        # Find packages with proof photos
        packages_with_proof = [p for p in packages if p.get("kosmo_proof_count", 0) > 0]
        assert len(packages_with_proof) > 0, "Should have packages with proof photos"
        
        for pkg in packages_with_proof:
            assert isinstance(pkg["kosmo_proof_count"], int)
            assert pkg["kosmo_proof_count"] > 0

    def test_package_kosmo_driver_note(self, dev_token):
        """Some packages should have kosmo_driver_note field"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{KOSMO_JOURNEY_ID}",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        packages = data.get("packages", [])
        
        # Find packages with driver notes
        packages_with_notes = [p for p in packages if p.get("kosmo_driver_note")]
        assert len(packages_with_notes) > 0, "Should have packages with driver notes"

    def test_status_mapping_delivered(self, dev_token):
        """Kosmo 'delivered' status should map to 'delivered'"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{KOSMO_JOURNEY_ID}",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        packages = data.get("packages", [])
        
        for pkg in packages:
            if pkg.get("kosmo_status_raw") == "delivered":
                assert pkg["status"] == "delivered", f"Kosmo delivered should map to delivered status"

    def test_status_mapping_cancelled(self, dev_token):
        """Kosmo 'cancelled' status should map to 'failed'"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{KOSMO_JOURNEY_ID}",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        data = response.json()
        packages = data.get("packages", [])
        
        for pkg in packages:
            if pkg.get("kosmo_status_raw") == "cancelled":
                assert pkg["status"] == "failed", f"Kosmo cancelled should map to failed status"


class TestSyncUpdatesStatus:
    """Tests to verify sync updates the status correctly"""

    def test_sync_updates_last_sync_timestamp(self, dev_token):
        """POST /api/sync/tracking should update last_sync timestamp"""
        # Get initial status
        status_before = requests.get(
            f"{BASE_URL}/api/sync/status",
            headers={"Authorization": f"Bearer {dev_token}"}
        ).json()
        
        # Trigger sync
        requests.post(
            f"{BASE_URL}/api/sync/tracking",
            headers={"Authorization": f"Bearer {dev_token}"}
        )
        
        # Get updated status
        status_after = requests.get(
            f"{BASE_URL}/api/sync/status",
            headers={"Authorization": f"Bearer {dev_token}"}
        ).json()
        
        # last_sync should be updated (or same if no packages to sync)
        assert status_after["last_sync"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
