"""
Test script for the HR Application API
Run this script to test the main endpoints
"""

import requests
import json

BASE_URL = "http://127.0.0.1:8000/api"

def print_response(title, response):
    """Pretty print API response"""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    print(f"Status Code: {response.status_code}")
    try:
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except:
        print(f"Response: {response.text}")
    print(f"{'='*60}\n")


def test_admin_login():
    """Test admin login"""
    url = f"{BASE_URL}/auth/login/"
    data = {
        "email": "admin@payrova.com",
        "password": "Admin@123456"
    }
    response = requests.post(url, json=data)
    print_response("1. ADMIN LOGIN", response)
    
    if response.status_code == 200:
        return response.json()['data']['tokens']['access']
    return None


def test_create_employer(admin_token):
    """Test creating employer account"""
    url = f"{BASE_URL}/admin/create-employer/"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    data = {
        "email": "employer.test@company.com"
    }
    response = requests.post(url, json=data, headers=headers)
    print_response("2. CREATE EMPLOYER ACCOUNT", response)
    
    if response.status_code == 201:
        # For testing, we'll return the token from response if available
        return response.json()['data'].get('activation_token')
    return None


def test_activate_account(activation_token):
    """Test account activation"""
    if not activation_token:
        print("\n⚠️  No activation token available. Check email or response.")
        return None
    
    url = f"{BASE_URL}/auth/activate/"
    data = {
        "token": activation_token,
        "password": "TestPassword123!",
        "confirm_password": "TestPassword123!"
    }
    response = requests.post(url, json=data)
    print_response("3. ACTIVATE ACCOUNT", response)
    return response.status_code == 200


def test_employer_login():
    """Test employer login"""
    url = f"{BASE_URL}/auth/login/"
    data = {
        "email": "employer.test@company.com",
        "password": "TestPassword123!"
    }
    response = requests.post(url, json=data)
    print_response("4. EMPLOYER LOGIN", response)
    
    if response.status_code == 200:
        return response.json()['data']['tokens']['access']
    return None


def test_get_profile(employer_token):
    """Test getting user profile"""
    url = f"{BASE_URL}/profile/"
    headers = {
        "Authorization": f"Bearer {employer_token}"
    }
    response = requests.get(url, headers=headers)
    print_response("5. GET USER PROFILE", response)


def test_setup_2fa(employer_token):
    """Test 2FA setup"""
    url = f"{BASE_URL}/auth/2fa/setup/"
    headers = {
        "Authorization": f"Bearer {employer_token}"
    }
    response = requests.post(url, headers=headers)
    print_response("6. SETUP 2FA", response)


def test_complete_profile(employer_token):
    """Test completing employer profile"""
    url = f"{BASE_URL}/employer/profile/complete/"
    headers = {
        "Authorization": f"Bearer {employer_token}",
        "Content-Type": "application/json"
    }
    data = {
        "company_name": "Test Tech Corporation Ltd",
        "employer_name_or_group": "Test Tech Group",
        "organization_type": "PRIVATE",
        "industry_sector": "Technology",
        "date_of_incorporation": "2020-01-15",
        "company_location": "Douala",
        "physical_address": "123 Test Business Street, Akwa, Douala",
        "phone_number": "+237699123456",
        "fax_number": "+237233123456",
        "official_company_email": "contact@testtech.cm",
        "rccm": "RC/DLA/2020/B/12345",
        "taxpayer_identification_number": "M012345678901Z",
        "cnps_employer_number": "1234567",
        "labour_inspectorate_declaration": "DIT/DLA/2020/123",
        "business_license": "P2020/12345",
        "bank_name": "Afriland First Bank",
        "bank_account_number": "10002000300040005",
        "bank_iban_swift": "CCBACMCXXXX"
    }
    response = requests.post(url, json=data, headers=headers)
    print_response("7. COMPLETE EMPLOYER PROFILE", response)


def test_get_employer_profile(employer_token):
    """Test getting employer profile"""
    url = f"{BASE_URL}/employer/profile/"
    headers = {
        "Authorization": f"Bearer {employer_token}"
    }
    response = requests.get(url, headers=headers)
    print_response("8. GET EMPLOYER PROFILE", response)


def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("HR APPLICATION API TEST SUITE")
    print("="*60)
    
    # Test 1: Admin Login
    admin_token = test_admin_login()
    if not admin_token:
        print("❌ Admin login failed. Cannot proceed with tests.")
        return
    
    print("✅ Admin login successful!")
    
    # Test 2: Create Employer
    activation_token = test_create_employer(admin_token)
    
    # Test 3: Activate Account (only if we have activation token)
    if activation_token:
        test_activate_account(activation_token)
        
        # Test 4: Employer Login
        employer_token = test_employer_login()
        
        if employer_token:
            print("✅ Employer login successful!")
            
            # Test 5: Get Profile
            test_get_profile(employer_token)
            
            # Test 6: Setup 2FA
            test_setup_2fa(employer_token)
            
            # Test 7: Complete Profile
            test_complete_profile(employer_token)
            
            # Test 8: Get Employer Profile
            test_get_employer_profile(employer_token)
    else:
        print("\n⚠️  Activation token not available in response.")
        print("This is expected if email backend is configured.")
        print("Check your email or console for the activation token.\n")
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETED")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to the server.")
        print("Please ensure the Django development server is running:")
        print("python manage.py runserver\n")
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}\n")
