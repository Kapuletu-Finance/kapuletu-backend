import datetime

def get_base_template(content_html: str, title: str) -> str:
    """Wraps content in a highly professional, sleek Kapuletu layout."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #1e293b;
                background-color: #f8fafc;
                margin: 0;
                padding: 0;
                -webkit-font-smoothing: antialiased;
            }}
            .container {{
                max-width: 600px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 12px;
                overflow: hidden;
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
                border: 1px solid #e2e8f0;
            }}
            .header {{
                background-color: #ffffff;
                padding: 32px 40px;
                text-align: center;
                border-bottom: 1px solid #f1f5f9;
            }}
            .header h1 {{
                margin: 0;
                font-size: 26px;
                font-weight: 700;
                color: #16a34a; /* Kapuletu Green */
                letter-spacing: -0.5px;
            }}
            .content {{
                padding: 40px;
                font-size: 16px;
            }}
            .footer {{
                background-color: #f8fafc;
                color: #64748b;
                padding: 24px 40px;
                text-align: center;
                font-size: 12px;
                border-top: 1px solid #f1f5f9;
            }}
            .button {{
                display: inline-block;
                background-color: #16a34a; /* Kapuletu Green */
                color: #ffffff !important;
                text-decoration: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 15px;
                margin-top: 24px;
                margin-bottom: 16px;
                transition: background-color 0.2s ease;
                text-align: center;
            }}
            .button:hover {{
                background-color: #15803d;
            }}
            .meta-box {{
                background-color: #f1f5f9;
                border-radius: 8px;
                padding: 16px 20px;
                margin: 24px 0;
                border-left: 4px solid #16a34a;
            }}
            .meta-box p {{
                margin: 0;
                font-size: 14px;
            }}
            h2 {{
                color: #0f172a;
                font-size: 20px;
                margin-top: 0;
                margin-bottom: 16px;
                font-weight: 600;
            }}
            p {{
                margin-top: 0;
                margin-bottom: 16px;
                color: #334155;
            }}
            .muted {{
                color: #64748b;
                font-size: 13px;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>KapuLetu</h1>
            </div>
            <div class="content">
                {content_html}
            </div>
            <div class="footer">
                <p>&copy; {datetime.datetime.utcnow().year} KapuLetu Finance. Confidential & Proprietary.</p>
                <p>This is an automated system notification. Please do not reply.</p>
            </div>
        </div>
    </body>
    </html>
    """

def get_ticket_created_template(user_name: str, ticket_subject: str, ticket_id: str) -> str:
    content = f"""
    <h2>Support Request Received</h2>
    <p>Hi {user_name},</p>
    <p>We've successfully received your support request regarding <strong>"{ticket_subject}"</strong>.</p>
    <div class="meta-box">
        <p><strong>Ticket ID:</strong> <span style="font-family: monospace;">{ticket_id}</span></p>
    </div>
    <p>Our support engineers are reviewing your ticket and will follow up shortly. You can track the status in your dashboard.</p>
    <center>
        <a href="https://app.kapuletu.com/treasurer/support" class="button">View Ticket Status</a>
    </center>
    """
    return get_base_template(content, "Ticket Received - KapuLetu Support")

def get_admin_new_ticket_alert(user_name: str, ticket_subject: str, priority: str) -> str:
    priority_color = "#ef4444" if priority in ["urgent", "high"] else "#3b82f6"
    content = f"""
    <h2>New Support Ticket Alert</h2>
    <p>A new support ticket has been opened by <strong>{user_name}</strong>.</p>
    <div class="meta-box" style="border-left-color: {priority_color};">
        <p style="margin-bottom: 8px;"><strong>Subject:</strong> {ticket_subject}</p>
        <p><strong>Priority:</strong> <span style="color: {priority_color}; font-weight: 600; text-transform: uppercase;">{priority}</span></p>
    </div>
    <p>Please review and assign this ticket in the support queue.</p>
    <center>
        <a href="https://app.kapuletu.com/admin/support" class="button">Go to Support Queue</a>
    </center>
    """
    return get_base_template(content, f"New Ticket: {ticket_subject}")

def get_ticket_reply_template(ticket_subject: str, message_body: str, sender_name: str, is_admin: bool = True) -> str:
    title = f"New Reply: {ticket_subject}"
    role_text = "Kapuletu Support" if is_admin else "Treasurer"
    
    content = f"""
    <h2>New message on your ticket</h2>
    <p><strong>{sender_name} ({role_text})</strong> has replied to <strong>"{ticket_subject}"</strong>:</p>
    <div class="meta-box" style="border-left-color: #cbd5e1; background-color: #f8fafc;">
        {message_body.replace(chr(10), '<br>')}
    </div>
    <center>
        <a href="https://app.kapuletu.com/support" class="button">View Complete Thread</a>
    </center>
    """
    return get_base_template(content, title)

def get_employee_invite_template(first_name: str, role: str, setup_url: str) -> str:
    role_display = role.replace("_", " ").title()
    content = f"""
    <h2>Welcome to KapuLetu, {first_name}</h2>
    <p>You have been invited to join the KapuLetu internal administration team.</p>
    <div class="meta-box">
        <p><strong>Designated Role:</strong> {role_display}</p>
    </div>
    <p>Please configure your authentication credentials to securely access your workspace. Click below to begin the onboarding process.</p>
    <center>
        <a href="{setup_url}" class="button">Set Up Account</a>
    </center>
    <p class="muted">This secure link will expire in 24 hours. Contact your administrator if you require a new invitation.</p>
    """
    return get_base_template(content, "KapuLetu Team Invitation")
