"""
Constants for the Aster client.
"""

# API Configuration
DEFAULT_BASE_URL = "https://fapi.asterdex.com"
DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_MAX_RETRIES = 3

# Authentication Configuration
DEFAULT_RECV_WINDOW = 5000  # milliseconds

# HTTP Status Codes
SUCCESS_STATUS_CODE = 200
ERROR_STATUS_CODE = 500