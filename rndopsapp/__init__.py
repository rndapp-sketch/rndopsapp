__version__ = "0.0.1"
# Import API functions to make them accessible at module level
from .api import (
    get_universal_user_by_email,
    get_existing_registration,
    get_or_load_user_registration,
    save_universal_registration_data,
    get_universal_registration_list,
    get_universal_registration_details,
    update_universal_registration_data,
    get_universal_registration_by_email,
    get_universal_registration_by_phone,
    search_universal_registration,
    get_universal_registration_by_profile_type
)

__all__ = [
    'get_universal_user_by_email',
    'get_existing_registration',
    'get_or_load_user_registration',
    'save_universal_registration_data',
    'get_universal_registration_list',
    'get_universal_registration_details',
    'update_universal_registration_data',
    'get_universal_registration_by_email',
    'get_universal_registration_by_phone',
    'search_universal_registration',
    'get_universal_registration_by_profile_type'
]