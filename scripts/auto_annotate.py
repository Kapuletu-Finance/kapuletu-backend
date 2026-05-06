import re
import json
import os

INPUT_FILE = r"c:\Users\josep\kapuletu-backend\data\merged_training_data.txt"
OUTPUT_FILE = r"c:\Users\josep\kapuletu-backend\data\merged_annotated_dataset.json"

patterns = [
    # 1. Confirmed.You have received Ksh700.00 from Jane Wanjiru on 4/4/26
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\.You have received (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) from (?P<SENDER>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
    # 2. Confirmed. On 27/03/26 at 03:42 AM Give Ksh40,914.84 cash to Kariuki M-PESA Shop New
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\. On (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4}) at [\d: AMP]+ Give (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) cash to (?P<SENDER>.*?) New"),
    # 3. Your transaction of KES 7,554.44 has been received by KOBBI'S OVEN LIMITED (Acc 426786) on 12/09/25 at 04:36 AM Ref: U62PIEJN8K.
    re.compile(r"^Your transaction of (?:KES|Ksh)\s*(?P<AMOUNT>[\d,]+\.\d{2}) has been received by (?P<SENDER>.*?) \(Acc (?P<ACCOUNT>.*?)\) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4}).*?Ref:\s*(?P<CODE>[A-Z0-9]{8,12})"),
    # 4. Confirmed. Ksh2,405.74 paid to KEIL WB HEALTH LTD. on 01/03/25
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\. (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) paid to (?P<SENDER>.*?)\. on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
    # 5. Confirmed. Ksh42,723.12 sent to Kaps Parking JujaMall for account YMKBWVNE on 15/03/26
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\. (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) sent to (?P<PROVIDER>.*?) for account (?P<ACCOUNT>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
    # 6. Confirmed. Your M-PESA transaction UCNP3A8KWD of Ksh 1500.00 to KCB Paybill A/C for account 517335200315**** on 23/03/2026
    re.compile(r"^Confirmed\. Your M-PESA transaction (?P<CODE>[A-Z0-9]{8,12}) of (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) to (?P<PROVIDER>.*?) for account (?P<ACCOUNT>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
    # 7. Confirmed. Ksh265.26 sent to ESTHER KIPKEMBOI 0737064578 on 17/01/26
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\. (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) sent to (?P<SENDER>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
    
    # 8. Dear PETER KINYANJUI, you have sent Ksh. 1527.01 to ...
    re.compile(r"^Dear .*?, you have sent (?:Ksh|KES)\.?\s*(?P<AMOUNT>[\d,]+\.\d{2}) to (?P<PROVIDER>.*?) for (?P<ACCOUNT>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4}).*?Ref\.?\s*(?P<CODE>[A-Z0-9]{8,12})"),
    
    # 9. Dear Member,You have withdrawn Ksh. 5,329.88 from Account ...
    re.compile(r"^Dear Member,You have withdrawn (?:Ksh|KES)\.?\s*(?P<AMOUNT>[\d,]+\.\d{2}) from Account (?P<ACCOUNT>.*?)\s*\.Thank you for using (?P<PROVIDER>.*?) Mobile Banking"),
    
    # 10. You have received KES 386.66 from JOHN DOE. M-PESA Ref UYH3JBJ20Q.
    re.compile(r"^You have received (?:Ksh|KES)\.?\s*(?P<AMOUNT>[\d,]+\.\d{2}) from (?P<SENDER>.*?)\.\s*M-PESA Ref (?P<CODE>[A-Z0-9]{8,12})"),
    
    # 11. Reversal of transaction UYH3JBJ20Q has been successfully done...
    re.compile(r"^Reversal of transaction (?P<CODE>[A-Z0-9]{8,12}) has been successfully done\. (?:Ksh|KES)\.?\s*(?P<AMOUNT>[\d,]+\.\d{2}) has been credited to your account from (?P<SENDER>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),

    # 12. Dear Member, you have deposited Ksh. 5,329.88 to A/C No. ...
    re.compile(r"^Dear Member, you have deposited (?:Ksh|KES)\.?\s*(?P<AMOUNT>[\d,]+\.\d{2}) to A/C No\. (?P<ACCOUNT>.*?), of (?P<PROVIDER>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),

    # 13. Confirmed. Payment of Ksh 400.00 to SENDER Till No. 0708613560 has been received. Ref. UYH3JBJ20Q on ...
    re.compile(r"^Confirmed\. Payment of (?:Ksh|KES)\.?\s*(?P<AMOUNT>[\d,]+\.\d{2}) to (?P<SENDER>.*?) Till No\. .*? has been received\. Ref\. (?P<CODE>[A-Z0-9]{8,12}) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),

    # 14. Confirmed. Ksh1,500.00 paid to NAIL POLISH beauty salon for account 12345 on 27/3/26
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\. (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) paid to (?P<PROVIDER>.*?) for account (?P<ACCOUNT>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
]

dataset = []
failed_lines = []

with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line: continue
        
        matched = False
        for pat in patterns:
            match = pat.search(line)
            if match:
                entities = []
                for label, value in match.groupdict().items():
                    if value:
                        start = match.start(label)
                        end = match.end(label)
                        entities.append([start, end, label])
                dataset.append({"text": line, "entities": entities})
                matched = True
                break
        if not matched:
            failed_lines.append(line)

with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(dataset, f, indent=2)

print(f"Successfully annotated {len(dataset)} messages.")
print(f"Failed to annotate {len(failed_lines)} messages.")
if failed_lines:
    print("Example failures:")
    for l in failed_lines[:5]:
        print(" -", l)
