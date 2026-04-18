import json

with open("data.json", "r") as f:
    dbData = json.load(f)

for k, v in dbData.items():
    print(f"{k}: {len(v)} records")
