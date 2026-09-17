import datetime

def get_base_template(content_html: str, title: str) -> str:
    """Wraps content in a professional, responsive layout."""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{title}</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                line-height: 1.6;
                color: #333333;
                background-color: #f9fafb;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 40px auto;
                background-color: #ffffff;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
            }}
            .header {{
                background-color: #111827;
                color: #ffffff;
                padding: 24px 32px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
                font-weight: 600;
                letter-spacing: 0.5px;
            }}
            .content {{
                padding: 32px;
            }}
            .footer {{
                background-color: #f3f4f6;
                color: #6b7280;
                padding: 24px;
                text-align: center;
                font-size: 13px;
            }}
            .button {{
                display: inline-block;
                background-color: #2563eb;
                color: #ffffff;
                text-decoration: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: 500;
                margin-top: 16px;
            }}
            .quote {{
                border-left: 4px solid #e5e7eb;
                padding-left: 16px;
                color: #4b5563;
                margin: 24px 0;
                font-style: italic;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>KapuLetu Finance</h1>
            </div>
            <div class="content">
                {content_html}
            </div>
            <div class="footer">
                <p>&copy; {datetime.datetime.utcnow().year} KapuLetu Finance. All rights reserved.</p>
                <p>This is an automated message, please do not reply directly to this email.</p>
            </div>
        </div>
    </body>
    </html>
    """

def get_ticket_created_template(user_name: str, ticket_subject: str, ticket_id: str) -> str:
    content = f"""
    <h2>Support Request Received</h2>
    <p>Hi {user_name},</p>
    <p>We've received your support request regarding <strong>"{ticket_subject}"</strong>.</p>
    <p>Our support team is reviewing it and will get back to you as soon as possible. You can view the status of your ticket and add additional comments from your dashboard.</p>
    <p>Ticket ID: <span style="color: #6b7280; font-family: monospace;">{ticket_id}</span></p>
    <a href="https://app.kapuletu.com/treasurer/support" class="button">View Ticket</a>
    """
    return get_base_template(content, "Ticket Received - KapuLetu Support")

def get_admin_new_ticket_alert(user_name: str, ticket_subject: str, priority: str) -> str:
    priority_color = "#ef4444" if priority in ["urgent", "high"] else "#3b82f6"
    content = f"""
    <h2>New Support Ticket Alert</h2>
    <p>A new support ticket has been opened by <strong>{user_name}</strong>.</p>
    <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 20px 0;">
        <p style="margin: 0 0 8px 0;"><strong>Subject:</strong> {ticket_subject}</p>
        <p style="margin: 0;"><strong>Priority:</strong> <span style="color: {priority_color}; font-weight: 600; text-transform: uppercase;">{priority}</span></p>
    </div>
    <p>Please review and assign this ticket promptly.</p>
    <a href="https://app.kapuletu.com/admin/support" class="button">Go to Support Queue</a>
    """
    return get_base_template(content, f"New Ticket: {ticket_subject}")

def get_ticket_reply_template(ticket_subject: str, message_body: str, sender_name: str, is_admin: bool = True) -> str:
    title = f"New Reply: {ticket_subject}"
    role_text = "Kapuletu Support" if is_admin else "Treasurer"
    
    content = f"""
    <h2>New message regarding your ticket</h2>
    <p><strong>{sender_name} ({role_text})</strong> has replied to <strong>"{ticket_subject}"</strong>:</p>
    <div class="quote">
        {message_body.replace(chr(10), '<br>')}
    </div>
    <a href="https://app.kapuletu.com/support" class="button">View Thread</a>
    """
    return get_base_template(content, title)
