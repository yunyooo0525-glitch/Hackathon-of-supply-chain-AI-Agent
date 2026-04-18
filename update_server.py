import re

with open('material-tracer/server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# We want to replace everything from "elif self.path == '/api/company-consolidation':" to the end of that block.
# Which is basically until the "else:" block at the very end of do_POST.

pattern = re.compile(r"elif self\.path == '/api/company-consolidation':.*?        else:\n            self\.send_response\(404\)", re.DOTALL)

replacement = """elif self.path == '/api/company-rm-list':
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
                for rm_sku, compliant_alts in rm_compliant_map.items():
                    # alts is a list of objects like {'sku': '...', 'supplier': '...'}
                    for alt in compliant_alts:
                        sup = alt.get('supplier')
                        if sup:
                            supplier_coverage.setdefault(sup, set()).add(rm_sku)
                
                supplier_rankings = sorted(
                    [{'supplier': k, 'covers_count': len(v), 'covers': sorted(v)}
                     for k, v in supplier_coverage.items()],
                    key=lambda x: -x['covers_count']
                )

                temp_unc = set(rm_compliant_map.keys())
                greedy_set = []
                for sr in supplier_rankings:
                    newly = set(sr['covers']) & temp_unc
                    if newly:
                        greedy_set.append({'supplier': sr['supplier'], 'covers': sorted(newly)})
                        temp_unc -= newly
                    if not temp_unc:
                        break

                matrix = []
                for rm_sku, alts in rm_compliant_map.items():
                    matrix.append({
                        'rm_sku': rm_sku,
                        'chem_name': ' '.join(rm_sku.split('-')[2:-1]) if len(rm_sku.split('-')) >= 4 else rm_sku,
                        'used_in_fg': [], 
                        'current_suppliers': [],
                        'alternatives': [{'sku': a['sku'], 'chem_name': '', 'suppliers': [a.get('supplier')]} for a in alts]
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
                    'greedy_minimum_set': greedy_set,
                    'ai_analysis': "此矩阵所有替代项均已由各前端进程通过单物料深度分析与合规测试筛选而得。"
                }, ensure_ascii=False).encode('utf-8'))

            except Exception as e:
                import traceback
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e), "trace": traceback.format_exc()}).encode('utf-8'))

        else:
            self.send_response(404)"""

new_content, count = pattern.subn(replacement, content)
if count > 0:
    with open('material-tracer/server.py', 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("SUCCESS: server.py updated.")
else:
    print("ERROR: Regex did not match.")
