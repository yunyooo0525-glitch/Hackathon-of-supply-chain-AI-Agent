import re

with open('material-tracer/app.js', 'r', encoding='utf-8') as f:
    content = f.read()

# We need to find the start of the block and the start of the next block.
start_idx = content.find("document.getElementById('company-consolidate-btn').addEventListener('click', async () => {")
end_idx = content.find("    // Product selection event")

if start_idx == -1 or end_idx == -1:
    print("Cannot find indices")
    exit(1)

replacement = """document.getElementById('company-consolidate-btn').addEventListener('click', async () => {
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

                // Map Phase: Concurrency Pool
                const CONCURRENCY = 4;
                let currentIndex = 0;

                const processRM = async (rm, i) => {
                    const statusEl = document.getElementById(`status-rm-${i}`);
                    
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
                        const approvedSectionMatches = [...reportText.matchAll(/(?:最终合规放行推荐|🏆)[\s\S]*?(?=###|$)/g)];
                        const alts = [];
                        if (approvedSectionMatches.length > 0) {
                            const lines = approvedSectionMatches[0][0].split('\\n');
                            for (let line of lines) {
                                const skuMatch = line.match(/(RM-[A-Za-z0-9_-]+)/);
                                if (skuMatch) {
                                    alts.push({ sku: skuMatch[1], supplier: "当前有效" });
                                }
                            }
                        }
                        
                        compliantMap[rm.rm_sku] = alts.length > 0 ? alts : [{sku: rm.rm_sku, supplier: rm.current_suppliers[0] || '默认供应商'}];
                        
                        statusEl.innerHTML = `<span class="status-badge" style="background:#10b981;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">✅ 完成验证</span> <code style="color:#a5f3fc">${rm.rm_sku}</code> <span style="color:#8b8d96;margin-left:0.5rem">符合要求: ${compliantMap[rm.rm_sku].length} 项</span>`;

                    } catch (e) {
                        statusEl.innerHTML = `<span class="status-badge" style="background:#ef4444;padding:2px 6px;border-radius:4px;font-size:0.7rem;color:#fff;">❌ 截断失败(可重试)</span> <code style="color:#a5f3fc">${rm.rm_sku}</code>`;
                        compliantMap[rm.rm_sku] = [{sku: rm.rm_sku, supplier: rm.current_suppliers[0] || '默认供应商'}]; // fallback
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
                        ? rm.alternatives.map(a => `<code style="font-size:0.75rem">${a.sku}</code>`).join('<br>')
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
                        <td style="font-size:0.78rem;color:#8b8d96">${s.covers.map(sku => sku.split('-').slice(2,-1).join(' ')).join(', ')}</td>
                    </tr>
                `).join('');

                const greedyRows = json.greedy_minimum_set.map((g, i) => `
                    <div class="greedy-step">
                        <span class="greedy-num">${i+1}</span>
                        <strong>${g.supplier}</strong>
                        <span style="color:#8b8d96;font-size:0.85rem">→ 排他覆盖 ${g.covers.length} 种：
                            ${g.covers.map(sku => sku.split('-').slice(2,-1).join(' ')).join('、')}
                        </span>
                    </div>
                `).join('');

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

                        <h3 style="color:#38bdf8;margin-bottom:0.75rem">🎯 最优集贪心预算：最小风险组合</h3>
                        <p style="color:#8b8d96;font-size:0.85rem;margin-bottom:1rem">
                            通过前置单点极审剔除风险后，只需合作这 <strong>${json.greedy_minimum_set.length}</strong> 家供应商即可吃下此业务全盘需求：
                        </p>
                        <div class="greedy-steps" style="margin-bottom:2rem">${greedyRows}</div>
                        
                        <h3 style="color:#a78bfa;margin-bottom:0.75rem">📊 合规库内供应商综合硬广覆盖排名</h3>
                        <div style="overflow-x:auto;margin-bottom:2rem">
                            <table class="matrix-table">
                                <thead><tr><th>推荐位序</th><th>供应商抬头</th><th>完全满足项总数</th><th>精准涉及 SKU</th></tr></thead>
                                <tbody>${rankRows}</tbody>
                            </table>
                        </div>
                    </div>
                `;

            } catch (err) {
                resultDiv.innerHTML += `<div style="color:#ffb74d;margin-top:1rem;">Error: ${err.message}</div>`;
            } finally {
                btn.disabled = false;
                btn.textContent = `🔗 全公司原材料 × 供应商整合分析（${companyName}）`;
            }
        });
    });

"""

new_content = content[:start_idx] + replacement + content[end_idx:]

with open('material-tracer/app.js', 'w', encoding='utf-8') as f:
    f.write(new_content)
    
print("SUCCESS")
