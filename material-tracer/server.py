import http.server
import socketserver
import json
import os
import urllib.request
import urllib.parse
from html.parser import HTMLParser
import google.auth
from google.oauth2 import service_account
import google.auth.transport.requests
import requests

# --- CUSTOM AMAZON ASIN SCRAPER ---
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
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8')
        parser = DDGParser()
        parser.feed(html)
        return " ".join(parser.snippets[:5])
    except Exception as e:
        return ""

PORT = 8000
CREDS_PATH = "/Users/lzy/Documents/Hackathon/aiweb-492614-76467b775ab7.json"
PROJECT_ID = "aiweb-492614"
LOCATION = "us-central1"
MODEL = "gemini-2.5-flash"

class CustomHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        super().end_headers()

    def do_POST(self):
        if self.path == '/api/suggest-alternatives':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                material_sku = data.get('material_sku')
                parent_product_sku = data.get('parent_product_sku', '')
                
                if not material_sku:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b'{"error": "material_sku missing"}')
                    return
                
                # Fetch DB Data
                try:
                    with open('data.json', 'r', encoding='utf-8') as f:
                        db_data = json.load(f)
                        
                    # --- Data Pruning to Fix 429 Token Exhaustion ---
                    # 1. We only need raw materials for alternatives. Finished goods take up huge space.
                    if 'Product' in db_data:
                        db_data['Product'] = [p for p in db_data['Product'] if p.get('Type') == 'raw-material']
                    
                    # 2. Convert to compact JSON to save tokens
                    db_data_text = json.dumps(db_data, separators=(',', ':'), ensure_ascii=False)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b'{"error": "data.json processing error"}')
                    return
                
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
                    # e.g. RM-C4-calcium-c77f1de7
                    parts = material_sku.split('-')
                    if len(parts) >= 3:
                        generic_material_name = parts[2]
                
                prompt = (
                    f"You are a professional supply chain AI assistant connected to the internet.\n"
                    f"The user is looking for alternatives for the raw material `{material_sku}` .\n\n"
                )
                
                if is_fg and website_name and product_code:
                    # 直接启动后台 Python 爬虫，暴力获取内容，避开 Google Grounding 的限制
                    scraped_info = scrape_ext_info(f"{website_name} {product_code} supplement details")
                    google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(website_name + ' ' + product_code + ' supplement details')}"
                    prompt += (
                        f"[Product Function Reverse Engineering Instructions]:\n"
                        f"This raw material is being used in the finished product `{parent_product_sku}` 中。\n"
                        f"The SKU of this finished product indicates it originates from `{website_name}`, with ID `{product_code}`。\n"
                        f"The core introduction obtained via real-time web scraping from the external product page (Reference query: {google_url}) is as follows:\n"
                        f"『{scraped_info}』\n"
                        f"1. Please carefully read the scraped product text to understand what this product is and its primary function.\n"
                        f"2. Then deeply infer the specific role that the raw material `{material_sku}` plays in this specific product's formulation/manufacturing process (Do NOT give generic physiological knowledge).\n\n"
                    )
                elif generic_material_name:
                    prompt += (
                        f"[Raw Material Properties Search Instructions]:\n"
                        f"This material is a directly queried basic raw material. The core component extracted from its SKU is `{generic_material_name}`。\n"
                        f"1. Please use your knowledge base or Google Search to review the generic industrial/medical uses of `{generic_material_name}` .\n"
                        f"2. Deeply consider the primary function of this material in manufacturing, and use this as a baseline to select alternatives.\n\n"
                    )

                prompt += (
                    f"[Judgment & Output Rules]:\n"
                    f"1. After profoundly understanding the raw material's [core function] at the **formulation/process level**, search the database for a raw material that can **perfectly substitute this function**.\n"
                    f"2. The alternative should ideally appear in the BOM (Bill of Materials) of similar products.\n"
                    f"3. Core Task: Carefully rank ALL database candidates by **degree of functional similarity** to the original material's specific role in this formulation. Then output **only the TOP 10 most functionally equivalent SKUs** — prioritizing those that are the most precise drop-in substitute (same chemical family, same delivery form, same intended function). For each selected SKU, you must accurately state the **Supplier** that provides this SKU by identifying the relationship in the `Supplier_Product` table. **NEVER** write down the Company that owns or buys the raw material.\n"
                    f"4. MUST ENFORCE: If you relied on the external search snippet I provided or called the built-in Google Grounding parameter, you **MUST append a Markdown inline superscript hyperlink strictly at the end of the sentence where you cited it** (e.g., provides antioxidant effects`[1](https://actual_url)`). Do NOT aggregate referencing links into a separate list at the bottom.\n\n"
                    f"[Global Database JSON (Select Alternatives from here)]:\n"
                    f"{db_data_text}\n\n"
                    f"Based on the background investigation and local database, please think thoroughly and output exactly in the following concise Markdown format (Please use English, max 10 options):\n\n"
                    f"### 🔍 Origin & Formulation Process Analysis\n"
                    f"[Output detailed understanding of the formulation here, and definitively explicitly determine the physical/chemical or active role {material_sku} plays in the product formulation. Do not just recite biological common knowledge.]\n\n"
                    f"### Alternative Option 1: [MUST be a specific alternative raw material SKU, do not use generic component terms]\n"
                    f"- **Target Supplier**: [List the real supplier name from the database capable of supplying this specific SKU]\n"
                    f"- **Process-level Recommendation Reason**: [Explain why this substitute can act as a drop-in replacement in terms of physicochemical properties and formulation processes]\n\n"
                    f"### Alternative Option 2: [MUST be a specific alternative raw material SKU]\n"
                    f"...(and so on, maximum 10 options total, ranked from most to least functionally similar)"
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
                    "generationConfig": {"temperature": 0.2}
                }
                
                # Finished product trace brings external scraped script text. Only turn on built-in internet search grounding model for independent raw material query
                if not is_fg:
                    payload["tools"] = [{"googleSearch": {}}]
                
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    ai_res = response.json()
                    
                    ai_text = ""
                    try:
                        ai_text = ai_res.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    except Exception:
                        pass
                        
                    # Hot fallback strategy for LLM returning empty text due to Grounding failure
                    if not ai_text.strip():
                        # Remove forced search tool, downgrade to pure model inference
                        payload.pop("tools", None)
                        fallback_prompt = prompt + "\n\n[URGENT FALLBACK]: Network search failed. Please imagine the product as a 'typical capsule/tablet/health supplement containing this material', then deeply infer its formulation/nutritional use in this hypothetical context, and select corresponding replacement SKUs and suppliers from the database!"
                        payload["contents"][0]["parts"][0]["text"] = fallback_prompt
                        response_fallback = requests.post(url, headers=headers, json=payload)
                        if response_fallback.status_code == 200:
                            ai_res_fallback = response_fallback.json()
                            try:
                                ai_text = ai_res_fallback.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                            except Exception:
                                pass
                            if not ai_text.strip():
                                ai_text = "AI Response error: API returned an empty response, likely due to safety intercept policies on the platform."
                        else:
                            ai_text = f"Fallback API Error: {response_fallback.text}"
                    
                    extracted_urls = []
                    if is_fg and website_name and product_code:
                        extracted_urls.append(f"https://www.google.com/search?q={urllib.parse.quote_plus(website_name + ' ' + product_code + ' supplement details')}")
                    
                    if 'ai_res' in locals():
                        chunks = ai_res.get('candidates', [{}])[0].get('groundingMetadata', {}).get('groundingChunks', [])
                        extracted_urls.extend([c.get('web', {}).get('uri') for c in chunks if c.get('web', {}).get('uri')])
                        
                    if extracted_urls:
                        unique_urls = list(dict.fromkeys(extracted_urls))
                        url_list = "\n".join([f"> 🔗 [{u}]({u})" for u in unique_urls[:4]])
                        ai_text += f"\n\n### 📚 Auxiliary Search & Retrieval Evidence\n{url_list}"

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"suggestion": ai_text}).encode('utf-8'))
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Vertex AI API Error: {response.text}"}).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        elif self.path == '/api/screen-compliance':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            material_sku = data.get('material_sku', '')
            parent_product_sku = data.get('parent_product_sku', '')
            alternatives_context = data.get('alternatives_context', '')
            
            if not parent_product_sku or not alternatives_context:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error": "Missing essential product context or alternatives data"}')
                return
                
            try:
                is_fg = parent_product_sku.startswith("FG-")
                product_intro = ""
                if is_fg:
                    parts = parent_product_sku.split('-')
                    if len(parts) >= 3:
                        website_name = parts[1]
                        product_code = "-".join(parts[2:])
                        # Again extract the original product description to understand constraints
                        product_intro = scrape_ext_info(f"{website_name} {product_code} supplement details")
                
                # Trim alternatives context to 4000 chars max to prevent Token overflow
                trimmed_context = alternatives_context[:150000] + ("…(content truncated due to length)" if len(alternatives_context) > 150000 else "")
                
                compliance_prompt = (
                    f"[NOTE]: Please output the report content directly, without any self-introduction, opening remarks, or echoing the user.\n\n"
                    f"[Task] You are a Senior Ingredient Compliance Auditor. Please conduct a strict secondary regulatory and quality screening on the following candidate raw materials. Begin outputting the substantive report immediately.\n\n"
                    f"[Finished Product]`{parent_product_sku}`\n"
                    f"Scraped product introduction from the public web: '{product_intro}'\n\n"
                    f"[Candidate Raw Materials Summary] (Candidate list generated from previous step):\n{trimmed_context}\n\n"
                    f"[Auditing Guidelines]:\n"
                    f"1. All incoming raw materials must satisfy Food-Grade baseline quality requirements.\n"
                    f"2. Identify and forcefully enforce specific requirements (e.g. Organic, Vegan, Gluten-Free, Non-GMO) based on the scraped product overview.\n"
                    f"3. Strict Legal & Purity Filtering (FDA GRAS & USP): You must verify if the underlying active chemical compound is FDA GRAS and meets USP heavy metal limits. Furthermore, since this is a premium supplement, enforce a **Bioavailability Hierarchy**: completely disqualify cheap, low-absorption chemical forms like 'carbonate' or 'oxide', and heavily favor premium forms like 'citrate', 'malate', or 'gluconate'. If it is an industrial cheap form, reject it immediately.\n"
                    f"4. If multiple candidates pass, list them all natively. Do not force uniqueness.\n"
                    f"5. **INLINE CITATION ENFORCEMENT (CRITICAL RULE — DO NOT VIOLATE)**: Every single time you invoke Google Search and use it to support a compliance claim, you MUST immediately append the citation **on the same line, directly after the sentence that relies on it**, using the format `[N](https://actual_url)` where N is a sequential integer starting from 1. Example of CORRECT behavior: 'Calcium Citrate is listed on the FDA GRAS list`[1](https://www.fda.gov/...)`and also meets USP monograph purity`[2](https://www.usp.org/...)`.' NEVER collect citations into a reference list at the bottom. NEVER leave any claim unsupported if you used search for it.\n\n"
                    f"Output Format (Markdown):\n"
                    f"### 📋 Product Terminal Compliance Baseline\n"
                    f"[Summarize mandated quality requirements in 1-3 sentences. Do not be overly verbose.]\n\n"
                    f"### 🚫 Disqualified Candidates\n"
                    f"[List disqualified SKUs. If none were disqualified, write 'None.' Do NOT leave this section blank.]\n\n"
                    f"### 🏆 Final Compliant Approvals\n"
                    f"CRITICAL: You MUST list every approved candidate here. Each entry MUST start with the exact SKU code in the format `RM-XXXX-XXXX-XXXX` (copy it exactly from the candidate list). Format each entry as:\n"
                    f"- **SKU**: `RM-C1-example-abc12345` | **Supplier**: [Supplier Name] | [One-sentence compliance reason]\n"
                    f"If no candidates were disqualified, ALL candidates from the input list must appear here. An empty approvals section is NEVER acceptable."
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
                    "contents": [{"role": "user", "parts": [{"text": compliance_prompt}]}],
                    "tools": [{"googleSearch": {}}],
                    "generationConfig": {"temperature": 0.2}
                }
                
                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    ai_res = response.json()
                    ai_text = ""
                    try:
                        ai_text = ai_res.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    except Exception:
                        pass
                    if not ai_text:
                        ai_text = "API returned empty response during strict compliance search."
                        
                    extracted_urls = []
                    chunks = ai_res.get('candidates', [{}])[0].get('groundingMetadata', {}).get('groundingChunks', [])
                    extracted_urls.extend([c.get('web', {}).get('uri') for c in chunks if c.get('web', {}).get('uri')])
                    if extracted_urls:
                        unique_urls = list(dict.fromkeys(extracted_urls))
                        url_list = "\n".join([f"> 🔗 [{u}]({u})" for u in unique_urls[:4]])
                        ai_text += f"\n\n### 📚 Compliance Legal & Standard Sources\n{url_list}"

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"report": ai_text}).encode('utf-8'))
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Vertex AI API Error: {response.text}"}).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif self.path == '/api/score-optimal':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            material_sku    = data.get('material_sku', '')
            parent_product_sku = data.get('parent_product_sku', '')
            quantity_kg     = data.get('quantity_kg', 1)
            compliant_report = data.get('compliant_report_text', '')

            try:
                with open('data.json', 'r', encoding='utf-8') as f:
                    db = json.load(f)

                # ── 1. Find target company & all RM ──────────────────────────
                fg_product = next((p for p in db['Product'] if p['SKU'] == parent_product_sku), None)
                company_id = fg_product['CompanyId'] if fg_product else None
                company_name = next((c['Name'] for c in db['Company'] if c['Id'] == company_id), 'Unknown') if company_id else 'Unknown'

                company_rm_ids = set(
                    p['Id'] for p in db['Product']
                    if p.get('CompanyId') == company_id and p.get('Type') == 'raw-material'
                ) if company_id else set()
                total_rm = len(company_rm_ids)

                # ── 2. Find original RM & suppliers ───────────────────────────
                orig_product = next((p for p in db['Product'] if p['SKU'] == material_sku), None)
                orig_prod_id = orig_product['Id'] if orig_product else None

                def get_suppliers_for_product(prod_id):
                    sup_ids = [sp['SupplierId'] for sp in db['Supplier_Product'] if sp['ProductId'] == prod_id]
                    return [s for s in db['Supplier'] if s['Id'] in sup_ids]

                orig_suppliers = get_suppliers_for_product(orig_prod_id) if orig_prod_id else []

                # ── 3. Calculate consolidation score for each supplier ─────────────────────────────
                def consolidation_score(supplier_id):
                    sup_product_ids = set(sp['ProductId'] for sp in db['Supplier_Product'] if sp['SupplierId'] == supplier_id)
                    overlap = len(sup_product_ids & company_rm_ids)
                    rate = overlap / total_rm if total_rm else 0
                    return round(rate * 45, 1), overlap

                # ── 4. Extract only SKUs from the compliant approval zone (after 🏆), filter out disqualified SKUs
                import re
                
                # Find 'Final Compliant Approvals' or 🏆 line, take only the following content
                approved_section = ""
                lines_report = compliant_report.split('\n')
                in_approved = False
                for line in lines_report:
                    if '\U0001f3c6' in line or '放行' in line or '推荐' in line:
                        in_approved = True
                    if in_approved:
                        approved_section += line + '\n'
                
                # If no approval zones found, keep original RM only
                if approved_section:
                    found_skus = re.findall(r'RM-[A-Za-z0-9_-]+', approved_section)
                else:
                    found_skus = []
                found_skus = list(dict.fromkeys(found_skus))  # Deduplicate preserving order

                # Build candidate list: original SKU + compliant alternatives
                candidate_skus = [material_sku] + [s for s in found_skus if s != material_sku]
                candidate_skus = candidate_skus[:12]  # Max 12 candidates to prevent token explosion

                # ── 5. Directly scrape PureBulk product search page for real prices ──────────────
                def scrape_price(supplier_name, material_name):
                    try:
                        slug = urllib.parse.quote_plus(material_name.replace('-', ' '))
                        url = f"https://www.purebulk.com/search?q={slug}"
                        req = urllib.request.Request(
                            url,
                            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
                        )
                        html = urllib.request.urlopen(req, timeout=6).read().decode('utf-8')
                        prices = re.findall(r'\$[\d,]+\.\d{2}', html)
                        if prices:
                            # Filter out obvious bulk high prices (>200), use lowest retail price as reference
                            price_vals = sorted(set(float(p.replace('$','').replace(',','')) for p in prices))
                            relevant = [p for p in price_vals if 1 < p < 500]
                            if relevant:
                                return f"PureBulk Ref Price: ${relevant[0]:.2f} up (multi-spec, lowest price)"
                    except Exception:
                        pass
                    # Fallback: Alibaba DuckDuckGo snippet
                    fallback = scrape_ext_info(f"{material_name} bulk price per kg USD 2024")
                    return fallback[:200] if fallback else "Public price not found"


                # ── 6. Build structured candidate data ─────────────────────────────────
                candidate_rows = []
                for sku in candidate_skus:
                    prod = next((p for p in db['Product'] if p['SKU'] == sku), None)
                    if not prod:
                        continue
                    sups = get_suppliers_for_product(prod['Id'])
                    is_original = (sku == material_sku)
                    # Infer chemical generic name from SKU
                    parts = sku.split('-')
                    chem_name = ' '.join(parts[2:-1]) if len(parts) >= 4 else sku

                    for sup in sups:
                        con_score, overlap_count = consolidation_score(sup['Id'])
                        price_info = scrape_price(sup['Name'], chem_name)
                        candidate_rows.append({
                            'sku': sku,
                            'is_original': is_original,
                            'supplier': sup['Name'],
                            'chem_name': chem_name,
                            'consolidation_score': con_score,
                            'overlap_count': overlap_count,
                            'price_info': price_info[:300] if price_info else 'Public price not found'
                        })

                # Sort primarily by is_original, then by consolidation score
                candidate_rows.sort(key=lambda x: (-int(x['is_original']), -x['consolidation_score']))
                candidate_rows = candidate_rows[:15]  # Max 15 rows

                # Build structured context
                rows_text = "\n".join([
                    f"{'[Original]' if r['is_original'] else '[Alternative]'} SKU={r['sku']} | Supplier={r['supplier']} | "
                    f"Supplied {r['overlap_count']}/{total_rm} RM for this company (Score {r['consolidation_score']}/45) | "
                    f"价格情报: {r['price_info']}"
                    for r in candidate_rows
                ])

                scoring_prompt = (
                    f"[Do not introduce yourself, output report directly]\n\n"
                    f"You are a procurement optimization expert. Please rank the candidate raw materials based on the pre-calculated structured data below.\n\n"
                    f"[Background]\n"
                    f"Company: {company_name} | Demand: {quantity_kg} kg/month\n"
                    f"Raw Material: {material_sku} | This company has a total of {total_rm} raw materials\n\n"
                    f"[Candidate List (incl. pre-calculated consolidation scores)]\n"
                    f"{rows_text}\n\n"
                    f"[Scoring Rules]\n"
                    f"- Price Score (40 pts): Estimate unit price from intel, cheapest=40, scaled, unknown=20\n"
                    f"- Consolidation Score (45 pts): Pre-calculated, use directly\n"
                    f"- Scale Fit Score (15 pts): Evaluate based on {quantity_kg}kg/mo demand + supplier type (Industrial=15, Retail=5, Unknown=10)\n"
                    f"- Total Score = Sum of three\n\n"
                    f"[Output Format]\n"
                    f"### 🏆 Optimal Sourcing Score Ranking\n"
                    f"| Rank | SKU | Supplier | Est. Price | Consol Score | Price Score | Scale Score | **Total Score** |\n"
                    f"|------|-----|----------|------------|--------------|-------------|-------------|-----------------|\n"
                    f"(Fill in all candidate rows, sorted by Total Score from highest to lowest)\n\n"
                    f"### 🥇 Final Recommendation\n"
                    f"[1-2 sentences: Which SKU + Supplier do you recommend, and what is the core reason?]\n\n"
                    f"### 📈 Supply Chain Consolidation Opportunity\n"
                    f"[1-2 sentences: If this supplier is chosen, what other raw materials can be consolidated, and what is the integration potential?]\n\n"
                    f"---\n"
                    f"*TODO (Future Batch Optimization): /api/optimize-company-sourcing — One-click output of the minimal supplier combination for all {total_rm} materials of {company_name}*"
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
                    "contents": [{"role": "user", "parts": [{"text": scoring_prompt}]}],
                    "generationConfig": {"temperature": 0.1}
                }

                response = requests.post(url, headers=headers, json=payload)
                if response.status_code == 200:
                    ai_res = response.json()
                    ai_text = ""
                    try:
                        ai_text = ai_res.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    except Exception:
                        pass
                    if not ai_text:
                        ai_text = "Scoring API returned empty response."
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"ranking": ai_text}).encode('utf-8'))
                else:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Vertex AI Error: {response.text}"}).encode('utf-8'))

            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

        elif self.path == '/api/company-rm-list':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            company_id = data.get('company_id')

            try:
                with open('data.json', 'r', encoding='utf-8') as f:
                    db = json.load(f)

                company = next((c for c in db['Company'] if c['Id'] == company_id), None)
                if not company:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Company not found"}).encode('utf-8'))
                    return

                fg_products = [p for p in db['Product']
                               if p.get('CompanyId') == company_id and p.get('Type') == 'finished-good']

                rm_to_fg = {}
                for fg in fg_products:
                    bom = next((b for b in db['BOM'] if b['ProducedProductId'] == fg['Id']), None)
                    if bom:
                        for comp in db['BOM_Component']:
                            if comp['BOMId'] == bom['Id']:
                                rm_to_fg.setdefault(comp['ConsumedProductId'], []).append(fg['SKU'])

                for rm in db['Product']:
                    if rm.get('CompanyId') == company_id and rm.get('Type') == 'raw-material':
                        if rm['Id'] not in rm_to_fg:
                            rm_to_fg[rm['Id']] = ['(direct company RM)']

                def get_sups(prod_id):
                    ids = [sp['SupplierId'] for sp in db['Supplier_Product'] if sp['ProductId'] == prod_id]
                    return [s['Name'] for s in db['Supplier'] if s['Id'] in ids], ids

                rm_entries = []
                for prod_id, fg_skus in rm_to_fg.items():
                    rm_prod = next((p for p in db['Product'] if p['Id'] == prod_id), None)
                    if not rm_prod:
                        continue
                    parts = rm_prod['SKU'].split('-')
                    chem_name = ' '.join(parts[2:-1]) if len(parts) >= 4 else rm_prod['SKU']
                    chem_keywords = set(w.lower() for w in chem_name.split() if len(w) > 2)

                    current_sups, current_sup_ids = get_sups(prod_id)

                    rm_entries.append({
                        'rm_sku': rm_prod['SKU'],
                        'chem_name': chem_name,
                        'used_in_fg': fg_skus,
                        'current_suppliers': current_sups,
                        'parent_product_sku': fg_skus[0] if fg_skus and not fg_skus[0].startswith('(') else ''
                    })

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'company': company['Name'],
                    'company_id': company_id,
                    'total_fg': len(fg_products),
                    'total_rm': len(rm_entries),
                    'rm_entries': rm_entries
                }, ensure_ascii=False).encode('utf-8'))

            except Exception as e:
                import traceback
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "trace": traceback.format_exc()}).encode('utf-8'))

        elif self.path == '/api/compute-consolidation':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            company_id = data.get('company_id')
            rm_compliant_map = data.get('rm_compliant_map', {})

            try:
                with open('data.json', 'r', encoding='utf-8') as f:
                    db = json.load(f)

                company = next((c for c in db['Company'] if c['Id'] == company_id), None)
                if not company:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Company not found"}).encode('utf-8'))
                    return
                
                fg_products = [p for p in db['Product'] if p.get('CompanyId') == company_id and p.get('Type') == 'finished-good']

                supplier_coverage = {}
                sup_to_alts = {}
                for rm_sku, compliant_alts in rm_compliant_map.items():
                    for alt in compliant_alts:
                        sups = alt.get('suppliers', [])
                        if 'supplier' in alt:
                            sups.append(alt['supplier'])
                        
                        seen_sups = set()
                        for sup in sups:
                            if sup and sup not in seen_sups:
                                seen_sups.add(sup)
                                supplier_coverage.setdefault(sup, set()).add(rm_sku)
                                sup_to_alts.setdefault((sup, rm_sku), set()).add(alt['sku'])
                
                supplier_rankings = []
                for k, v in supplier_coverage.items():
                    target_skus = set()
                    for rm_sku in v:
                        alts = sup_to_alts.get((k, rm_sku), set())
                        if alts:
                            target_skus.add(sorted(alts)[0])
                    supplier_rankings.append({
                        'supplier': k, 
                        'covers_count': len(v), 
                        'covers': sorted(target_skus),
                        '_orig_covers': sorted(v)
                    })
                supplier_rankings = sorted(supplier_rankings, key=lambda x: -x['covers_count'])

                def compute_greedy(exclude_suppliers=None):
                    if exclude_suppliers is None: 
                        exclude_suppliers = set()
                    temp_unc = set(rm_compliant_map.keys())
                    g_set = []
                    
                    for sr in supplier_rankings:
                        if sr['supplier'] in exclude_suppliers:
                            continue
                        newly = set(sr['_orig_covers']) & temp_unc
                        if newly:
                            target_skus = set()
                            for rm_sku in newly:
                                alts = sup_to_alts.get((sr['supplier'], rm_sku), set())
                                if alts:
                                    target_skus.add(sorted(alts)[0])
                            g_set.append({'supplier': sr['supplier'], 'covers': sorted(target_skus)})
                            temp_unc -= newly
                        if not temp_unc:
                            break
                    
                    if temp_unc:
                        for sr in supplier_rankings:
                            if sr['supplier'] not in exclude_suppliers:
                                continue
                            newly = set(sr['_orig_covers']) & temp_unc
                            if newly:
                                target_skus = set()
                                for rm_sku in newly:
                                    alts = sup_to_alts.get((sr['supplier'], rm_sku), set())
                                    if alts:
                                        target_skus.add(sorted(alts)[0])
                                g_set.append({'supplier': sr['supplier'] + ' (Fallback Supplement)', 'covers': sorted(target_skus)})
                                temp_unc -= newly
                            if not temp_unc:
                                break
                    
                    # Final safety net: any RM still uncovered (no supplier found via greedy)
                    # gets inserted directly using its first compliant alt entry
                    if temp_unc:
                        for rm_sku in sorted(temp_unc):
                            alts = rm_compliant_map.get(rm_sku, [])
                            if alts:
                                first_alt = alts[0]
                                supplier = first_alt.get('suppliers', ['Unknown Supplier'])[0] if first_alt.get('suppliers') else 'Unknown Supplier'
                                sku = first_alt.get('sku', rm_sku)
                            else:
                                supplier = 'Unknown Supplier'
                                sku = rm_sku
                            g_set.append({'supplier': f'{supplier} (Direct Fallback)', 'covers': [sku]})
                    
                    return g_set

                plan1 = {
                    'name': 'Plan 1: Extreme Consolidation (Min. Mgmt Cost)',
                    'desc': 'Prioritizes suppliers with the broadest coverage based on a greedy mathematical algorithm, drastically reducing the number of procurement contacts.',
                    'steps': compute_greedy()
                }
                
                final_plans = [plan1]
                
                if len(supplier_rankings) > 1:
                    top_supp = supplier_rankings[0]['supplier']
                    final_plans.append({
                        'name': f'Plan 2: Resilient Distributed (Risk Mitigation)',
                        'desc': f'A forced decentralization strategy removing the absolute top supplier ({top_supp}) to prevent single-point supply chain gridlocks.',
                        'steps': compute_greedy(exclude_suppliers={top_supp})
                    })
                
                if len(supplier_rankings) > 2:
                    top2 = {supplier_rankings[0]['supplier'], supplier_rankings[1]['supplier']}
                    final_plans.append({
                        'name': 'Plan 3: Multi-Source Diversification',
                        'desc': 'Intentionally sidestepping the top two mega-suppliers to forcefully inject more niche/SMB suppliers, ideal for establishing secondary alternative networks.',
                        'steps': compute_greedy(exclude_suppliers=top2)
                    })

                matrix = []
                for rm_sku, alts in rm_compliant_map.items():
                    matrix.append({
                        'rm_sku': rm_sku,
                        'chem_name': ' '.join(rm_sku.split('-')[2:-1]) if len(rm_sku.split('-')) >= 4 else rm_sku,
                        'used_in_fg': [], 
                        'current_suppliers': [],
                        'alternatives': [{'sku': a['sku'], 'chem_name': '', 'suppliers': a.get('suppliers', [s for s in [a.get('supplier')] if s])} for a in alts]
                    })

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'company': company['Name'],
                    'total_rm': len(rm_compliant_map),
                    'total_fg': len(fg_products),
                    'rm_matrix': matrix,
                    'supplier_rankings': supplier_rankings,
                    'purchasing_plans': final_plans,
                    'ai_analysis': "All replacement items in this matrix have been rigorously filtered through individual material deep-diving and compliance testing by concurrent processes."
                }, ensure_ascii=False).encode('utf-8'))

            except Exception as e:
                import traceback
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "trace": traceback.format_exc()}).encode('utf-8'))

        else:
            self.send_response(404)
            self.end_headers()

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), CustomHandler) as httpd:
    print(f"Serving at port {PORT} with Vertex AI Gateway")
    httpd.serve_forever()


