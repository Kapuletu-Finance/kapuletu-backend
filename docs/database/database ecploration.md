docker exec -it kapuletu_db psql -U postgres -d kapuletu
This will drop you into the PostgreSQL interactive terminal. From there, you can type:

\dt (Press Enter to list all tables)
SELECT * FROM pending_transactions; (To view the parsed messages the AI just saved!)
\q (To exit and go back to normal terminal)