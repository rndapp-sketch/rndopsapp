"""
Test script for save_registration_section endpoint

This script demonstrates how to test the save_registration_section API endpoint
for all section types: basic, contact, bank, education, experience, organization, compliance

Usage:
    python test_save_registration_section.py
    
Note: This needs to be run in the Frappe context with proper test user setup
"""

import frappe
import json


def test_save_registration_section():
    """Test all section types for save_registration_section"""
    
    # Test user email (should already exist in Universal User__)
    test_user = "test.user@example.com"
    
    print("\n" + "="*70)
    print("Testing save_registration_section Endpoint")
    print("="*70)
    
    # =========================================================================
    # TEST 1: BASIC SECTION - INDIVIDUAL PROFILE
    # =========================================================================
    print("\n[TEST 1] Saving BASIC section (Individual Profile)")
    basic_individual_data = {
        "section_name": "basic",
        "section_data": {
            "full_name_u_r": "John Doe",
            "guardian_name_u_r": "Mr. Doe",
            "dob_u_r": "1990-05-15",
            "gender_u_r": "Male",
            "nationality_u_r": "India",
            "mobile_number_u_r": "+91-9876543210",
            "email_address_u_r": "john@example.com",
            "same_as_mobile_number_u_r": 1,
            "whatsapp_number_u_r": "+91-9876543210",
            "alternate_mobile_number_u_r": None,
            "address_details": [
                {
                    "address_line1": "123 Main St",
                    "address_line2": "Apt 4B",
                    "city": "Bangalore",
                    "state": "Karnataka",
                    "postal_code": "560001",
                    "country": "India"
                }
            ]
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=basic_individual_data
        )
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 2: CONTACT SECTION
    # =========================================================================
    print("\n[TEST 2] Saving CONTACT section")
    contact_data = {
        "section_name": "contact",
        "section_data": {
            "mobile_number_u_r": "+91-9876543210",
            "email_address_u_r": "john@example.com",
            "same_as_mobile_number_u_r": 1,
            "whatsapp_number_u_r": "+91-9876543210",
            "alternate_mobile_number_u_r": None
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=contact_data
        )
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 3: BANK SECTION
    # =========================================================================
    print("\n[TEST 3] Saving BANK section")
    bank_data = {
        "section_name": "bank",
        "section_data": {
            "bank_details_u_r": [
                {
                    "account_holder_name": "John Doe",
                    "account_number": "1234567890",
                    "account_type": "Savings",
                    "bank_name": "SBI",
                    "ifsc_code": "SBIN0001234",
                    "branch": "Bangalore Main"
                },
                {
                    "account_holder_name": "John Doe",
                    "account_number": "9876543210",
                    "account_type": "Current",
                    "bank_name": "ICICI Bank",
                    "ifsc_code": "ICIC0000123",
                    "branch": "Bangalore Branch"
                }
            ]
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=bank_data
        )
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 4: EDUCATION SECTION
    # =========================================================================
    print("\n[TEST 4] Saving EDUCATION section")
    education_data = {
        "section_name": "education",
        "section_data": {
            "qualifications_u_r": [
                {
                    "degree": "B.Tech",
                    "field_of_study": "Computer Science",
                    "institution": "IIT Bombay",
                    "completion_year": 2012,
                    "grade_percentage": 85
                },
                {
                    "degree": "M.Tech",
                    "field_of_study": "Computer Science",
                    "institution": "IIT Delhi",
                    "completion_year": 2014,
                    "grade_percentage": 8.9
                }
            ]
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=education_data
        )
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 5: EXPERIENCE SECTION
    # =========================================================================
    print("\n[TEST 5] Saving EXPERIENCE section")
    experience_data = {
        "section_name": "experience",
        "section_data": {
            "experiences_u_r": [
                {
                    "job_title": "Senior Developer",
                    "company_name": "Tech Corp",
                    "industry": "IT",
                    "start_date": "2012-06-01",
                    "end_date": "2015-05-31",
                    "is_current": 0,
                    "description": "Led development team"
                },
                {
                    "job_title": "Principal Engineer",
                    "company_name": "Tech Solutions Pvt Ltd",
                    "industry": "IT",
                    "start_date": "2015-06-01",
                    "end_date": None,
                    "is_current": 1,
                    "description": "Leading architecture and design"
                }
            ]
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=experience_data
        )
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 6: ORGANIZATION SECTION
    # =========================================================================
    print("\n[TEST 6] Saving ORGANIZATION section")
    organization_data = {
        "section_name": "organization",
        "section_data": {
            "org_name_u_r": "Tech Solutions Pvt Ltd",
            "est_date_u_r": "2010-05-15",
            "nature_of_business_u_r": "Software & IT Services",
            "website_u_r": "https://techsolutions.com",
            "contact_person_u_r": "Rajesh Kumar",
            "org_contact_number_u_r": "+91-8765432100",
            "type_of_business_u_r": "Supply",
            "other_business_type_u_r": None,
            "nature_of_org": "Company Registered",
            "pan_number_org_u_r": "AAAGT5055K",
            "gst_status_u_r": "Registered",
            "gst_number_u_r": "29AABG5055K1Z1"
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=organization_data
        )
        print(f"✓ Success: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 7: VALIDATION ERROR TEST
    # =========================================================================
    print("\n[TEST 7] Testing VALIDATION ERROR (Invalid mobile number)")
    invalid_data = {
        "section_name": "contact",
        "section_data": {
            "mobile_number_u_r": "123",  # Invalid - not 10 digits
            "email_address_u_r": "john@example.com",
            "same_as_mobile_number_u_r": 0,
            "whatsapp_number_u_r": None,
            "alternate_mobile_number_u_r": None
        }
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=invalid_data
        )
        if result.get("error_code") == "VALIDATION_ERROR":
            print(f"✓ Validation correctly caught error: {result.get('message')}")
        else:
            print(f"✗ Expected VALIDATION_ERROR but got: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    # =========================================================================
    # TEST 8: INVALID SECTION TEST
    # =========================================================================
    print("\n[TEST 8] Testing INVALID SECTION (Unknown section name)")
    invalid_section = {
        "section_name": "unknown_section",
        "section_data": {}
    }
    
    try:
        result = frappe.call(
            'rndopsapp.auth_api.save_registration_section',
            kwargs=invalid_section
        )
        if result.get("error_code") == "INVALID_SECTION":
            print(f"✓ Invalid section correctly caught: {result.get('message')}")
        else:
            print(f"✗ Expected INVALID_SECTION but got: {result}")
    except Exception as e:
        print(f"✗ Error: {str(e)}")
    
    print("\n" + "="*70)
    print("Testing Complete!")
    print("="*70 + "\n")


def test_validation_function():
    """Test the _validate_registration_section function directly"""
    from rndopsapp.auth_api import _validate_registration_section
    
    print("\n" + "="*70)
    print("Testing _validate_registration_section Function")
    print("="*70)
    
    # Test 1: Valid mobile number
    print("\n[TEST 1] Valid mobile number")
    is_valid, error = _validate_registration_section("contact", {
        "mobile_number_u_r": "+91-9876543210",
        "email_address_u_r": "valid@example.com"
    })
    print(f"Result: Valid={is_valid}, Error={error}")
    
    # Test 2: Invalid mobile number
    print("\n[TEST 2] Invalid mobile number (too short)")
    is_valid, error = _validate_registration_section("contact", {
        "mobile_number_u_r": "123",
        "email_address_u_r": "valid@example.com"
    })
    print(f"Result: Valid={is_valid}, Error={error}")
    
    # Test 3: Invalid email
    print("\n[TEST 3] Invalid email format")
    is_valid, error = _validate_registration_section("contact", {
        "mobile_number_u_r": "+91-9876543210",
        "email_address_u_r": "invalid-email"
    })
    print(f"Result: Valid={is_valid}, Error={error}")
    
    # Test 4: Invalid IFSC code
    print("\n[TEST 4] Invalid IFSC code format")
    is_valid, error = _validate_registration_section("bank", {
        "bank_details_u_r": [
            {
                "account_holder_name": "Test User",
                "account_number": "1234567890",
                "bank_name": "SBI",
                "ifsc_code": "INVALID"  # Wrong format
            }
        ]
    })
    print(f"Result: Valid={is_valid}, Error={error}")
    
    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    # Uncomment to run tests:
    # test_save_registration_section()
    # test_validation_function()
    
    print("Test script ready. Uncomment test functions in __main__ to run tests.")
