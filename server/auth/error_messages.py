AUTH_ERROR_MESSAGES = {
    "LOGIN_BAD_CREDENTIALS": "Invalid email or password. Please check your credentials and try again.",
    "LOGIN_USER_NOT_VERIFIED": "Your email address has not been verified. Please check your inbox for a verification email.",
    "REGISTER_USER_ALREADY_EXISTS": "An account with this email already exists. Please try logging in or use a different email.",
    "REGISTER_INVALID_PASSWORD": "The password does not meet the requirements. Please choose a stronger password.",
    "VERIFY_USER_BAD_TOKEN": "The verification link is invalid or has expired. Please request a new verification email.",
    "VERIFY_USER_ALREADY_VERIFIED": "Your email address has already been verified. You can log in now.",
    "RESET_PASSWORD_BAD_TOKEN": "The password reset link is invalid or has expired. Please request a new reset link.",
    "RESET_PASSWORD_INVALID_PASSWORD": "The new password does not meet the requirements. Please choose a stronger password.",
    "UPDATE_USER_EMAIL_ALREADY_EXISTS": "This email address is already in use by another account.",
    "UPDATE_USER_INVALID_PASSWORD": "The password does not meet the requirements.",
}


def get_auth_error_message(detail: str) -> str:
    detail_str = str(detail)
    if "ErrorCode." in detail_str:
        error_code = detail_str.split("ErrorCode.")[-1]
        return AUTH_ERROR_MESSAGES.get(error_code, detail_str)
    return AUTH_ERROR_MESSAGES.get(detail_str, detail_str)
