# KapuLetu Database Exploration Guide

To enter the database from your terminal, run:
```bash
docker exec -it kapuletu_db psql -U postgres -d kapuletu
```

## 🛠️ PostgreSQL (`psql`) Core Commands
These are commands used to navigate the database structure itself. You must type the `\` before them.

* `\dt` - List all tables in the database.
* `\d pending_transactions` - View the schema/columns of the `pending_transactions` table.
* `\d users` - View the schema/columns of the `users` table.
* `\x` - Toggle "Expanded Display" (highly recommended). This makes long rows easier to read by displaying columns vertically instead of wrapping across the screen!
* `\q` - Quit and exit the database.

---

## 🔍 Essential SQL Queries (KapuLetu Specific)

### 1. Pending Transactions (The AI Parsing Results)
**View the 5 most recent parsed transactions:**
```sql
SELECT created_at, sender_name, amount, transaction_code, workflow_status 
FROM pending_transactions 
ORDER BY created_at DESC 
LIMIT 5;
```

**Find a transaction by its M-Pesa code:**
```sql
SELECT * FROM pending_transactions WHERE transaction_code = 'UDJJO182MS';
```

**See the raw message vs what the AI extracted:**
```sql
SELECT raw_message, sender_name, amount, confidence_score 
FROM pending_transactions 
ORDER BY created_at DESC 
LIMIT 1;
```

### 2. Treasurers and Users
**See all registered treasurers:**
```sql
SELECT full_name, phone_number, role, is_active FROM users;
```

### 3. Approved / Finalized Ledger
**View finalized transactions that have been approved by the treasurer:**
```sql
SELECT amount, entry_type, balance_after 
FROM ledger_entries 
ORDER BY created_at DESC 
LIMIT 5;
```

## 💡 Pro-Tips for the Terminal
1. **Always end SQL queries with a semicolon `;`** 
   If you press enter and nothing happens (and the prompt turns into `kapuletu-#`), it means you forgot the semicolon! Just type `;` and hit Enter.
2. **Clear the screen:** Press `CTRL + L` to clear the terminal if it gets too cluttered.
3. **Scroll through history:** Use the UP and DOWN arrow keys to reuse commands you typed previously.
