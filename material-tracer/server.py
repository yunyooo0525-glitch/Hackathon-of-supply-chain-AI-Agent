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
                    f"你是一个专业的供应链分析 AI 助手，并且已连入整个互联网。\n"
                    f"用户正在为原材料 `{material_sku}` 寻找合适的替代方案。\n\n"
                )
                
                if is_fg and website_name and product_code:
                    # 直接启动后台 Python 爬虫，暴力获取内容，避开 Google Grounding 的限制
                    scraped_info = scrape_ext_info(f"{website_name} {product_code} supplement details")
                    google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(website_name + ' ' + product_code + ' supplement details')}"
                    prompt += (
                        f"【产品功能逆向工程指令】:\n"
                        f"该原料正在被用于终端成品 `{parent_product_sku}` 中。\n"
                        f"该成品的 SKU 表明它来源于 `{website_name}`，ID 为 `{product_code}`。\n"
                        f"通过后台爬虫实时抓取该外网商品（参考检索来源：{google_url}）获得的核心介绍如下：\n"
                        f"『{scraped_info}』\n"
                        f"1. 请仔细阅读上述真实爬取的商品文本来明确这款产品的真身及其作用。\n"
                        f"2. 然后深度推断出原材料 `{material_sku}` 在该具体成品的配方工艺中扮演的具体角色（绝对不要笼统答复生理基础知识）。\n\n"
                    )
                elif generic_material_name:
                    prompt += (
                        f"【原材料特性检索指令】:\n"
                        f"该材料是一项直接查询的基础原料。从其 SKU 中提取出的核心成分标识为 `{generic_material_name}`。\n"
                        f"1. 请结合你的知识库，或者使用 Google Search 查阅 `{generic_material_name}` 的一般工业/医药用途。\n"
                        f"2. 深度思考该材质在制造领域的主要功能，并以此作为基准来挑选替代品。\n\n"
                    )

                prompt += (
                    f"【判断与输出规则】:\n"
                    f"1. 深刻理解原材料在产品**配方/工艺级别**的【核心功能】后，在数据库中寻找能够**完美替代这一功能**的原料。\n"
                    f"2. 替代品也最好出现在类似产品的 BOM（物料清单）中。\n"
                    f"3. 尽可能多地列出具体的替代原材料 SKU。对于每一个选出的 SKU，必须准确写出**为该 SKU 供货的供应商（Supplier）**，请从 `Supplier_Product` 表中寻找对应关系，**绝对不要**写出所属或购买该原料的公司（Company）。\n"
                    f"4. 强制执行：如果你依赖了我提供的外部搜索文本或者你调用了内置的 Google Grounding 进行判断，请**务必在引述该证据的整句末尾当场打上对应的 Markdown 行内锚点角标**（例如：对视力起保护作用`[1](https://具体的真实URL)`），不要集中堆砌到文末。\n\n"
                    f"【全局数据库 JSON（从中挑选替代品）】:\n"
                    f"{db_data_text}\n\n"
                    f"请基于上述背景调查和本地数据库，务必完整思考并输出。按照以下精简的 Markdown 格式输出（请使用中文，可以有多项）：\n\n"
                    f"### 🔍 溯源与处方工艺寻源解读\n"
                    f"[此处详细输出你对该成品配方的理解，并明确判定 {material_sku} 在产品配方中起到的物理/化学或有效成分作用。不要大段背诵生物学常识。]\n\n"
                    f"### 替代选项 1：[必须是一个具体的替代原料 SKU，不可写成分泛称]\n"
                    f"- **对接供应商 (Supplier)**: [列出数据库中能为该具体 SKU 供货的真实供应商名称]\n"
                    f"- **工艺级推荐理由**: [说明该替换料在理化性质和制剂工艺上为何能平替原物料]\n\n"
                    f"### 替代选项 2：[必须是一个具体的替代原料 SKU]\n"
                    f"...(以此类推，请列出尽可能多的具体 SKU)"
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
                
                # 成品溯源已经自带外网爬取脚本文本。只有针对独立的原材料查询，才开启内置的联网搜索辅助大模型
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
                        
                    # 针对大模型由于 Grounding 失败返回空文本的情况启动热回退策略
                    if not ai_text.strip():
                        # 去掉强制搜索工具，降级纯模型推理
                        payload.pop("tools", None)
                        fallback_prompt = prompt + "\n\n【紧急回退注意】：因为防火墙或参数异常，联网查明产品具体形态失败。请直接将该终端产品假想为一款“典型的含有该物料的胶囊/压片/健康补剂”，然后推理出该成分在这类假想产品配方里的制剂学或营养学用途（一定要具体到应用场景中），再去数据库中挑选能够满足该处方工艺的替代 SKU 及对应的源头供应商！"
                        payload["contents"][0]["parts"][0]["text"] = fallback_prompt
                        response_fallback = requests.post(url, headers=headers, json=payload)
                        if response_fallback.status_code == 200:
                            ai_res_fallback = response_fallback.json()
                            try:
                                ai_text = ai_res_fallback.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                            except Exception:
                                pass
                            if not ai_text.strip():
                                ai_text = "AI Response error: API 最终返回了空响应，这可能是由于平台针对此关键词的安全拦截策略。"
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
                        ai_text += f"\n\n### 📚 辅助决策搜寻与检索凭证\n{url_list}"

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
                
                # 将 alternatives_context 裁剪到最多 4000 字，防止 Token 超限导致裁断
                trimmed_context = alternatives_context[:4000] + ("…(内容已经过大裁剪)" if len(alternatives_context) > 4000 else "")
                
                compliance_prompt = (
                    f"【注意】：请直接输出报告内容，不要任何自我介经、开场白或重复用户的话。\n\n"
                    f"【任务】你是一名高级原料合规审查师。请对以下候选原料进行严格的二次法规与质量过滤。直接开始输出实质性报告尚表。\n\n"
                    f"【终端成品】`{parent_product_sku}`\n"
                    f"公网爬取到的产品介绍：『{product_intro}』\n\n"
                    f"【候选原料摘要】（前一步生成的候选名单）：\n{trimmed_context}\n\n"
                    f"【审查准则】：\n"
                    f"1. 所有原料必须满足 Food-Grade 食品级基础要求。\n"
                    f"2. 根据抓取的产品介绍，识别并强制执行 Organic/Vegan/Gluten-Free/Non-GMO 等特殊要求。\n"
                    f"3. 对不符合的候选一律淘汰，对幸存者说明代表供应商对应质量标准。\n"
                    f"4. 如果匹配多个，直接当成多项列出、不强求唯一。\n"
                    f"5. 全局硬性格式要求：在你断言一个合规事实（例如判定某种物质不属于纯素、或者符合无麸质标准时），一旦调用了谷歌搜索，必须精确地在其句末直接接上 Markdown 格式网址角标：如 `[1](https://来源网址)` 进行溯源。\n\n"
                    f"输出格式（Markdown）：\n"
                    f"### 📋 产品终端合规基准识别\n"
                    f"[1-3句总结强制质量要求。勿过多描述。]\n\n"
                    f"### 🚫 淘汰名单\n"
                    f"[列出被否决的 SKU + 一句话说明为什么淘汰]\n\n"
                    f"### 🏆 最终合规放行推荐\n"
                    f"[列出幸存的 SKU + 对接供应商 + 一句话合规理由]\n"
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
                        ai_text += f"\n\n### 📚 合规法务及标准查阅来源\n{url_list}"

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

                # ── 1. 找到目标公司 & 其所有 RM ──────────────────────────
                fg_product = next((p for p in db['Product'] if p['SKU'] == parent_product_sku), None)
                company_id = fg_product['CompanyId'] if fg_product else None
                company_name = next((c['Name'] for c in db['Company'] if c['Id'] == company_id), 'Unknown') if company_id else 'Unknown'

                company_rm_ids = set(
                    p['Id'] for p in db['Product']
                    if p.get('CompanyId') == company_id and p.get('Type') == 'raw-material'
                ) if company_id else set()
                total_rm = len(company_rm_ids)

                # ── 2. 找到原始原料 & 其供应商 ───────────────────────────
                orig_product = next((p for p in db['Product'] if p['SKU'] == material_sku), None)
                orig_prod_id = orig_product['Id'] if orig_product else None

                def get_suppliers_for_product(prod_id):
                    sup_ids = [sp['SupplierId'] for sp in db['Supplier_Product'] if sp['ProductId'] == prod_id]
                    return [s for s in db['Supplier'] if s['Id'] in sup_ids]

                orig_suppliers = get_suppliers_for_product(orig_prod_id) if orig_prod_id else []

                # ── 3. 计算每个供应商的合并分 ─────────────────────────────
                def consolidation_score(supplier_id):
                    sup_product_ids = set(sp['ProductId'] for sp in db['Supplier_Product'] if sp['SupplierId'] == supplier_id)
                    overlap = len(sup_product_ids & company_rm_ids)
                    rate = overlap / total_rm if total_rm else 0
                    return round(rate * 45, 1), overlap

                # ── 4. 仅提取合规放行区域(🏆后)的 SKU，过滤掉淘汰区的 SKU
                import re
                
                # 找到"最终合规放行推荐"或 🏆 所在行，只取其后的内容
                approved_section = ""
                lines_report = compliant_report.split('\n')
                in_approved = False
                for line in lines_report:
                    if '\U0001f3c6' in line or '放行' in line or '推荐' in line:
                        in_approved = True
                    if in_approved:
                        approved_section += line + '\n'
                
                # 如果没有找到任何放行区域，只保留原始原料
                if approved_section:
                    found_skus = re.findall(r'RM-[A-Za-z0-9_-]+', approved_section)
                else:
                    found_skus = []
                found_skus = list(dict.fromkeys(found_skus))  # 去重保序

                # 构建候选列表：含原始 SKU + 合规通过的替代品
                candidate_skus = [material_sku] + [s for s in found_skus if s != material_sku]
                candidate_skus = candidate_skus[:12]  # 最多 12 个候选，防止 token 爆炸

                # ── 5. 直接爬 PureBulk 产品搜索页抓真实价格 ──────────────
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
                            # 过滤掉明显是大包装的超高价格（>200），取最低零售单价作参考
                            price_vals = sorted(set(float(p.replace('$','').replace(',','')) for p in prices))
                            relevant = [p for p in price_vals if 1 < p < 500]
                            if relevant:
                                return f"PureBulk 参考价: ${relevant[0]:.2f}起（多规格，最低单价）"
                    except Exception:
                        pass
                    # 回退：Alibaba DuckDuckGo 片段
                    fallback = scrape_ext_info(f"{material_name} bulk price per kg USD 2024")
                    return fallback[:200] if fallback else "未找到公开价格"


                # ── 6. 构建结构化候选数据 ─────────────────────────────────
                candidate_rows = []
                for sku in candidate_skus:
                    prod = next((p for p in db['Product'] if p['SKU'] == sku), None)
                    if not prod:
                        continue
                    sups = get_suppliers_for_product(prod['Id'])
                    is_original = (sku == material_sku)
                    # 从 SKU 推断化学通用名
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
                            'price_info': price_info[:300] if price_info else '未找到公开价格'
                        })

                # 按 is_original 优先，再按合并分排序
                candidate_rows.sort(key=lambda x: (-int(x['is_original']), -x['consolidation_score']))
                candidate_rows = candidate_rows[:15]  # 最多 15 行

                # 构建结构化上下文
                rows_text = "\n".join([
                    f"{'[原始]' if r['is_original'] else '[替代]'} SKU={r['sku']} | 供应商={r['supplier']} | "
                    f"已为该公司供{r['overlap_count']}/{total_rm}种原料(合并分{r['consolidation_score']}/45) | "
                    f"价格情报: {r['price_info']}"
                    for r in candidate_rows
                ])

                scoring_prompt = (
                    f"【禁止自我介绍，直接输出报告】\n\n"
                    f"你是一位采购优化专家。请根据以下系统预计算的结构化数据，对候选原料进行最终打分排名。\n\n"
                    f"【背景】\n"
                    f"公司: {company_name} | 需求量: {quantity_kg} 千克/月\n"
                    f"原料: {material_sku} | 该公司共有 {total_rm} 种原材料\n\n"
                    f"【候选列表（含系统预算的合并分）】\n"
                    f"{rows_text}\n\n"
                    f"【打分规则】\n"
                    f"- 价格分(40分): 从价格情报中估算单价，最便宜=40，其余按比例，无法判断=20\n"
                    f"- 合并分(45分): 已由系统算好，直接使用\n"
                    f"- 规模适配分(15分): 根据 {quantity_kg}kg/月需求 + 供应商性质判断(工业级=15, 零售级=5, 未知=10)\n"
                    f"- 总分 = 三项之和\n\n"
                    f"【输出格式】\n"
                    f"### 🏆 最优寻源打分排名\n"
                    f"| 排名 | SKU | 供应商 | 估算单价 | 合并分 | 价格分 | 规模分 | **总分** |\n"
                    f"|------|-----|--------|----------|--------|--------|--------|----------|\n"
                    f"(填入所有候选行，按总分从高到低)\n\n"
                    f"### 🥇 最终推荐\n"
                    f"[1-2句：推荐哪个SKU+供应商，核心理由]\n\n"
                    f"### 📈 供应链整合机会\n"
                    f"[1-2句：如果选择该供应商，可以合并哪些其他原料的采购，整合潜力如何]\n\n"
                    f"---\n"
                    f"*TODO (未来整批次优化): /api/optimize-company-sourcing — 对 {company_name} 全部 {total_rm} 种原料一键输出最小供应商组合方案*"
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
                                g_set.append({'supplier': sr['supplier'] + ' (备选补齐)', 'covers': sorted(target_skus)})
                                temp_unc -= newly
                            if not temp_unc:
                                break
                    return g_set

                plan1 = {
                    'name': '方案一：极致精简组合（最低管理成本）',
                    'desc': '按照数学贪心算法优先选择覆盖面最广的供货商，大幅减少采购对接对象。',
                    'steps': compute_greedy()
                }
                
                final_plans = [plan1]
                
                if len(supplier_rankings) > 1:
                    top_supp = supplier_rankings[0]['supplier']
                    final_plans.append({
                        'name': f'方案二：韧性备选组合（规避重度依赖）',
                        'desc': f'剔除覆盖面最大的头号供应商 ({top_supp}) 强行去中心化的策略，防止单点断供卡脖子。',
                        'steps': compute_greedy(exclude_suppliers={top_supp})
                    })
                
                if len(supplier_rankings) > 2:
                    top2 = {supplier_rankings[0]['supplier'], supplier_rankings[1]['supplier']}
                    final_plans.append({
                        'name': '方案三：多源分散组合（多元化采买）',
                        'desc': '故意避开排名前两位的头部大厂，强制引入更多中小供应商，适用于测试二级备用供应链网络。',
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
                    'ai_analysis': "此矩阵所有替代项均已由各前端进程通过单物料深度分析与合规测试筛选而得。"
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


