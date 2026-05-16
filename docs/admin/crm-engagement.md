# Module: CRM & Engagement

## 1. Overview
The CRM module is the primary bridge between administrative staff and the platform's users. It facilitates proactive support, gathers community feedback, and manages platform-wide communications.

## 2. Key Functionalities

### 2.1 Ticket Management System
A structured way to handle user concerns, questions, and technical issues.
- **Support Inbox**: Centralized view of all incoming support requests.
- **Assignment & Resolution**: Routing tickets to the appropriate admin and tracking their time-to-resolution.
- **Issue Classification**: Categorizing tickets (e.g., "Login Issue", "Parsing Error", "Billing Question") to identify platform-wide trends.

### 2.2 Suggestions & Feedback Tracking
Giving Treasurers a voice in the platform's development.
- **Suggestion Box**: A dedicated area for users to submit feature requests and improvements.
- **Voting/Prioritization**: Allowing admins to gauge the popularity of specific suggestions.
- **Roadmap Integration**: Converting high-value suggestions into development tasks.

### 2.3 Platform Notifications & Broadcasting
Managing communication at scale.
- **System Alerts**: Broadcasting maintenance windows or platform updates to all users.
- **Automated Sequences**: Managing the "Welcome" series for new signups and "Churn Prevention" messages for expiring users.
- **Direct Messaging**: Admins can send targeted WhatsApp or SMS messages to specific Treasurers regarding their account status.

## 3. Data Captured for Auditing
- **Action**: (e.g., `TICKET_RESOLVED`, `BROADCAST_SENT`).
- **Entity**: Ticket ID or Broadcast ID.
- **Payload**: Message content and recipient list.
- **Metrics**: Open rates and response times.

## 4. Engagement Metrics
Admins track the following "Heartbeat" metrics:
- **Daily Active Treasurers (DAT)**.
- **Avg. Resolution Time** for support tickets.
- **Engagement Rate** for platform announcements.

---
**Security Note**: All platform broadcasts must be authorized by a `super_admin` to prevent spam or miscommunication.
