def get_password_reset_email_html(
    email: str,
    reset_link: str,
    name: str | None = None,
    expiration_hours: int = 1,
) -> str:
    greeting = f"Hi {name}" if name else "Hello"
    expiration_text = f"{expiration_hours} hour{'s' if expiration_hours > 1 else ''}"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reset Your Password</title>
  <style>
    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}

    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      background-color: #f5f5f5;
      line-height: 1.6;
    }}

    .email-wrapper {{
      background-color: #f5f5f5;
      min-height: 100vh;
      padding-top: 40px;
    }}

    .header {{
      background-color: #f97316;
      padding: 20px 40px;
      text-align: center;
      max-width: 1260px;
      margin: 0 auto;
      border-radius: 8px 8px 0 0;
    }}

    .logo {{
      color: white;
      font-size: 28px;
      font-weight: bold;
      letter-spacing: 1px;
    }}

    .content-wrapper {{
      max-width: 1260px;
      margin: 0 auto;
    }}

    .content-card {{
      background-color: white;
      margin: 0 0 40px 0;
      padding: 25px 80px;
      border-radius: 0 0 8px 8px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
    }}

    .greeting {{
      font-size: 22px;
      font-weight: 700;
      color: #1f2937;
      margin-bottom: 15px;
      text-align: center;
    }}

    .message {{
      color: #4b5563;
      font-size: 15px;
      margin-bottom: 6px;
      line-height: 1.4;
    }}

    .message strong {{
      color: #1f2937;
    }}

    .button-wrapper {{
      text-align: center;
      margin: 15px 0;
    }}

    .reset-button {{
      display: inline-block;
      background-color: #f97316;
      color: white !important;
      text-decoration: none;
      padding: 14px 30px;
      border-radius: 6px;
      font-size: 16px;
      font-weight: 600;
      letter-spacing: 0.3px;
    }}

    .reset-button:hover {{
      background-color: #ea580c;
    }}

    .fallback-text {{
      color: #6b7280;
      font-size: 13px;
      margin-bottom: 6px;
    }}

    .fallback-link {{
      color: #f97316;
      font-size: 13px;
      text-decoration: underline;
      word-break: break-all;
      display: block;
      margin-bottom: 15px;
    }}

    .warning {{
      background-color: #fef3c7;
      border: 1px solid #fbbf24;
      border-radius: 6px;
      padding: 8px 15px;
      margin: 12px 0;
      font-size: 14px;
      color: #92400e;
      text-align: center;
    }}

    .ignore-text {{
      color: #6b7280;
      font-size: 14px;
      margin-top: 12px;
      line-height: 1.4;
    }}

    .footer {{
      text-align: center;
      color: #6b7280;
      font-size: 14px;
      margin-top: 15px;
      padding-top: 12px;
      border-top: 1px solid #e5e7eb;
    }}
  </style>
</head>
<body>
  <div class="email-wrapper">
    <div class="header">
      <div class="logo">Byaan</div>
    </div>

    <div class="content-wrapper">
      <div class="content-card">
        <h1 class="greeting">Reset Your Password</h1>

        <p class="message">{greeting},</p>

        <p class="message">
          We received a request to reset your password. Click the button below to set a new password:
        </p>

        <div class="button-wrapper">
          <a href="{reset_link}" class="reset-button">Reset Password</a>
        </div>

        <p class="fallback-text">Or copy and paste this link into your browser:</p>
        <a href="{reset_link}" class="fallback-link">{reset_link}</a>

        <div class="warning">
          <strong>⏰ Important:</strong> This reset link will expire in {expiration_text}.
        </div>

        <p class="ignore-text">
          If you didn't request a password reset, you can just ignore this email. Your password will remain unchanged.
        </p>

        <div class="footer">
          <p>© 2024 Byaan. All rights reserved.</p>
        </div>
      </div>
    </div>
  </div>
</body>
</html>
""".strip()


def get_password_reset_email_text(
    email: str,
    reset_link: str,
    name: str | None = None,
    expiration_hours: int = 1,
) -> str:
    greeting = f"Hi {name}" if name else "Hello"
    expiration_text = f"{expiration_hours} hour{'s' if expiration_hours > 1 else ''}"

    return f"""
{greeting},

We received a request to reset your password.

Click the link below to set a new password:

{reset_link}

IMPORTANT: This reset link will expire in {expiration_text}.

If you didn't request a password reset, please ignore this email. Your password will remain unchanged.

© 2024 Byaan. All rights reserved.
""".strip()
