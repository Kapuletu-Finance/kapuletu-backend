import subprocess
import sys
import os

def migrate():
    """
    Database Migration Utility: Updates the schema to the latest version using Alembic.
    """
    print("Executing schema synchronization and database migrations...")
    
    # Path to alembic executable in venv
    alembic_exe = os.path.join("venv", "Scripts", "alembic") if os.name == 'nt' else os.path.join("venv", "bin", "alembic")
    
    if not os.path.exists(alembic_exe) and not os.path.exists(alembic_exe + ".exe"):
        alembic_exe = "alembic" # Fallback to system alembic
        
    try:
        subprocess.run([alembic_exe, "upgrade", "head"], check=True)
        print("Migrations completed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"Error during migrations: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    migrate()
