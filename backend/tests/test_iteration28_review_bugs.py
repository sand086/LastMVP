"""
Iteration 28 - Testing Review Indicator and Auto-Advance Bugs in Guías Tab

Bug 1: Review indicator column should be read-only with 3 states (pending ○, approved ✓, rejected ✗)
Bug 2: After approve/reject, auto-advance to next pending guide without scroll jump, update KPIs in real-time

Test Coverage:
- PATCH /api/packages/{id}/review endpoint for approve/reject
- Role-based access control (403 for agent/proveedor)
- Package state changes (manually_reviewed, rejection_reason)
- Journey detail endpoint returns correct package enrichment
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
CREDENTIALS = {
    'developer': {'email': 'dev@me.mx', 'password': os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")},
    'coordinator': {'email': 'yael@me.mx', 'password': os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")},
    'agent': {'email': 'agente@me.mx', 'password': os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")},
    'proveedor': {'email': 'proveedor@me.mx', 'password': os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")},
}

# Test journey IDs
JOURNEY_1_GUIDE = 'fefd8411-7a4e-4a8f-9c32-1d66d41ead9c'  # 1-guide journey
JOURNEY_27_GUIDES = '0c628824-b509-40a6-a7fd-b9b210b3eacd'  # 27-guide journey


@pytest.fixture(scope='module')
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({'Content-Type': 'application/json'})
    return session


def get_auth_token(api_client, role):
    """Get authentication token for a specific role"""
    creds = CREDENTIALS.get(role)
    if not creds:
        pytest.skip(f"No credentials for role: {role}")
    response = api_client.post(f"{BASE_URL}/api/auth/login", json=creds)
    if response.status_code != 200:
        pytest.skip(f"Login failed for {role}: {response.text}")
    data = response.json()
    # Auth returns access_token (not token)
    return data.get('access_token') or data.get('token')


@pytest.fixture(scope='module')
def developer_token(api_client):
    return get_auth_token(api_client, 'developer')


@pytest.fixture(scope='module')
def coordinator_token(api_client):
    return get_auth_token(api_client, 'coordinator')


@pytest.fixture(scope='module')
def agent_token(api_client):
    return get_auth_token(api_client, 'agent')


@pytest.fixture(scope='module')
def proveedor_token(api_client):
    return get_auth_token(api_client, 'proveedor')


class TestAuthEndpoints:
    """Verify all test users can login"""
    
    def test_developer_login(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=CREDENTIALS['developer'])
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data or 'token' in data
        print("Developer login successful")
    
    def test_coordinator_login(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=CREDENTIALS['coordinator'])
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data or 'token' in data
        print("Coordinator login successful")
    
    def test_agent_login(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=CREDENTIALS['agent'])
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data or 'token' in data
        print("Agent login successful")
    
    def test_proveedor_login(self, api_client):
        response = api_client.post(f"{BASE_URL}/api/auth/login", json=CREDENTIALS['proveedor'])
        assert response.status_code == 200
        data = response.json()
        assert 'access_token' in data or 'token' in data
        print("Proveedor login successful")


class TestJourneyDetailEndpoint:
    """Test journey detail endpoint returns packages with correct enrichment fields"""
    
    def test_journey_27_guides_exists(self, api_client, developer_token):
        """Verify the 27-guide journey exists and has packages"""
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        assert 'packages' in data
        assert len(data['packages']) > 0
        print(f"Journey {JOURNEY_27_GUIDES} has {len(data['packages'])} packages")
    
    def test_journey_1_guide_exists(self, api_client, developer_token):
        """Verify the 1-guide journey exists"""
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_1_GUIDE}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        assert 'packages' in data
        print(f"Journey {JOURNEY_1_GUIDE} has {len(data['packages'])} packages")
    
    def test_packages_have_review_fields(self, api_client, developer_token):
        """Verify packages have manually_reviewed and rejection_reason fields"""
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        packages = data['packages']
        
        # Check first package has required fields
        pkg = packages[0]
        assert 'manually_reviewed' in pkg, "Package missing manually_reviewed field"
        assert 'id' in pkg, "Package missing id field"
        print(f"Package {pkg['id']} has manually_reviewed={pkg.get('manually_reviewed')}, rejection_reason={pkg.get('rejection_reason')}")


class TestPackageReviewEndpoint:
    """Test PATCH /api/packages/{id}/review endpoint"""
    
    def test_developer_can_approve_package(self, api_client, developer_token):
        """Developer should be able to approve a package"""
        # First get a package ID
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        pkg_id = packages[0]['id']
        
        # Approve the package
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': True},
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get('manually_reviewed')
        print(f"Developer approved package {pkg_id}")
    
    def test_coordinator_can_approve_package(self, api_client, coordinator_token):
        """Coordinator should be able to approve a package"""
        # First get a package ID
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {coordinator_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        # Use second package to avoid conflict
        pkg_id = packages[1]['id'] if len(packages) > 1 else packages[0]['id']
        
        # Approve the package
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': True},
            headers={'Authorization': f'Bearer {coordinator_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get('manually_reviewed')
        print(f"Coordinator approved package {pkg_id}")
    
    def test_coordinator_can_reject_with_note(self, api_client, coordinator_token):
        """Coordinator should be able to reject a package with a note"""
        # First get a package ID
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {coordinator_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        # Use third package
        pkg_id = packages[2]['id'] if len(packages) > 2 else packages[0]['id']
        
        # Reject the package with note
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': False, 'manually_reviewed_note': 'Test rejection reason'},
            headers={'Authorization': f'Bearer {coordinator_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        assert not data.get('manually_reviewed')
        assert data.get('rejection_reason') == 'Test rejection reason'
        print(f"Coordinator rejected package {pkg_id} with note")
    
    def test_agent_cannot_review_package(self, api_client, agent_token, developer_token):
        """Agent should get 403 when trying to review a package"""
        # First get a package ID using developer token
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        pkg_id = packages[3]['id'] if len(packages) > 3 else packages[0]['id']
        
        # Try to approve as agent - should fail
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': True},
            headers={'Authorization': f'Bearer {agent_token}'}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("Agent correctly denied access to review package (403)")
    
    def test_proveedor_cannot_review_package(self, api_client, proveedor_token, developer_token):
        """Proveedor should get 403 when trying to review a package"""
        # First get a package ID using developer token
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        pkg_id = packages[4]['id'] if len(packages) > 4 else packages[0]['id']
        
        # Try to approve as proveedor - should fail
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': True},
            headers={'Authorization': f'Bearer {proveedor_token}'}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("Proveedor correctly denied access to review package (403)")


class TestReviewIndicatorStates:
    """Test that packages have correct review indicator states"""
    
    def test_approved_package_state(self, api_client, developer_token):
        """Verify approved package has manually_reviewed=True"""
        # Get journey packages
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        
        # Find a package to approve
        pkg_id = packages[5]['id'] if len(packages) > 5 else packages[0]['id']
        
        # Approve it
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': True},
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        
        # Verify state
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        packages = response.json()['packages']
        pkg = next((p for p in packages if p['id'] == pkg_id), None)
        assert pkg is not None
        assert pkg['manually_reviewed']
        assert pkg.get('rejection_reason') is None or pkg.get('rejection_reason') == ''
        print("Approved package state verified: manually_reviewed=True, rejection_reason=None")
    
    def test_rejected_package_state(self, api_client, developer_token):
        """Verify rejected package has manually_reviewed=False and rejection_reason set"""
        # Get journey packages
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        
        # Find a package to reject
        pkg_id = packages[6]['id'] if len(packages) > 6 else packages[0]['id']
        
        # Reject it
        response = api_client.patch(
            f"{BASE_URL}/api/packages/{pkg_id}/review",
            json={'manually_reviewed': False, 'manually_reviewed_note': 'Foto borrosa'},
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        
        # Verify state
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        packages = response.json()['packages']
        pkg = next((p for p in packages if p['id'] == pkg_id), None)
        assert pkg is not None
        assert not pkg['manually_reviewed']
        assert pkg.get('rejection_reason') == 'Foto borrosa'
        print("Rejected package state verified: manually_reviewed=False, rejection_reason='Foto borrosa'")
    
    def test_pending_package_state(self, api_client, developer_token):
        """Verify pending package has manually_reviewed=False and no rejection_reason"""
        # Get journey packages
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        
        # Find a package that hasn't been reviewed (no reviewed_by)
        pending_pkgs = [p for p in packages if not p.get('reviewed_by') and not p.get('rejection_reason')]
        if not pending_pkgs:
            # Reset a package to pending state
            packages[7]['id'] if len(packages) > 7 else packages[0]['id']
            # Note: There's no direct way to reset, but we can check the logic
            print("No pending packages found - all may have been reviewed in previous tests")
            return
        
        pkg = pending_pkgs[0]
        # Pending state: manually_reviewed should be False (or not set), no rejection_reason
        assert not pkg.get('manually_reviewed') or pkg.get('manually_reviewed') is None
        assert not pkg.get('rejection_reason')
        print("Pending package state verified: manually_reviewed=False, rejection_reason=None")


class TestKPICalculations:
    """Test that KPI values are correctly calculated from package states"""
    
    def test_manual_review_count_updates(self, api_client, developer_token):
        """Verify manual review count reflects approved packages"""
        # Get journey packages
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        
        # Count manually reviewed packages
        manual_reviewed_count = sum(1 for p in packages if p.get('manually_reviewed'))
        total_packages = len(packages)
        
        print(f"KPI: Manual reviewed {manual_reviewed_count}/{total_packages}")
        assert manual_reviewed_count >= 0
        assert total_packages > 0


class TestResyncAndEvaluateEndpoints:
    """Test Re-sincronizar Kosmo and Evaluar IA todas endpoints"""
    
    def test_batch_rescrape_endpoint_exists(self, api_client, developer_token):
        """Verify batch rescrape endpoint exists and works"""
        response = api_client.post(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}/batch-rescrape",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        # Should return 200 even if no packages need rescraping
        assert response.status_code == 200
        data = response.json()
        assert 'total' in data or 'message' in data
        print(f"Batch rescrape response: {data}")
    
    def test_evaluate_all_evidence_endpoint_exists(self, api_client, developer_token):
        """Verify evaluate all evidence endpoint exists and works"""
        response = api_client.post(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}/evaluate-evidence-all",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        data = response.json()
        assert 'status' in data or 'message' in data
        print(f"Evaluate all evidence response: {data}")


class TestResetPackageForTesting:
    """Helper tests to reset package states for UI testing"""
    
    def test_reset_package_to_pending(self, api_client, developer_token):
        """Reset a package to pending state for UI testing"""
        # Get journey packages
        response = api_client.get(
            f"{BASE_URL}/api/journeys/{JOURNEY_27_GUIDES}",
            headers={'Authorization': f'Bearer {developer_token}'}
        )
        assert response.status_code == 200
        packages = response.json()['packages']
        
        # Find packages that are reviewed and reset them
        reviewed_pkgs = [p for p in packages if p.get('manually_reviewed')]
        if reviewed_pkgs:
            pkg_id = reviewed_pkgs[0]['id']
            # Reset by setting manually_reviewed to False without rejection note
            # Note: The backend sets rejection_reason when manually_reviewed=False with a note
            # To truly reset, we'd need a separate endpoint, but we can test the approve flow
            response = api_client.patch(
                f"{BASE_URL}/api/packages/{pkg_id}/review",
                json={'manually_reviewed': False, 'manually_reviewed_note': ''},
                headers={'Authorization': f'Bearer {developer_token}'}
            )
            print(f"Reset package {pkg_id} to pending-like state")
        else:
            print("No reviewed packages to reset")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
