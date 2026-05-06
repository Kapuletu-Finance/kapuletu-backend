import os
import sys
import time
from colorama import Fore, Style, init

# Initialize colorama for Windows terminal styling
init(autoreset=True)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

# Import our production singleton parser
from services.ingestion.parser_engine import parse_message

DEMO_FILE_PATH = os.path.join(BASE_DIR, "data", "demo_messages.txt")

def print_styled_box(title):
    print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "=" * 80)
    print(f"{Fore.CYAN}{Style.BRIGHT}      {title}")
    print(f"{Fore.CYAN}{Style.BRIGHT}" + "=" * 80 + "\n")

def run_demo():
    print_styled_box("KAPULETU AI: LIVE DEMONSTRATION ENGINE")
    
    if not os.path.exists(DEMO_FILE_PATH):
        print(f"{Fore.RED}[ERROR] The file 'data/demo_messages.txt' does not exist.")
        print(f"{Fore.YELLOW}Please create it and paste your raw messages inside (one message per line).")
        return

    with open(DEMO_FILE_PATH, "r", encoding="utf-8") as f:
        # Read lines, strip whitespace, and ignore empty lines
        messages = [line.strip() for line in f.readlines() if line.strip()]

    if not messages:
        print(f"{Fore.YELLOW}No messages found in 'data/demo_messages.txt'. Please paste some messages to test.")
        return

    print(f"{Fore.GREEN}Loaded {len(messages)} messages for live parsing...\n")
    time.sleep(1)

    for i, msg in enumerate(messages, 1):
        # Print Message Header
        print(f"{Fore.YELLOW}{Style.BRIGHT}[Message {i}]")
        print(f"{Fore.WHITE}{msg}\n")
        
        # Start AI Parse Timer
        start_time = time.time()
        
        # --- THE MAGIC HAPPENS HERE ---
        result = parse_message(msg)
        # ------------------------------
        
        elapsed_time = (time.time() - start_time) * 1000 # convert to milliseconds
        
        # Print Beautiful Output
        print(f"{Fore.GREEN}{Style.BRIGHT}[AI] Extraction Results (took {elapsed_time:.2f}ms):")
        
        # Sender
        sender = result.get('sender_name')
        if sender: print(f"  {Fore.CYAN}> SENDER   :{Fore.WHITE} {sender}")
        else:      print(f"  {Fore.CYAN}> SENDER   :{Fore.RED} [Not Found]")
            
        # Provider
        provider = result.get('provider')
        if provider: print(f"  {Fore.CYAN}> PROVIDER :{Fore.WHITE} {provider}")
        else:        print(f"  {Fore.CYAN}> PROVIDER :{Fore.RED} [Not Found]")
            
        # Amount
        amt = result.get('amount', 0.0)
        print(f"  {Fore.CYAN}> AMOUNT   :{Fore.GREEN}{Style.BRIGHT} KES {amt:,.2f}")
        
        # Code
        code = result.get('transaction_code')
        if code: print(f"  {Fore.CYAN}> CODE     :{Fore.WHITE} {code}")
        else:    print(f"  {Fore.CYAN}> CODE     :{Fore.RED} [Not Found]")
            
        # Account
        account = result.get('account')
        if account: print(f"  {Fore.CYAN}> ACCOUNT  :{Fore.WHITE} {account}")
            
        # Date
        date = result.get('transaction_date')
        if date: print(f"  {Fore.CYAN}> DATE     :{Fore.WHITE} {date}")

        print(f"\n{Fore.BLACK}{Style.BRIGHT}" + "-" * 80 + "\n")
        
    print_styled_box("DEMONSTRATION COMPLETE")
    print(f"{Fore.WHITE}To test more messages, open {Fore.GREEN}'data/demo_messages.txt'{Fore.WHITE}, paste them there, and run this script again!")

if __name__ == "__main__":
    run_demo()
