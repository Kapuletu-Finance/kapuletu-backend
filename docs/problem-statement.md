KapuLetu Treasury Application
1. Problem Statement
1.1 Background
Community finance groups, commonly known as welfare groups, church fundraising committees, social contribution groups, and community-based organizations, rely heavily on treasurers to coordinate and manage member contributions, fundraising campaigns, and financial reporting.
In most cases, these financial activities are currently managed using manual and fragmented processes, such as:
WhatsApp messages
SMS payment confirmations
handwritten notebooks
spreadsheets
verbal confirmations
treasurer memory
This manual process introduces significant operational inefficiencies and financial risks.
1.2 Core Problem
Treasurers currently face major challenges in accurately recording, verifying, and reporting group financial transactions.
The current workflow is highly manual:
Members send money through M-Pesa, bank transfer, or cash
Payment confirmation messages are sent through SMS or WhatsApp
Treasurer manually reads and interprets messages
Records are entered into notebooks or Excel
Running balances are manually updated
Daily updates are posted in group chats



This process is:
slow
error-prone
difficult to audit
difficult to scale
As contribution volumes increase, the treasurer experiences workload fatigue, increasing the probability of mistakes.
1.3 Existing Challenges
 Fragmented Transaction Records
Payment confirmations are scattered across:
SMS inbox
WhatsApp chats
screenshots
voice notes
paper notes
This makes it difficult to track all contributions in one place.
High Risk of Missing Transactions
Treasurers can easily miss:
unread messages
deleted messages
duplicate forwards
cash contributions
delayed confirmations
This leads to incomplete financial records.











Duplicate and Inconsistent Entries
Without automated validation, the same payment may be recorded multiple times.
Example:
same M-Pesa transaction code entered twice
screenshot + forwarded message both recorded
This causes ledger inconsistencies.

No Structured Verification Workflow
Currently, there is no formal approval process before transactions are made official.
This means errors may be shared publicly before verification.

Weak Audit Trail
There is limited evidence preservation for:
who approved a payment
when it was approved
original payment message
rejected entries
edited records
This creates trust and accountability issues.






Poor Handling of Group Contributions
Often one member contributes on behalf of multiple people.
Example:
KES 5,000 paid for 5 members
Current systems do not support transaction splitting and allocation.

Cash Payments Are Poorly Managed
Cash contributions are frequently handled separately from digital payments.
This creates:
forgotten cash entries
inconsistent totals
reconciliation challenges

Reporting Fatigue
Treasurers spend excessive time preparing:
daily contribution summaries
member payment lists
campaign progress reports
meeting statements
This delays communication and reduces transparency.






1.4 Business Impact
The result of the above issues in the current treasury workflows  is:
low trust in financial reporting
contribution disputes
delayed reporting
inaccurate fundraising status
treasurer burnout
poor accountability
For community finance systems built on trust, these issues can significantly affect participation and group confidence.




2. Proposed Solution
2.1 Solution Overview
KapuLetu-Treasurer  is a treasurer-first community finance solution designed to assist treasurers in managing group contributions through a structured, intelligent, and auditable workflow.
The system does not replace the treasurer.
Instead, it acts as an intelligent treasury assistant that:
captures transactions
structures records
enables verification
maintains immutable ledgers
automates reporting





2.2 Proposed System Objectives
The proposed system aims to:
centralize all contribution records
automate transaction capture
reduce manual errors
preserve evidence of payments
support transaction approval workflows
improve transparency
simplify reporting
support future payment integrations









3. Proposed System Workflow Solution
3.1 Identity and Access Management Layer
This layer manages:
system admins
treasurers
future contributors/member accounts
It ensures only authorized users can:
approve transactions
create campaigns and groups 
generate reports
access ledgers
This improves security and accountability.

3.2 Input Capture Gateway
This is the system’s transaction entry point.
It captures both structured and unstructured financial evidence.
Supported Inputs
WhatsApp forwarded messages
SMS payment confirmations
manual cash entry
This ensures no contribution is left outside the system.
3.3 Intelligent Parsing Engine
This is the intelligence layer.
The system automatically converts payment messages into structured records.
Example extracted fields:
sender name
phone number
amount
transaction code
timestamp
payment method
contribution reference
This eliminates manual interpretation errors.

3.4 Treasurer Inbox and Review Queue
All incoming transactions first enter a Pending Inbox.
The treasurer reviews each transaction before approval.
 Actions - 
approve
reject
edit
split contribution
assign campaign
assign contributor
This preserves human oversight.
3.5 Smart Contribution Ledger
Once approved, the transaction moves into the official immutable ledger.
The ledger becomes the single source of truth.
Features include:
append-only records
no deletion
timestamped entries
approval traceability
correction via adjusting entries
This ensures strong financial integrity.




3.6 Campaign and Group Management
The system supports multiple:
welfare groups
church funds
project campaigns
emergency fundraising drives
So a treasurer creates a group then we have  campaigns inside that particular group. 
Each transaction is linked to a campaign.
Example:
School Fees Fund
Church Roof Fund
Welfare Support
Monthly Savings
This prevents mixing of group finances.
3.7 Split Contribution Allocation
The system allows one payment to be split among multiple contributors. This is during the approval of a transation
Example:
KES 5,000 may be allocated as:
John – 1,000
Mary – 1,000
Peter – 1,000
Jane – 1,000
Paul – 1,000
This improves fairness and recognition.


3.8 Evidence Preservation Layer
Every original payment message is stored as evidence.
This includes:
raw SMS text
forwarded WhatsApp text
transaction screenshots (future)
cash acknowledgment notes
This supports dispute resolution and audits.
3.9 Automated Reporting Service
The system automatically generates:
daily summaries
contributor lists
campaign progress reports
PDF statements
Excel exports
WhatsApp-ready updates
Example:
Today’s total: KES 25,000
 Contributors: John, Mary, Peter
 Campaign Progress: 62%
This reduces treasurer workload.




3.10 Feedback and User Experience Layer
The system will include a feedback module for collecting:
treasurer usability feedback
contributor complaints
improvement suggestions
issue reporting
This supports continuous improvement.



4. Future Proposed Enhancements (Phase 2)
Future versions of KapuLetu will include:
4.1 Native Payment Gateway
Members will pay directly inside the application through:
M-Pesa
cards
bank transfer
wallet accounts
This removes dependency on forwarded messages.
4.2 System-Generated Contribution Links
Treasurers can generate contribution links for campaigns.
Example:
“Church Roof Fund – Pay Here”
Members contribute directly via secure links.


4.3 Member Self-Service Accounts
Members can:
view payment history
confirm balances
download statements
track campaign progress

4.4 Intelligent Insights
AI-powered analytics can provide:
payment trends
contribution predictions
defaulter alerts
fundraising performance
5. Value Proposition
KapuLetu transforms community finance management from:
manual → structured
 stressful → assisted
 uncertain → auditable
 fragmented → centralized
It embeds trust directly into the system.

