"""Email template functions for verification emails"""

from dataclasses import dataclass


@dataclass
class EmailTemplateData:
    """Data required for email templates"""

    email: str
    verification_link: str
    expiration_hours: int
    name: str | None = None


def get_verification_email_html(data: EmailTemplateData) -> str:
    """Generate HTML version of verification email"""
    greeting = f"Hi {data.name}" if data.name else "Hello"
    expiration_text = f"{data.expiration_hours} hour{'s' if data.expiration_hours > 1 else ''}"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verify Your Email</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      max-width: 600px;
      margin: 0 auto;
      padding: 20px;
      background-color: #f4f4f4;
    }}
    .container {{
      background-color: #ffffff;
      border-radius: 10px;
      padding: 40px;
      box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }}
    .header {{
      text-align: center;
      margin-bottom: 30px;
    }}
    .logo {{
      font-size: 32px;
      font-weight: bold;
      color: #2563eb;
      margin-bottom: 10px;
    }}
    h1 {{
      color: #1f2937;
      font-size: 24px;
      margin-bottom: 20px;
    }}
    .content {{
      margin-bottom: 30px;
    }}
    .button-container {{
      text-align: center;
      margin: 30px 0;
    }}
    .verify-button {{
      display: inline-block;
      padding: 14px 30px;
      background-color: #2563eb;
      color: #ffffff;
      text-decoration: none;
      border-radius: 6px;
      font-weight: 600;
      font-size: 16px;
    }}
    .verify-button:hover {{
      background-color: #1d4ed8;
    }}
    .link-text {{
      color: #6b7280;
      font-size: 12px;
      word-break: break-all;
      margin-top: 20px;
    }}
    .warning {{
      background-color: #fef3c7;
      border: 1px solid #fbbf24;
      border-radius: 6px;
      padding: 12px;
      margin-top: 20px;
      font-size: 14px;
      color: #92400e;
    }}
    .footer {{
      text-align: center;
      color: #6b7280;
      font-size: 14px;
      margin-top: 30px;
      padding-top: 20px;
      border-top: 1px solid #e5e7eb;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo">Byaan!</div>
      <h1>Verify Your Email Address</h1>
    </div>

    <div class="content">
      <p>{greeting},</p>

      <p>Thank you for joining Byaan! To complete your registration and verify your email address, please click the button below:</p>

      <div class="button-container">
        <a href="{data.verification_link}" class="verify-button" style="color: white;">Verify Email Address</a>
      </div>

      <p class="link-text">Or copy and paste this link into your browser:<br>{data.verification_link}</p>

      <div class="warning">
        <strong>⏰ Important:</strong> This verification link will expire in {expiration_text}. Please verify your email before it expires.
      </div>

      <p>Once verified, you'll be able to start using Byaan to analyze your data locally and securely.</p>

      <p>If you didn't sign up for Byaan, please ignore this email.</p>
    </div>

    <div class="footer">
      <p>© 2026 Byaan. All rights reserved.</p>
      <p>This is an automated message. Please do not reply to this email.</p>
    </div>
  </div>
</body>
</html>
""".strip()


def get_verification_email_text(data: EmailTemplateData) -> str:
    """Generate plain text version of verification email"""
    greeting = f"Hi {data.name}" if data.name else "Hello"
    expiration_text = f"{data.expiration_hours} hour{'s' if data.expiration_hours > 1 else ''}"

    return f"""
{greeting},

Thank you for joining Byaan!

To complete your registration and verify your email address, please click the link below:

{data.verification_link}

IMPORTANT: This verification link will expire in {expiration_text}. Please verify your email before it expires.

Once verified, you'll be able to start using Byaan to analyze your data locally and securely.

If you didn't sign up for Byaan, please ignore this email.

© 2026 Byaan. All rights reserved.
This is an automated message. Please do not reply to this email.
""".strip()
