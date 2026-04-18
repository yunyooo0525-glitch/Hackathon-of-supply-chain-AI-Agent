import urllib.request
import urllib.parse
from html.parser import HTMLParser

class DDGParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_snippet = False
        self.snippets = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, value in attrs:
                if name == 'class' and 'result__snippet' in value:
                    self.in_snippet = True

    def handle_endtag(self, tag):
        if tag == 'a' and self.in_snippet:
            self.in_snippet = False

    def handle_data(self, data):
        if self.in_snippet:
            self.snippets.append(data.strip())

def scrape_ext_info(query):
    try:
        req = urllib.request.Request(
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        parser = DDGParser()
        parser.feed(html)
        return " ".join(parser.snippets[:5])
    except Exception as e:
        return str(e)

print(scrape_ext_info("target A-94285133 ingredients"))
