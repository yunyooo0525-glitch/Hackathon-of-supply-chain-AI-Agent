import urllib.request
import urllib.parse

def get_ddg_text(query):
    req = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}",
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
    )
    html = urllib.request.urlopen(req).read().decode('utf-8')
    return html

try:
    res = get_ddg_text("amazon B07Z2X2XTC ingredients")
    if "AlkemyPower" in res:
        print("Success")
    else:
        print("Failed to find keyword")
except Exception as e:
    print(e)
