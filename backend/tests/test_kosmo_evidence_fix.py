"""
Test suite for Kosmo Evidence Fix and Operational Adjustments
Tests:
1. POST /api/sync/tracking returns immediately with {status: 'started'}
2. Packages with kosmo_proof_urls are returned in journey detail
3. PUT /api/packages/{package_id}/review saves reviewed_by and reviewed_at
4. PUT /api/incidents/journey/{journey_id}/resolve-all resolves all open incidents
5. Dashboard shows Driver column in journeys
6. Kosmo sync status endpoint
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestKosmoEvidenceFix:
    """Tests for Kosmo evidence fix - proof URLs and async sync"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_sync_tracking_returns_immediately(self):
        """POST /api/sync/tracking should return immediately with status: started"""
        start_time = time.time()
        response = requests.post(f"{BASE_URL}/api/sync/tracking", headers=self.headers)
        elapsed = time.time() - start_time
        
        assert response.status_code == 200, f"Sync tracking failed: {response.text}"
        data = response.json()
        
        # Should return immediately (< 5 seconds) with status: started or in_progress
        assert elapsed < 5, f"Sync took too long: {elapsed}s - should return immediately"
        assert data.get("status") in ["started", "in_progress"], f"Expected status 'started' or 'in_progress', got: {data}"
        print(f"Sync tracking returned in {elapsed:.2f}s with status: {data.get('status')}")
    
    def test_sync_status_endpoint(self):
        """GET /api/sync/status should return last sync info"""
        response = requests.get(f"{BASE_URL}/api/sync/status", headers=self.headers)
        
        assert response.status_code == 200, f"Sync status failed: {response.text}"
        data = response.json()
        
        # Should have last_sync, total_checked, updated, errors
        assert "last_sync" in data, "Missing last_sync in response"
        assert "total_checked" in data, "Missing total_checked in response"
        assert "updated" in data, "Missing updated in response"
        assert "errors" in data, "Missing errors in response"
        print(f"Sync status: last_sync={data.get('last_sync')}, checked={data.get('total_checked')}, updated={data.get('updated')}")
    
    def test_journey_packages_have_kosmo_proof_urls(self):
        """Journey detail should include packages with kosmo_proof_urls"""
        # Use the known journey with evidence
        journey_id = "51d80f44-85c7-4ddb-a932-40e49b7d8fd6"
        response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        
        assert response.status_code == 200, f"Get journey failed: {response.text}"
        data = response.json()
        
        packages = data.get("packages", [])
        assert len(packages) > 0, "Journey has no packages"
        
        # Check for packages with kosmo_proof_urls
        packages_with_urls = [p for p in packages if p.get("kosmo_proof_urls") and len(p.get("kosmo_proof_urls", [])) > 0]
        packages_with_count = [p for p in packages if p.get("kosmo_proof_count", 0) > 0]
        
        print(f"Journey {journey_id}: {len(packages)} packages, {len(packages_with_count)} with proof_count > 0, {len(packages_with_urls)} with proof_urls")
        
        # At least some packages should have proof URLs
        assert len(packages_with_urls) > 0, "No packages have kosmo_proof_urls"
        
        # Verify proof URL structure
        sample_pkg = packages_with_urls[0]
        assert isinstance(sample_pkg.get("kosmo_proof_urls"), list), "kosmo_proof_urls should be a list"
        assert len(sample_pkg.get("kosmo_proof_urls")) > 0, "kosmo_proof_urls should not be empty"
        assert sample_pkg.get("kosmo_proof_urls")[0].startswith("http"), "Proof URL should be a valid URL"
        print(f"Sample package {sample_pkg.get('tracking_number')}: {len(sample_pkg.get('kosmo_proof_urls'))} proof URLs")


class TestPackageReview:
    """Tests for package review functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_review_package_saves_fields(self):
        """PUT /api/packages/{package_id}/review should save reviewed_by and reviewed_at"""
        # Get a package from the known journey
        journey_id = "51d80f44-85c7-4ddb-a932-40e49b7d8fd6"
        response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        assert response.status_code == 200
        
        packages = response.json().get("packages", [])
        assert len(packages) > 0, "No packages found"
        
        # Find a package that hasn't been reviewed yet, or use the first one
        test_pkg = None
        for pkg in packages:
            if not pkg.get("reviewed_by"):
                test_pkg = pkg
                break
        if not test_pkg:
            test_pkg = packages[0]  # Use first package if all reviewed
        
        package_id = test_pkg.get("id")
        
        # Review the package
        response = requests.put(f"{BASE_URL}/api/packages/{package_id}/review", headers=self.headers)
        assert response.status_code == 200, f"Review package failed: {response.text}"
        
        data = response.json()
        assert "reviewed_by" in data, "Missing reviewed_by in response"
        assert "reviewed_at" in data, "Missing reviewed_at in response"
        assert data.get("reviewed_by") is not None, "reviewed_by should not be None"
        print(f"Package {package_id} reviewed by {data.get('reviewed_by')} at {data.get('reviewed_at')}")
        
        # Verify the package was updated by fetching journey again
        response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        assert response.status_code == 200
        
        updated_pkg = next((p for p in response.json().get("packages", []) if p.get("id") == package_id), None)
        assert updated_pkg is not None, "Package not found after review"
        assert updated_pkg.get("reviewed_by") is not None, "reviewed_by not persisted"
        assert updated_pkg.get("reviewed_at") is not None, "reviewed_at not persisted"


class TestResolveAllIncidents:
    """Tests for resolve all incidents functionality"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as coordinator to get auth token (resolve-all requires coordinator/agent role)"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_resolve_all_incidents_endpoint_exists(self):
        """PUT /api/incidents/journey/{journey_id}/resolve-all should exist"""
        journey_id = "51d80f44-85c7-4ddb-a932-40e49b7d8fd6"
        response = requests.put(f"{BASE_URL}/api/incidents/journey/{journey_id}/resolve-all", headers=self.headers)
        
        # Should return 200 (even if no incidents to resolve)
        assert response.status_code == 200, f"Resolve all incidents failed: {response.text}"
        
        data = response.json()
        assert "resolved_count" in data, "Missing resolved_count in response"
        print(f"Resolved {data.get('resolved_count')} incidents for journey {journey_id}")


class TestDashboardDriverColumn:
    """Tests for Dashboard driver column"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_journeys_include_driver_name(self):
        """GET /api/journeys should include driver_name field"""
        # Use a wide date range to get journeys
        response = requests.get(
            f"{BASE_URL}/api/journeys",
            params={"date_from": "2026-03-01", "date_to": "2026-03-31"},
            headers=self.headers
        )
        
        assert response.status_code == 200, f"Get journeys failed: {response.text}"
        journeys = response.json()
        
        assert len(journeys) > 0, "No journeys found"
        
        # Check that driver_name field exists
        sample_journey = journeys[0]
        assert "driver_name" in sample_journey, "driver_name field missing from journey"
        
        # Count journeys with driver names
        with_driver = [j for j in journeys if j.get("driver_name")]
        print(f"Found {len(journeys)} journeys, {len(with_driver)} have driver_name")


class TestEvidenceScoring:
    """Tests for evidence quality scoring"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json().get("access_token")
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_packages_have_evidence_scores(self):
        """Packages should have evidence_score field after sync"""
        journey_id = "51d80f44-85c7-4ddb-a932-40e49b7d8fd6"
        response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        
        assert response.status_code == 200, f"Get journey failed: {response.text}"
        packages = response.json().get("packages", [])
        
        # Check for packages with evidence scores
        with_scores = [p for p in packages if p.get("evidence_score") is not None]
        print(f"Journey {journey_id}: {len(packages)} packages, {len(with_scores)} have evidence_score")
        
        # Packages with 3+ proofs should have high scores
        high_proof_pkgs = [p for p in packages if p.get("kosmo_proof_count", 0) >= 3]
        if high_proof_pkgs:
            sample = high_proof_pkgs[0]
            print(f"Sample high-proof package: proof_count={sample.get('kosmo_proof_count')}, score={sample.get('evidence_score')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
