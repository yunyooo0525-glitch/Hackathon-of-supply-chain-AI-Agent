import google.auth
from google.oauth2 import service_account
import google.auth.transport.requests
import requests
import json

CREDS_PATH = "/Users/lzy/Documents/Hackathon/aiweb-492614-76467b775ab7.json"
PROJECT_ID = "aiweb-492614"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash"

with open('material-tracer/data.json', 'r', encoding='utf-8') as f:
    db_data = json.load(f)
    if 'Product' in db_data:
        db_data['Product'] = [p for p in db_data['Product'] if p.get('Type') == 'raw-material']
    db_data_text = json.dumps(db_data, separators=(',', ':'), ensure_ascii=False)

material_sku = 'RM-C4-calcium-c77f1de7'
parent_product_sku = 'FG-amazon-b07z2x2xtc'
website_name = ""
product_code = ""
generic_material_name = ""

is_fg = parent_product_sku.startswith("FG-")
is_rm = parent_product_sku.startswith("RM-")

if is_fg:
    parts = parent_product_sku.split('-')
    if len(parts) >= 3:
        website_name = parts[1]
        product_code = "-".join(parts[2:])
elif is_rm:
    parts = material_sku.split('-')
    if len(parts) >= 3:
        generic_material_name = parts[2]

prompt = (
    f"你是一个专业的供应链分析 AI 助手，并且已连入整个互联网。\n"
    f"用户正在为原材料 `{material_sku}` 寻找合适的替代方案。\n\n"
)

if is_fg and website_name and product_code:
    prompt += (
        f"【产品功能逆向工程指令】:\n"
        f"该原料正在被用于终端成品 `{parent_product_sku}` 中。\n"
        f"该成品的 SKU 表明它来源于渠道 `{website_name}`，且在该网站上的产品 ID 为 `{product_code}`。\n"
        f"1. 首先，你必须使用 Google Search 工具搜索 `{website_name} {product_code}` 以获取该成品的实际销售网页、营养成分表和产品描述。\n"
        f"2. 然后，通过产品的整体功效，深度推断出原材料 `{material_sku}` 在该产品中扮演的核心功能。\n\n"
    )
elif generic_material_name:
    prompt += (
        f"【原材料特性检索指令】:\n"
        f"该材料是一项直接查询的基础原料。从其 SKU 中提取出的核心成分标识为 `{generic_material_name}`。\n"
        f"1. 请结合你的知识库，或者使用 Google Search 查阅 `{generic_material_name}` 的一般工业/医药用途。\n"
        f"2. 深度思考该材质在制造领域的主要功能，并以此作为基准来挑选替代品。\n\n"
    )

prompt += (
    f"【判断规则】:\n"
    f"1. 深刻理解原材料的【核心功能】后，在数据库中寻找能够**完美替代该功能的同源或同效原料**。\n"
    f"2. 替代品也最好出现在类似产品的 BOM（物料清单）中。\n"
    f"3. 尽可能多地列出有潜力的替代原材料，并且为每一个替代原材料列出**所有相关的供应商**，供用户后期进行全面的人工筛选。\n\n"
    f"【全局数据库 JSON（从中挑选替代品）】:\n"
    f"{db_data_text}\n\n"
    f"请基于上述背景调查和本地数据库，务必完整思考并输出。按照以下精简的 Markdown 格式输出（请使用中文，可以有多项）：\n\n"
    f"### 🔍 溯源与功能寻源解读\n"
    f"[此处详细输出你对该物料成分/成品的理解，并明确判定其核心功能。]\n\n"
    f"### 方案一：[替代原料 SKU]\n"
    f"- **所有供应商**: [列出数据库中该原料的所有供应商名称]\n"
    f"- **推荐理由**: [结合寻源分析得到的功能，简短说明为何认为该原料功能适配]\n\n"
    f"### 方案二：[替代原料 SKU]\n"
    f"...(以此类推)"
)

credentials = service_account.Credentials.from_service_account_file(
    CREDS_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"])
auth_req = google.auth.transport.requests.Request()
credentials.refresh(auth_req)

url = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/{MODEL}:generateContent"
headers = {
    "Authorization": f"Bearer {credentials.token}",
    "Content-Type": "application/json"
}
payload = {
    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    "tools": [{"googleSearch": {}}],
    "generationConfig": {"temperature": 0.2}
}

response = requests.post(url, headers=headers, json=payload)
res_json = response.json()
print("FULL RESPONSE:")
print(json.dumps(res_json, indent=2))
