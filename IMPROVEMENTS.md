# KapuLetu Platform Improvements & Roadmap

## 1. Feature Announcements & Changelogs

To seamlessly announce new features, updates, and enhancements to our users, we will implement a multi-layered announcement system consisting of two primary channels:

### A. The "What's New" Drawer (Changelog)
- **Concept:** A "Sparkle" (✨) or "Gift" (🎁) icon in the top navigation bar of the dashboard.
- **Behavior:**
  - When a new feature is deployed, the icon receives a notification badge (e.g., a red dot).
  - Clicking the icon opens a slide-out drawer (or modal) on the right side of the screen.
  - The drawer contains a timeline of recent updates, including short descriptions, images/GIFs, and "Try it out" call-to-action buttons.
- **Backend Requirements:**
  - A new database table `changelogs` to store release notes (title, description, image_url, created_at, active_status).
  - An endpoint `GET /changelogs` to fetch the timeline.
  - A mechanism to track the last time a user viewed the changelog to determine if the red notification dot should be active (e.g., `last_changelog_viewed_at` on the User model).

### B. System Broadcasts (Admin Inbox Announcements)
- **Concept:** Utilizing the existing Inbox module to send rich-text announcements directly to users.
- **Behavior:**
  - For massive updates (e.g., entirely new modules, pricing changes), administrators can broadcast a system message.
  - The message drops directly into the Inbox of targeted users (or all users) as a high-priority "System Message."
- **Backend Requirements:**
  - Extend the existing communications/inbox architecture to support a `system_broadcast` sender type.
  - An admin endpoint `POST /admin/broadcast` that can queue and deliver messages to all active users.
  - Support for rich-text (Markdown or HTML) rendering within the Inbox payload.

---

*Note: This document will be continually updated as we architect and plan new infrastructure enhancements.*
