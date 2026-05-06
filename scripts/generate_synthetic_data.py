import os
import json
import random
import string
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "synthetic_dataset.json")

FIRST_NAMES = ["JOHN", "MARY", "PETER", "JANE", "DAVID", "SARAH", "GEORGE", "LUCY", "PAUL", "GRACE", "MICHAEL", "FAITH", "STEPHEN", "JOYCE", "DANIEL", "RUTH", "JOSEPH", "ESTHER", "JAMES", "CAROLINE", "PATRICK", "BEATRICE", "MARTIN", "ALICE", "KEVIN", "FLORENCE", "BRIAN", "MARGARET", "SAMUEL", "ROSE", "RICHARD", "AGNES", "CHARLES", "EUNICE", "WILLIAM", "JANE", "SIMON", "LILIAN", "DENIS", "MILLICENT", "AMOS", "GLADYS", "VICTOR", "MERCY", "EDWARD", "IRENE", "ANTONY", "JACQUELINE", "TITUS", "PENINAH", "COLLINS", "SYLVIA", "EVANS", "DOROTHY", "GIDEON", "PAULINE", "ELIAS", "NANCY", "FELIX", "ANNE", "BENARD", "NAOMI"]
LAST_NAMES = ["KAMAU", "NJOROGE", "OCHIENG", "KIPKORIR", "MWANGI", "MUTUA", "WANGUI", "ATIENO", "KIPRONO", "WEKESA", "NANJALA", "OMONDI", "WAMBUI", "KIPCHUNGE", "NDUNGU", "WANGARI", "MUTUKU", "NJERI", "OTIENO", "MUTHONI", "KARIUKI", "WAITHIRA", "KIPTOO", "WANJIKU", "KIPROTICH", "NYAMBURA", "MAINA", "KEMUNTO", "ONYANGO", "AWINO", "AUMA", "KIPKEMBOI", "WANJIRU", "MUTISO", "ODHIAMBO", "MACHARIA", "CHERUIYOT", "WAWERU", "KIPLAGAT", "NDAMBUKI", "NGUGI", "OMARI", "WANYONYI", "KIBET", "KINYANJUI", "ODINGO", "KIMANI", "GITHINJI", "WAFULA", "MWANIA", "MWITA", "BARASA", "KIPCHIRCHIR", "OKOTH", "MUKAMI", "KIPROP", "MUSEMBI", "WACHIRA", "KIPRUTO", "NYABOKE"]

# Generating 1,500+ individual names by mixing
INDIVIDUAL_NAMES = [f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}" for _ in range(1500)]

BUSINESS_PREFIXES = ["QUICKMART", "NAIVAS", "TOTAL", "RUBIS", "SHELL", "CLEANSHELF", "CHANDARANA", "ZUKU", "JAMII", "KPLC", "NAIROBI WATER", "M-KOPA", "CARREFOUR", "JAVA", "ARTCAFE", "GALITOS", "PIZZA INN", "KENTUCKY FRIED CHICKEN", "MULTICHOICE", "STARTIMES", "GOTV", "SAFARICOM", "AIRTEL", "TELKOM", "NHIF", "NSSF", "KRA", "HELB", "KUCCPS", "GOODLIFE", "MYDAWA", "KNH", "AGA KHAN", "STRATHMORE", "UNIVERSITY OF NAIROBI", "KENYATTA UNIVERSITY", "JABALI", "TUMAINI", "MATHAI", "CHICKEN INN", "CREAMY INN", "BAKERS INN", "AFYA", "BAMBURI", "MABATI", "CROWN", "BASCO", "SIMBA", "DT DOBIE", "TOYOTA", "ISUZU", "TATA", "KIBO", "BODABODA"]
BUSINESS_SUFFIXES = ["LTD", "ENTERPRISES", "SUPERMARKET", "HARDWARE", "PHARMACY", "CLINIC", "HOSPITAL", "MOTORS", "WHOLESALERS", "DISTRIBUTORS", "AGENCY", "CYBER", "M-PESA", "BOUTIQUE", "SALON", "KINESIOLOGY", "INVESTMENTS", "TRADERS", "SUPPLIES", "STORES", "MERCHANTS", "GROUP", "HOLDINGS"]

# Generating 800+ businesses
BUSINESS_NAMES = [f"{random.choice(BUSINESS_PREFIXES)} {random.choice(BUSINESS_SUFFIXES)}" for _ in range(800)]
BUSINESS_NAMES += BUSINESS_PREFIXES # Include prefixes on their own

NAMES = INDIVIDUAL_NAMES + BUSINESS_NAMES

BASE_BANKS = ["KCB", "EQUITY", "COOP", "ABSA", "NCBA", "STANBIC", "DTB", "FAMILY BANK", "I&M", "GULF AFRICAN BANK", "STANDARD CHARTERED", "SBM BANK", "POSTBANK", "UBA", "GUARANTY TRUST", "ACCESS BANK", "BANK OF AFRICA", "BANK OF BARODA", "BANK OF INDIA", "CHASE BANK", "IMPERIAL BANK", "NATIONAL BANK", "PRIME BANK", "VICTORIA COMMERCIAL", "SPREEDBANK", "CONSOLIDATED BANK", "CREDIT BANK", "DEVELOPMENT BANK", "DIAMOND TRUST", "DIB BANK", "ECOBANK", "EQUATORIAL COMMERCIAL", "FIRST COMMUNITY", "HABIB BANK", "MAYFAIR CIB", "MIDDLE EAST BANK", "M-ORIENTAL", "PARAMOUNT", "SIDIAN", "TRANSNATIONAL"]
SACCO_PREFIXES = ["STIMA", "HARAMBEE", "SAFARICOM", "MWALIMU", "KENYA POLICE", "UKULIMA", "BINGWA", "IMARIKA", "METROPOLITAN", "TOWER", "SHIRIKA", "ASILI", "KIMISITU", "WAUMINI", "HAZINA", "BANDARI", "MAGEREZA", "AFYA", "ELIMU", "USALAMA", "NAWASCO", "FUNDILIMA", "CHAI", "MENTOR", "OLLIN", "WINAS", "QWETU", "NATION", "BIASHARA", "AMICA", "WAKULIMA", "SOLUTION", "VISION", "FORTUNE", "EGERTON", "KEMRI", "KENGEN", "KPA", "KRA", "UN", "MOMBASA PORT", "KENYA AIRWAYS", "JAMII", "SHERIA", "TELEPOSTA", "MWINGI", "KITUI", "MACHAKOS", "MAKUENI", "EMBU", "MERU", "NYERI", "MURANGA", "KIAMBU", "NAKURU", "UASIN GISHU", "TRANS NZOIA", "BUNGOMA", "KAKAMEGA", "KISUMU", "SIAYA", "HOMA BAY", "MIGORI", "KISII", "NYAMIRA", "BOMET", "KERICHO", "NANDI", "BARINGO", "LAIKIPIA", "NYANDARUA", "KIRINYAGA", "THARAKA NITHI", "ISIOLO", "MARSABIT", "MANDERA", "WAJIR", "GARISSA", "TANA RIVER", "LAMU", "KILIFI", "KWALE", "TAITA TAVETA", "NAIROBI", "BUSIA", "VIHIGA", "ELGEYO MARAKWET", "WEST POKOT", "TURKANA", "SAMBURU", "NAROK", "KAJIADO", "IGEMBE", "TIMAU", "MAUA", "TIGANIA", "CHUKA", "RUNYENJES", "EMBU", "MWEA", "KERUGOYA", "KARATINA", "OTHAYA", "MUKURWEINI", "KANGEMA", "KIGUMO", "MARAGUA", "KANDARA", "GATANGA", "THIKA", "RUIRU", "JUJA", "KIKUYU", "LIMURU", "LARI", "GITHUNGURI", "KIAMBAA", "KABETE"]
SACCOS = [f"{s} SACCO" for s in SACCO_PREFIXES]
MICROFINANCES = ["FAULU", "KWFT", "SMEP", "MAISHA", "UWEZO", "BIMAS", "CENTENARY", "CHOICE", "DARAZA", "ECLOF", "JITEE", "KADET", "K-REP", "LETSHEGO", "MUSONI", "OPPORTUNITY", "PLATINUM", "RAFIKI", "REMU", "SAMA", "SMEP", "SUMAC", "U&I", "UNISON", "VISION", "YEHU", "WAKENYA PAMOJA", "K-MET", "K-RURAL", "K-URBAN", "K-YOUTH", "K-WOMEN", "K-MEN"]
MICROFINANCES = [f"{m} MICROFINANCE" for m in MICROFINANCES]
WALLETS = ["M-PESA", "AIRTEL MONEY", "T-KASH", "PESALINK", "WORLDBREMIT", "SENDWAVE", "REMITLY", "WESTERN UNION", "MONEYGRAM", "PAYPAL", "SKRILL", "NETELLER", "PAYONEER", "CHIPPER", "WAVE", "WISE", "REVOLUT", "AZIMO", "WORLDREMIT", "XOOM", "MUKURU", "HELLO PAISA", "MAMA MONEY", "SASAI", "TINGO"]

PROVIDERS = BASE_BANKS + SACCOS + MICROFINANCES + WALLETS

def generate_mpesa_code():
    # Real M-Pesa codes typically start with recent sequential letters (e.g., S, T, U, V)
    prefix = random.choice(["Q", "R", "S", "T", "U", "V"])
    return prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=9))

def build_template(template_str, replacements):
    entities = []
    matches = list(re.finditer(r"\[([A-Z_0-9]+)\]", template_str))
    new_text = ""
    last_end = 0
    
    for match in matches:
        key = match.group(1)
        # Handle the case where a template has [DATE_1] or [DATE_2] by mapping it to DATE
        label = key.split("_")[0] 
        val = str(replacements.get(key, match.group(0)))
        
        new_text += template_str[last_end:match.start()]
        start_idx = len(new_text)
        new_text += val
        end_idx = len(new_text)
        
        if label in ["CODE", "AMOUNT", "SENDER", "PROVIDER", "DATE", "ACCOUNT"]:
            entities.append([start_idx, end_idx, label])
            
        last_end = match.end()
        
    new_text += template_str[last_end:]
    return new_text, entities

def generate_synthetic_data(num_samples=10000):
    dataset = []
    
    templates = [
        # 1. Real: Standard M-Pesa Send to Paybill / Buy Goods
        "[CODE] Confirmed. [AMOUNT_STR] sent to [PROVIDER] for account [ACCOUNT] on [DATE_1] at [TIME] New M-PESA balance is Ksh12,345.00. Transaction cost, Ksh10.00.Amount you can transact within the day is 498,260.00. Save frequent paybills for quick payment on M-PESA app https://bit.ly/mpesalnk",
        
        # 2. Real: Merchant Till Receipt (Reverse perspective)
        "Confirmed. Payment of [AMOUNT_STR] to [SENDER] Till No. 0708613560 has been received. Ref. [CODE] on [DATE_1] at [TIME]. Thank you.",
        
        # 3. Real: Paid to Company (Short)
        "[AMOUNT_STR] paid to [SENDER] (Acc 539850) on [DATE_1] at [TIME] Ref: [CODE]. Enquiries, call 0719088000.",
        
        # 4. Real: SACCO Deposit / Bank Deposit
        "Dear Member, you have deposited [AMOUNT_STR] to A/C No. xxxxxx6291, of [PROVIDER] on [DATE_1] [TIME]. For help 0709253000",
        
        # 5. Direct Receipt
        "[CODE] Confirmed.You have received [AMOUNT_STR] from [SENDER] 0712345678 on [DATE_1] at [TIME].",
        "[CODE] Confirmed. You have received [AMOUNT_STR] from [SENDER] on [DATE_1] at [TIME].",
        
        # 6. Pochi La Biashara
        "[CODE] Confirmed. You have received [AMOUNT_STR] from [SENDER] on [DATE_1] at [TIME]. Separate personal and business funds through Pochi la Biashara on *334#.",
        
        # 7. WhatsApp / Forwarded
        "Fwd: [CODE] Confirmed. You have received [AMOUNT_STR] from [SENDER] on [DATE_1] at [TIME] via [PROVIDER].",
        "[[TIME], [DATE_1]] [SENDER]: [CODE] Confirmed. [AMOUNT_STR] received.",
        
        # 8. Reversals
        "Reversal of transaction [CODE] has been successfully done. [AMOUNT_STR] has been credited to your account from [SENDER] on [DATE_1].",
        
        # 9. Bank to Wallet
        "You have received [AMOUNT_STR] from [SENDER]. M-PESA Ref [CODE]. Transaction Ref No DDM8FQCSHA on [DATE_1] via [PROVIDER]."
    ]
    
    for _ in range(num_samples):
        # Dynamically vary amounts to match real-world fluctuations
        raw_amt = round(random.uniform(10.0, 150000.0), random.choice([0, 1, 2]))
        amount_num = f"{raw_amt:,.2f}" if random.choice([True, False]) else str(raw_amt)
        amount_str = random.choice([
            f"Ksh {amount_num}", f"Ksh{amount_num}", 
            f"KES {amount_num}", f"KES{amount_num}", 
            f"KES. {amount_num}", f"{amount_num}"
        ])
        
        # Dynamically vary dates to match real-world formatting
        d = random.randint(1, 28)
        m = random.randint(1, 12)
        y_short = random.choice(['24', '25', '26', '27'])
        y_long = f"20{y_short}"
        
        date_1 = random.choice([
            f"{d}/{m}/{y_short}", 
            f"{d:02d}/{m:02d}/{y_long}", 
            f"{d:02d}-{m:02d}-{y_long}",
            f"{y_long}/{m:02d}/{d:02d}"
        ])
        
        # Dynamically vary times
        h = random.randint(1, 12)
        min_str = f"{random.randint(0, 59):02d}"
        sec_str = f"{random.randint(0, 59):02d}"
        ampm = random.choice(['AM', 'PM', 'am', 'pm'])
        time_str = random.choice([
            f"{h}:{min_str} {ampm}", 
            f"{h}:{min_str}{ampm}", 
            f"{random.randint(0, 23):02d}:{min_str}",
            f"{random.randint(0, 23):02d}:{min_str}:{sec_str}"
        ])

        replacements = {
            "CODE": generate_mpesa_code(),
            "SENDER": random.choice(NAMES),
            "ACCOUNT": random.choice(NAMES),
            "PROVIDER": random.choice(PROVIDERS),
            "AMOUNT_STR": amount_str,
            "DATE_1": date_1,
            "TIME": time_str
        }
        
        template_str = random.choice(templates)
        text, entities = build_template(template_str, replacements)
        dataset.append({"text": text, "entities": entities})
        
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, indent=2)
        
    logger.info(f"Successfully generated {num_samples} perfectly-labelled synthetic samples at {OUTPUT_PATH}")

if __name__ == "__main__":
    generate_synthetic_data(10000)
