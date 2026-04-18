import json, requests
with open('material-tracer/data.json') as f: db = json.load(f)
c = db['Company'][0]
data = {
    "company_id": c["Id"],
    "rm_compliant_map": {
        "RM-Nutrient-AscorbicAcid-1925": [
            {"sku": "RM-Nutrient-AscorbicAcid-1925", "supplier": "Cargill"}
        ],
        "RM-Excipient-StearicAcid-8392": [
            {"sku": "RM-Excipient-StearicAcid-8392", "supplier": "Unknown"}
        ]
    }
}
res = requests.post('http://localhost:8000/api/compute-consolidation', json=data)
print(res.status_code)
print(res.json())
