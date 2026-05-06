import re

with open("auto_annotate.py", "r") as f:
    content = f.read()

content = content.replace("{10}", "{8,12}")

pat14 = r'''    # 14. Confirmed. Ksh1,500.00 paid to NAIL POLISH beauty salon for account 12345 on 27/3/26
    re.compile(r"^(?P<CODE>[A-Z0-9]{8,12}) Confirmed\. (?:Ksh|KES)\s*(?P<AMOUNT>[\d,]+\.\d{2}) paid to (?P<PROVIDER>.*?) for account (?P<ACCOUNT>.*?) on (?P<DATE>\d{1,2}/\d{1,2}/\d{2,4})"),
]'''

content = content.replace("]", pat14)

with open("auto_annotate.py", "w") as f:
    f.write(content)
