import google.auth
from google.oauth2 import service_account
import google.auth.transport.requests
import requests
import json

creds_path = "/Users/lzy/Documents/Hackathon/aiweb-492614-76467b775ab7.json"
credentials = service_account.Credentials.from_service_account_file(
    creds_path, scopes=["https://www.googleapis.com/auth/cloud-platform"])

auth_req = google.auth.transport.requests.Request()
credentials.refresh(auth_req)
token = credentials.token

project_id = "aiweb-492614"
location = "us-central1"
model = "gemini-2.5-flash"

url = f"https://{location}-aiplatform.googleapis.com/v1/projects/{project_id}/locations/{location}/publishers/google/models/{model}:generateContent"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
data = {
    "contents": [{"role": "user", "parts": [{"text": "Hello"}]}]
}
response = requests.post(url, headers=headers, json=data)
print(response.status_code)
print(response.json())
