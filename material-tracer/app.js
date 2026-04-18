document.addEventListener('DOMContentLoaded', async () => {
    const companySelect = document.getElementById('companySelect');
    const productSelect = document.getElementById('productSelect');
    const productGroup = document.getElementById('productGroup');
    const resultsArea = document.getElementById('resultsArea');
    const resultsContent = document.getElementById('resultsContent');
    const emptyState = document.getElementById('emptyState');

    let dbData = null;

    // Load DB Data
    try {
        const response = await fetch('./data.json');
        dbData = await response.json();
        
        // Populate Companies
        companySelect.innerHTML = '<option value="" disabled selected>Choose a company...</option>';
        if (dbData.Company && dbData.Company.length > 0) {
            // Sort companies alphabetically
            const companies = [...dbData.Company].sort((a, b) => a.Name.localeCompare(b.Name));
            companies.forEach(company => {
                const option = document.createElement('option');
                option.value = company.Id;
                option.textContent = company.Name;
                companySelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading data:', error);
        companySelect.innerHTML = '<option value="" disabled selected>Error loading data.json</option>';
    }

    // Company selection event
    companySelect.addEventListener('change', (e) => {
        const companyId = parseInt(e.target.value);
        
        // Filter products for this company
        const companyProducts = (dbData.Product || []).filter(p => p.CompanyId === companyId);
        
        productSelect.innerHTML = '<option value="" disabled selected>Choose a product (' + companyProducts.length + ' found)...</option>';
        
        if (companyProducts.length > 0) {
            // Sort products by SKU
            const sortedProducts = [...companyProducts].sort((a, b) => a.SKU.localeCompare(b.SKU));
            sortedProducts.forEach(product => {
                const option = document.createElement('option');
                option.value = product.Id;
                option.textContent = product.SKU + (product.Type === 'raw-material' ? ' (Raw)' : '');
                productSelect.appendChild(option);
            });
            productSelect.disabled = false;
            productGroup.classList.remove('disabled');
        } else {
            productSelect.disabled = true;
            productGroup.classList.add('disabled');
            productSelect.innerHTML = '<option value="" disabled selected>No products found</option>';
        }
        
        // Reset results area
        resultsArea.classList.add('hidden');
        emptyState.classList.remove('hidden');

        // Inject company-level consolidation button
        let consolidationPanel = document.getElementById('consolidation-panel');
        if (!consolidationPanel) {
            consolidationPanel = document.createElement('div');
            consolidationPanel.id = 'consolidation-panel';
            consolidationPanel.style.marginTop = '1.5rem';
            resultsArea.parentNode.insertBefore(consolidationPanel, resultsArea);
        }

        const companyName = companySelect.options[companySelect.selectedIndex].text;
        consolidationPanel.innerHTML = `
            <button class="consolidation-btn" id="company-consolidate-btn">
                🔗 全公司原材料 × 供应商整合分析（${companyName}）
            </button>
            <div id="consolidation-result" class="hidden"></div>
        `;

        document.getElementById('company-consolidate-btn').addEventListener('click', async () => {
            const btn = document.getElementById('company-consolidate-btn');
            const resultDiv = document.getElementById('consolidation-result');
            btn.disabled = true;
            btn.textContent = '⏳ 首先读取图谱并行分析中...';
            resultDiv.classList.remove('hidden');
            resultDiv.innerHTML = '<div class="ai-loader"><i class="uil uil-spinner-alt ai-spin"></i> 正在读取全公司成分矩阵...</div>';

            try {
                // Phase 1: Get all RMs
                const listRes = await fetch('/api/company-rm-list', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ company_id: companyId })
                });
                const listJson = await listRes.json();
                if (!listRes.ok) { throw new Error(listJson.error); }
                
                const rmEntries = listJson.rm_entries;
                if (!rmEntries || rmEntries.length === 0) {
                    resultDiv.innerHTML = '<span>无需分析，未查到原材料数据。</span>';
                    return;
                }

                // Render Progress UI
                let progressHtml = `<div style="margin-bottom:1.5rem">
                    <h3 style="color:#a78bfa;margin-bottom:0.75rem">🚀 分布式 AI 分析管道启航 (共 ${rmEntries.length} 项)</h3>
                    <div style="font-size:0.85rem;color:#8b8d96;margin-bottom:1rem">为避免幻觉并确保 100% 合规，系统正逐一深度探究每种原材料！</div>
                    <div id="progress-list" style="max-height: 250px; overflow-y: auto; background: rgba(0,0,0,0.2); padding: 1rem; border-radius: 8px;">`;
                
                rmEntries.forEach((rm, i) => {
                    progressHtml += `<div id="status-rm-${i}" style="margin-bottom:0.4rem;font-size:0.85rem;">
                        <span class="status-badge" style="background:#555;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">排队中</span> 
                        <code style="color:#a5f3fc">${rm.rm_sku}</code> 
                        (${rm.chem_name})
                    </div>`;
                });
                progressHtml += `</div></div><div id="final-consolidation-area"></div>`;
                resultDiv.innerHTML = progressHtml;

                const compliantMap = {}; // { rmSku: [{sku, supplier}] }
                const detailedReports = []; // 存储每个材料的 AI 分析报告

                // Map Phase: Concurrency Pool
                const CONCURRENCY = 4;
                let currentIndex = 0;

                const processRM = async (rm, i) => {
                    const statusEl = document.getElementById(`status-rm-${i}`);
                    let rmReport = { sku: rm.rm_sku, name: rm.chem_name, suggestion: '', report: '' };
                    
                    try {
                        // 1. Suggest Alternatives
                        statusEl.innerHTML = `<span class="status-badge" style="background:#3b82f6;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">搜寻功能..</span> <code style="color:#a5f3fc">${rm.rm_sku}</code>`;
                        const sugRes = await fetch('/api/suggest-alternatives', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ material_sku: rm.rm_sku, parent_product_sku: rm.parent_product_sku })
                        });
                        const sugJson = await sugRes.json();
                        if(!sugRes.ok) throw new Error("Suggest fail");

                        // 2. Screen Compliance
                        statusEl.innerHTML = `<span class="status-badge" style="background:#f59e0b;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">深度审查..</span> <code style="color:#a5f3fc">${rm.rm_sku}</code>`;
                        const compRes = await fetch('/api/screen-compliance', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ material_sku: rm.rm_sku, parent_product_sku: rm.parent_product_sku, alternatives_context: sugJson.suggestion })
                        });
                        const compJson = await compRes.json();
                        if(!compRes.ok) throw new Error("Compliance fail");
                        
                        // Parse Report for survivors
                        const reportText = compJson.report || "";
                        rmReport.suggestion = sugJson.suggestion || "";
                        rmReport.report = reportText;
                        
                        const approvedSectionMatches = [...reportText.matchAll(/(?:最终合规放行推荐|🏆)[\s\S]*?(?=###|$)/g)];
                        const alts = [];
                        if (approvedSectionMatches.length > 0) {
                            const lines = approvedSectionMatches[0][0].split('\n');
                            for (let line of lines) {
                                const skuMatch = line.match(/(RM-[A-Za-z0-9_-]+)/);
                                if (skuMatch) {
                                    let matchedSku = skuMatch[1];
                                    let suppNames = rm.current_suppliers.length > 0 ? rm.current_suppliers : ['默认原供应商'];
                                    let validInDb = true;

                                    if (dbData && dbData.Product) {
                                        const prod = dbData.Product.find(p => p.SKU.toLowerCase() === matchedSku.toLowerCase());
                                        if (prod) {
                                            matchedSku = prod.SKU;
                                            if (dbData.Supplier_Product && dbData.Supplier) {
                                                const sps = dbData.Supplier_Product.filter(x => x.ProductId === prod.Id);
                                                if (sps.length > 0) {
                                                    suppNames = sps.map(sp => {
                                                        const s = dbData.Supplier.find(x => x.Id === sp.SupplierId);
                                                        return s ? s.Name : null;
                                                    }).filter(Boolean);
                                                }
                                            }
                                        } else {
                                            validInDb = false; // hallucinated SKU
                                        }
                                    }
                                    if (validInDb) {
                                        alts.push({ sku: matchedSku, suppliers: suppNames });
                                    }
                                }
                            }
                        }
                        
                        compliantMap[rm.rm_sku] = alts.length > 0 ? alts : [{sku: rm.rm_sku, suppliers: rm.current_suppliers.length > 0 ? rm.current_suppliers : ['默认原供应商']}];
                        detailedReports.push(rmReport);
                        
                        statusEl.innerHTML = `<span class="status-badge" style="background:#10b981;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">✅ 完成验证</span> <code style="color:#a5f3fc">${rm.rm_sku}</code> <span style="color:#8b8d96;margin-left:0.5rem">符合要求: ${compliantMap[rm.rm_sku].length} 项</span>`;

                    } catch (e) {
                        statusEl.innerHTML = `<span class="status-badge" style="background:#ef4444;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">❌ 截断失败(可重试)</span> <code style="color:#a5f3fc">${rm.rm_sku}</code>`;
                        compliantMap[rm.rm_sku] = [{sku: rm.rm_sku, suppliers: rm.current_suppliers.length > 0 ? rm.current_suppliers : ['默认原供应商']}]; // fallback
                        rmReport.report += `\n\n**Error:** ${e.message}`;
                        detailedReports.push(rmReport);
                    }
                };

                const worker = async () => {
                    while (currentIndex < rmEntries.length) {
                        const index = currentIndex;
                        currentIndex++;
                        await processRM(rmEntries[index], index);
                    }
                };

                const workers = [];
                for (let i = 0; i < Math.min(CONCURRENCY, rmEntries.length); i++) {
                    workers.push(worker());
                }
                await Promise.all(workers);

                // Reduce Phase
                const finalArea = document.getElementById('final-consolidation-area');
                finalArea.innerHTML = '<div class="ai-loader" style="margin-top:2rem;"><i class="uil uil-spinner-alt ai-spin"></i> 正在合并全公司矩阵...</div>';
                
                const res = await fetch('/api/compute-consolidation', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ company_id: companyId, rm_compliant_map: compliantMap })
                });
                const json = await res.json();
                if (!res.ok) throw new Error(json.error);

                // ── Render ────────────
                const rmRows = json.rm_matrix.map(rm => {
                    const altHtml = rm.alternatives.length > 0
                        ? rm.alternatives.map(a => `<div style="margin-bottom:0.2rem;"><code style="font-size:0.75rem">${a.sku}</code> <span style="font-size:0.75rem;color:#8b8d96;">(供货: ${a.suppliers.join(', ')})</span></div>`).join('')
                        : '-';
                    return `<tr>
                        <td><code style="font-size:0.78rem;color:#a5f3fc">${rm.rm_sku}</code></td>
                        <td><strong>${rm.chem_name}</strong></td>
                        <td>${altHtml}</td>
                    </tr>`;
                }).join('');

                const rankRows = json.supplier_rankings.slice(0, 15).map((s, i) => `
                    <tr>
                        <td><strong>#${i+1}</strong></td>
                        <td>${s.supplier}</td>
                        <td><strong>${s.covers_count}</strong> / ${json.total_rm}</td>
                        <td style="font-size:0.78rem;color:#8b8d96">${s.covers.map(sku => `<code>${sku}</code>`).join(' ')}</td>
                    </tr>
                `).join('');

                let plansHtml = '';
                if (json.purchasing_plans && json.purchasing_plans.length > 0) {
                    json.purchasing_plans.forEach((plan, pIdx) => {
                        let stepsHtml = plan.steps.map((g, i) => `
                            <div class="greedy-step">
                                <span class="greedy-num">${i+1}</span>
                                <strong>${g.supplier}</strong>
                                <span style="color:#8b8d96;font-size:0.85rem">→ 排他覆盖 ${g.covers.length} 种：
                                    ${g.covers.map(sku => `<code>${sku}</code>`).join('、')}
                                </span>
                            </div>
                        `).join('');
                        
                        plansHtml += `
                            <div style="background: rgba(255,255,255,0.05); padding: 1.5rem; border-radius: 8px; margin-bottom: 1.5rem; border: 1px solid rgba(255,255,255,0.1);">
                                <h4 style="color:#38bdf8; margin-top:0; margin-bottom: 0.5rem; font-size:1.1rem;">${plan.name}</h4>
                                <p style="color:#a5b4fc; font-size:0.85rem; margin-bottom:1rem;">${plan.desc}</p>
                                <div class="greedy-steps">${stepsHtml}</div>
                            </div>
                        `;
                    });
                }

                finalArea.innerHTML = `
                    <div class="consolidation-card" style="margin-top:1rem;border-top:1px solid rgba(255,255,255,0.1);padding-top:2rem;">
                        <h2 style="color:#fbbf24;margin-bottom:1.5rem">
                            🏭 ${json.company} — 全链条深度合并报告
                        </h2>

                        <h3 style="color:#10b981;margin-bottom:0.75rem">🏆 全严格合规级可购池</h3>
                        <div style="overflow-x:auto;margin-bottom:2rem">
                            <table class="matrix-table">
                                <thead><tr><th>原物料核心需求 (SKU)</th><th>基础材料体系</th><th>完全合格的可平替采购项</th></tr></thead>
                                <tbody>${rmRows}</tbody>
                            </table>
                        </div>

                        <h3 style="color:#38bdf8;margin-bottom:0.75rem">🎯 智能采买方案（多维度选择）</h3>
                        <p style="color:#8b8d96;font-size:0.85rem;margin-bottom:1rem">
                            系统基于合规源池并采用排他贪心算法，为您自动演算出如下 ${json.purchasing_plans.length} 种采购策略：
                        </p>
                        <div style="margin-bottom:2rem">${plansHtml}</div>
                        
                        <h3 style="color:#a78bfa;margin-bottom:0.75rem">📊 合规库内供应商综合硬广覆盖排名</h3>
                        <div style="overflow-x:auto;margin-bottom:2rem">
                            <table class="matrix-table">
                                <thead><tr><th>推荐位序</th><th>供应商抬头</th><th>完全满足项总数</th><th>精准涉及 SKU</th></tr></thead>
                                <tbody>${rankRows}</tbody>
                            </table>
                        </div>
                    </div>
                `;

                // ── Append Per-Material Detailed Reports ──
                if (detailedReports.length > 0) {
                    let reportsHtml = `<div style="margin-top: 3rem; border-top: 2px dashed rgba(255,255,255,0.2); padding-top: 2rem;">
                        <h2 style="color:#d946ef;margin-bottom:1.5rem">📑 各物料独立尽职调查报告 (AI)</h2>
                        <p style="color:#8b8d96;font-size:0.85rem;margin-bottom:2rem">以下为每种原材料经过独立的大模型查询与合规审查环节留存的原始证据链：</p>
                    `;

                    detailedReports.forEach(dr => {
                        reportsHtml += `
                        <div style="background: rgba(0,0,0,0.3); padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem;">
                            <h3 style="color:#a5f3fc; border-bottom: 1px solid #444; padding-bottom: 0.5rem; margin-bottom: 1rem;">
                                <i class="uil uil-box"></i> ${dr.sku} <span style="color:#8b8d96; font-size: 0.9em; font-weight: normal;">— ${dr.name}</span>
                            </h3>
                            <div class="markdown-body" style="font-size: 0.85rem;">
                                <div style="margin-bottom: 2rem;">
                                    <h4 style="color:#3b82f6;">🔍 [阶段一] 成分寻源与功能匹配</h4>
                                    ${marked.parse(dr.suggestion || "无响应数据")}
                                </div>
                                <div>
                                    <h4 style="color:#f59e0b;">🛡️ [阶段二] 强制合规审查与供应商筛选</h4>
                                    ${marked.parse(dr.report || "无响应数据")}
                                </div>
                            </div>
                        </div>`;
                    });
                    
                    reportsHtml += `</div>`;
                    finalArea.innerHTML += reportsHtml;
                }

            } catch (err) {
                resultDiv.innerHTML += `<div style="color:#ffb74d;margin-top:1rem;">Error: ${err.message}</div>`;
            } finally {
                btn.disabled = false;
                btn.textContent = `🔗 全公司原材料 × 供应商整合分析（${companyName}）`;
            }
        });
    });

    // Product selection event
    productSelect.addEventListener('change', (e) => {
        const productId = parseInt(e.target.value);
        traceProductMaterials(productId);
    });

    // Tracing Logic
    function traceProductMaterials(productId) {
        if (!dbData) return;

        emptyState.classList.add('hidden');
        resultsContent.innerHTML = '';
        
        const selectedProduct = (dbData.Product || []).find(p => p.Id === productId);
        if (!selectedProduct) return;

        // If the selected product is a raw material itself, just show its suppliers directly.
        if (selectedProduct.Type === 'raw-material') {
            renderMaterialCard(selectedProduct.Id, selectedProduct.SKU, selectedProduct.SKU);
            resultsArea.classList.remove('hidden');
            return;
        }

        // Find BOM for finished goods
        const bom = (dbData.BOM || []).find(b => b.ProducedProductId === productId);
        
        if (!bom) {
            resultsArea.classList.remove('hidden');
            resultsContent.innerHTML = `
                <div class="no-bom-card">
                    <i class="uil uil-info-circle"></i>
                    <p>No BOM (Bill of Materials) found for this product.</p>
                </div>`;
            return;
        }

        // Find BOM Components
        const components = (dbData.BOM_Component || []).filter(bc => bc.BOMId === bom.Id);
        
        if (components.length === 0) {
            resultsArea.classList.remove('hidden');
            resultsContent.innerHTML = `
                <div class="no-bom-card">
                    <i class="uil uil-info-circle"></i>
                    <p>BOM exists, but no components are registered for it.</p>
                </div>`;
            return;
        }

        // Render each component
        components.forEach(comp => {
            const rawMaterial = (dbData.Product || []).find(p => p.Id === comp.ConsumedProductId);
            const materialSKU = rawMaterial ? rawMaterial.SKU : `Unknown Material ID: ${comp.ConsumedProductId}`;
            renderMaterialCard(comp.ConsumedProductId, materialSKU, selectedProduct.SKU);
        });

        resultsArea.classList.remove('hidden');
    }

    // Helper to render a supplier card for a given material ID
    function renderMaterialCard(materialId, materialSKU, parentProductSKU) {
        // Find suppliers
        const supplierLinks = (dbData.Supplier_Product || []).filter(sp => sp.ProductId === materialId);
        const supplierNames = supplierLinks.map(link => {
            const s = (dbData.Supplier || []).find(sup => sup.Id === link.SupplierId);
            return s ? s.Name : 'Unknown Supplier';
        });

        // Create Card
        const card = document.createElement('div');
        card.className = 'glass-card material-card';
        
        let suppliersHtml = '';
        if (supplierNames.length > 0) {
            suppliersHtml = supplierNames.map(name => `<span class="supplier-badge"><i class="uil uil-truck"></i> ${name}</span>`).join('');
        } else {
            suppliersHtml = `<span class="supplier-badge empty">No suppliers listed</span>`;
        }

        card.innerHTML = `
            <div class="material-header">
                <i class="uil uil-puzzle-piece icon-purple"></i>
                <h3>${materialSKU}</h3>
                <button class="ai-btn" data-sku="${materialSKU}">
                    <i class="uil uil-sparkles"></i> AI Suggest Alternatives
                </button>
            </div>
            <div class="suppliers-container">
                <p class="suppliers-title">Suppliers:</p>
                <div class="suppliers-list">
                    ${suppliersHtml}
                </div>
            </div>
            <div class="ai-results-container hidden" id="ai-results-${materialId}">
                <div class="ai-loader hidden"><i class="uil uil-spinner-alt ai-spin"></i> Analyzing with Vertex AI...</div>
                <div class="ai-content markdown-body"></div>
            </div>
        `;
        resultsContent.appendChild(card);

        // Add event listener for AI button
        const aiBtn = card.querySelector('.ai-btn');
        const aiResultsContainer = card.querySelector('.ai-results-container');
        const aiLoader = card.querySelector('.ai-loader');
        const aiContent = card.querySelector('.ai-content');

        aiBtn.addEventListener('click', async () => {
            // Toggle visibility
            if(!aiResultsContainer.classList.contains('hidden') && !aiLoader.classList.contains('hidden')===false) {
                aiResultsContainer.classList.add('hidden');
                return;
            }

            aiBtn.disabled = true;
            aiResultsContainer.classList.remove('hidden');
            aiLoader.classList.remove('hidden');
            aiContent.innerHTML = '';

            try {
                const response = await fetch('/api/suggest-alternatives', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ material_sku: materialSKU, parent_product_sku: parentProductSKU })
                });

                const jsonStr = await response.json();
                aiLoader.classList.add('hidden');
                
                if (response.ok) {
                    aiContent.innerHTML = marked.parse(jsonStr.suggestion);
                    
                    // Add Deep Screening Button
                    const filterBtnWrapper = document.createElement('div');
                    filterBtnWrapper.innerHTML = `
                        <button class="ai-filter-btn" id="filter-btn-${materialId}">
                            <i class="uil uil-search-alt"></i> 🔬 Run Compliance & Deep Screening
                        </button>
                        <div class="compliance-results-container hidden" id="compliance-results-${materialId}">
                            <div class="ai-loader compliance-loader hidden"><i class="uil uil-spinner-alt ai-spin"></i> Running deep screening with Vertex AI...</div>
                            <div class="compliance-content markdown-body"></div>
                        </div>
                    `;
                    aiContent.appendChild(filterBtnWrapper);
                    
                    const filterBtn = filterBtnWrapper.querySelector('.ai-filter-btn');
                    const complianceResultsContainer = filterBtnWrapper.querySelector('.compliance-results-container');
                    const complianceLoader = filterBtnWrapper.querySelector('.compliance-loader');
                    const complianceContent = filterBtnWrapper.querySelector('.compliance-content');
                    
                    filterBtn.addEventListener('click', async () => {
                        filterBtn.disabled = true;
                        complianceResultsContainer.classList.remove('hidden');
                        complianceLoader.classList.remove('hidden');
                        complianceContent.innerHTML = '';
                        
                        try {
                            const res = await fetch('/api/screen-compliance', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ 
                                    material_sku: materialSKU, 
                                    parent_product_sku: parentProductSKU,
                                    alternatives_context: jsonStr.suggestion
                                })
                            });

                            const jsonRes = await res.json();
                            complianceLoader.classList.add('hidden');
                            if (res.ok) {
                                complianceContent.innerHTML = marked.parse(jsonRes.report);

                                // ── Phase 3: Quantity input + Optimal Scoring ──────────────
                                const scoringWrapper = document.createElement('div');
                                scoringWrapper.innerHTML = `
                                    <div class="quantity-input-group">
                                        <label>📦 需求量</label>
                                        <input type="number" class="qty-input" id="qty-input-${materialId}" 
                                               placeholder="千克 / 月" min="1" value="100" />
                                        <button class="score-btn" id="score-btn-${materialId}">
                                            🏆 开始最优解评选
                                        </button>
                                    </div>
                                    <div class="scoring-results-container hidden" id="scoring-results-${materialId}">
                                        <div class="ai-loader scoring-loader hidden">
                                            <i class="uil uil-spinner-alt ai-spin"></i> 正在查询价格、计算合并分、生成排名表…
                                        </div>
                                        <div class="scoring-content markdown-body"></div>
                                    </div>
                                `;
                                complianceContent.appendChild(scoringWrapper);

                                const scoreBtn = scoringWrapper.querySelector('.score-btn');
                                const qtyInput = scoringWrapper.querySelector('.qty-input');
                                const scoringContainer = scoringWrapper.querySelector('.scoring-results-container');
                                const scoringLoader = scoringWrapper.querySelector('.scoring-loader');
                                const scoringContent = scoringWrapper.querySelector('.scoring-content');

                                scoreBtn.addEventListener('click', async () => {
                                    const qty = parseFloat(qtyInput.value) || 100;
                                    scoreBtn.disabled = true;
                                    scoringContainer.classList.remove('hidden');
                                    scoringLoader.classList.remove('hidden');
                                    scoringContent.innerHTML = '';

                                    try {
                                        const scoreRes = await fetch('/api/score-optimal', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({
                                                material_sku: materialSKU,
                                                parent_product_sku: parentProductSKU,
                                                quantity_kg: qty,
                                                compliant_report_text: jsonRes.report
                                            })
                                        });
                                        const scoreJson = await scoreRes.json();
                                        scoringLoader.classList.add('hidden');
                                        if (scoreRes.ok) {
                                            scoringContent.innerHTML = marked.parse(scoreJson.ranking);
                                        } else {
                                            scoringContent.innerHTML = `<span style="color:#ffb74d;">Error: ${scoreJson.error}</span>`;
                                        }
                                    } catch (err) {
                                        scoringLoader.classList.add('hidden');
                                        scoringContent.innerHTML = `<span style="color:#ffb74d;">Network Error: ${err.message}</span>`;
                                    } finally {
                                        scoreBtn.disabled = false;
                                    }
                                });

                            } else {
                                complianceContent.innerHTML = `<span style="color: #ffb74d;">Error: ${jsonRes.error}</span>`;
                            }
                        } catch (err) {
                            complianceLoader.classList.add('hidden');
                            complianceContent.innerHTML = `<span style="color: #ffb74d;">Network Error: ${err.message}</span>`;
                        } finally {
                            filterBtn.disabled = false;
                        }
                    });

                    
                } else {
                    aiContent.innerHTML = `<span style="color: #ffb74d;">Error: ${jsonStr.error}</span>`;
                }
            } catch (err) {
                aiLoader.classList.add('hidden');
                aiContent.innerHTML = `<span style="color: #ffb74d;">Network Error: ${err.message}</span>`;
            } finally {
                aiBtn.disabled = false;
            }
        });
    }
});
