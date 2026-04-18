import urllib.request

url = "https://www.iherb.com/pr/a/10421"
req = urllib.request.Request(
    url, 
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)
try:
    with urllib.request.urlopen(req) as response:
        print("Status", response.status)
        content = response.read().decode('utf-8')
        print("Success, length", len(content))
except Exception as e:
    print("Error:", e)
