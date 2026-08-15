def get_invitation_email_html(
    email: str,
    invitation_link: str,
    tenant_name: str,
    inviter_name: str,
    role: str,
    expiration_days: int = 7,
) -> str:
    role_display = role.capitalize()
    expiration_text = f"{expiration_days} day{'s' if expiration_days > 1 else ''}"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>You've Been Invited to Join {tenant_name}</title>
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
      padding: 30px 40px;
      text-align: center;
      max-width: 600px;
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
      max-width: 600px;
      margin: 0 auto;
    }}

    .content-card {{
      background-color: white;
      margin: 0 0 40px 0;
      padding: 40px 35px;
      border-radius: 0 0 8px 8px;
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08);
    }}

    .greeting {{
      font-size: 28px;
      font-weight: 400;
      color: #1f2937;
      margin-bottom: 25px;
      text-align: center;
    }}

    .message {{
      color: #4b5563;
      font-size: 15px;
      margin-bottom: 10px;
      line-height: 1.7;
    }}

    .message strong {{
      color: #1f2937;
    }}

    .button-wrapper {{
      text-align: center;
      margin: 30px 0;
    }}

    .accept-button {{
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

    .accept-button:hover {{
      background-color: #ea580c;
    }}

    .fallback-text {{
      color: #6b7280;
      font-size: 13px;
      margin-bottom: 8px;
    }}

    .fallback-link {{
      color: #f97316;
      font-size: 13px;
      text-decoration: underline;
      word-break: break-all;
      display: block;
      margin-bottom: 20px;
    }}

    .warning {{
      background-color: #fef3c7;
      border: 1px solid #fbbf24;
      border-radius: 6px;
      padding: 12px 15px;
      margin: 20px 0;
      font-size: 14px;
      color: #92400e;
    }}

    .ignore-text {{
      color: #6b7280;
      font-size: 14px;
      margin-top: 20px;
      line-height: 1.7;
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
  <div class="email-wrapper">
    <div class="header">
      <div class="logo">Byaan</div>
    </div>

    <div class="content-wrapper">
      <div class="content-card">
        <h1 class="greeting">You've Been Invited to Join {tenant_name}</h1>

        <p class="message">Hi there,</p>

        <p class="message">
          <strong>{inviter_name}</strong> has invited you to join <strong>{tenant_name}</strong> on Byaan as a(n) <strong>{role_display}</strong>. Click the button below to accept the invitation.
        </p>

        <div class="button-wrapper">
          <a href="{invitation_link}" class="accept-button">Accept Invitation</a>
        </div>

        <p class="fallback-text">Or copy and paste this link into your browser:</p>
        <a href="{invitation_link}" class="fallback-link">{invitation_link}</a>

        <div class="warning">
          <strong>⏰ Important:</strong> This invitation link will expire in {expiration_text}.
        </div>

        <p class="ignore-text">
          If you don't want to accept this invitation, you can just ignore this email.
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


def get_invitation_email_text(
    email: str,
    invitation_link: str,
    tenant_name: str,
    inviter_name: str,
    role: str,
    expiration_days: int = 7,
) -> str:
    role_display = role.capitalize()
    expiration_text = f"{expiration_days} day{'s' if expiration_days > 1 else ''}"

    return f"""
You've Been Invited to Join {tenant_name} on Byaan!

Hi there,

{inviter_name} has invited you to join {tenant_name} on Byaan as a {role_display}.

Team: {tenant_name}
Role: {role_display}

Accept the invitation by clicking the link below:

{invitation_link}

IMPORTANT: This invitation link will expire in {expiration_text}.

If you don't want to accept this invitation, please ignore this email.

© 2024 Byaan. All rights reserved.
""".strip()
