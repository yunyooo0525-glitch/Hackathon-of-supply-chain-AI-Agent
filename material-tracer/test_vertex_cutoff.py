import google.auth
from google.oauth2 import service_account
import google.auth.transport.requests
import requests
import json

CREDS_PATH = "/Users/lzy/Documents/Hackathon/aiweb-492614-76467b775ab7.json"
PROJECT_ID = "aiweb-492614"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash"

with open('data.json', 'r', encoding='utf-8') as f:
    db_data_text = f.read()

material_sku = 'RM-C1-cellulose-594d4ce6'
prompt = (
    f"你是一个专业的供应链优化 AI 助手。\n"
    f"用户希望为以下原材料寻找替代方案: `{material_sku}`。\n\n"
    f"【判断与优选规则】:\n"
    f"1. 替代品在数据库中的名称/SKU 应与原物料高度相似或同源。\n"
    f"2. 替代品也经常出现在类似产品的 BOM（物料清单）中。\n"
    f"3. **核心目标（降低供应链复杂度）**: 同一家公司的所有原材料应尽可能来自更少的供应商。因此，你需要从替代品的可选供应商中，**明确挑选出唯一一个最佳供应商**，该供应商优选为“同一家公司目前已经在使用的、供货最频繁的供应商”。\n\n"
    f"【全局数据库 JSON】:\n"
    f"{db_data_text}\n\n"
    f"请基于上述全量数据，务必完整思考并输出，不要意外截断。按照以下精简的 Markdown 格式输出（请使用中文）：\n"
    f"- **推荐替代原料**: [SKU]\n"
    f"- **最佳推荐供应商**: [唯一选出的一家供应商名称]\n"
    f"- **推荐理由**: [简短说明为何选此原料，并重点解释为何选此特定供应商（例如：统合了供应链/该供应商还为该公司提供了哪些其他原料等）]\n"
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
    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048}
}

response = requests.post(url, headers=headers, json=payload)
res_json = response.json()
print("finishReason:", res_json['candidates'][0].get('finishReason'))
print("content:", res_json['candidates'][0]['content']['parts'][0]['text'])

