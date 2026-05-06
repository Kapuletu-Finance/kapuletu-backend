import pandas as pd

def generate_excel(data):
    df = pd.DataFrame(data)
    # logic to save to S3
    return "s3://bucket/report.xlsx"
