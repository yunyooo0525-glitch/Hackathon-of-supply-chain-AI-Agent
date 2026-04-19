# Material Tracer — Agentic Supply Chain Procurement Intelligence

> An AI-powered procurement decision-support system that automates raw material sourcing, regulatory compliance verification, and supplier consolidation for consumer health products.

---

## Table of Contents

1. [Problem Background](#1-problem-background)
2. [Data Architecture](#2-data-architecture)
3. [System Architecture](#3-system-architecture)
4. [End-to-End Processing Pipeline](#4-end-to-end-processing-pipeline)
5. [AI Reasoning Capabilities](#5-ai-reasoning-capabilities)
6. [Procurement Plan Output & Trade-offs](#6-procurement-plan-output--trade-offs)
7. [Getting Started](#7-getting-started)
8. [Demo Walkthrough](#8-demo-walkthrough)
9. [API Reference](#9-api-reference)
10. [Commercial Value](#10-commercial-value)

---

## 1. Problem Background

### The Procurement Challenge in Consumer Health

Consumer health brands (nutritional supplements, vitamins, OTC wellness products) routinely source **20–100+ distinct raw materials** per product line. Each material may have:

- Multiple chemically equivalent forms with varying bioavailability (e.g., Magnesium Citrate vs. Magnesium Oxide)
- Multiple competing suppliers with different price points, lead times, and certifications
- Strict regulatory obligations that vary by market and product claim (Organic, Vegan, Non-GMO, FDA GRAS)

**The current state of procurement** requires specialized category managers to manually:
1. Research equivalent raw material alternatives
2. Cross-reference suppliers against regulatory databases
3. Negotiate contracts with dozens of suppliers simultaneously
4. Periodically re-evaluate the supplier mix for cost and risk optimization

This process is **slow** (weeks to months), **expensive** (senior specialist labor), and **error-prone** (regulatory violations can trigger product recalls). Without systematic tooling, procurement teams must individually track and validate every material-supplier pair across their entire portfolio.

### What This System Solves

Material Tracer compresses the above workflow into a fully automated, evidence-backed AI pipeline that:

- Identifies every viable raw material substitute from a global supplier database
- Validates each substitute against the product's mandatory compliance profile
- Outputs a minimum-supplier procurement plan that covers all materials while giving procurement managers explicit, citable evidence for every decision

---

## 2. Data Architecture

### Database Schema

The system operates on a relational dataset (exported from SQLite to `data.json`) with the following core entities:

```
Company
  └── Product (Type: finished-good | raw-material)
        └── BOM (Bill of Materials)
              └── BOM_Component (links finished-good → raw-materials with quantity)

Supplier
  └── Supplier_Product (many-to-many: which supplier provides which raw-material SKU)
```

### Entity Relationships

```
┌──────────┐     ┌─────────────┐     ┌─────────────┐
│  Company │────▶│   Product   │────▶│     BOM     │
└──────────┘     │  (FG / RM)  │     └──────┬──────┘
                 └─────────────┘            │
                                            ▼
                                    ┌───────────────┐
                                    │ BOM_Component │
                                    │ (RM + qty)    │
                                    └───────────────┘

┌──────────┐     ┌──────────────────┐     ┌─────────┐
│ Supplier │────▶│ Supplier_Product │────▶│ Product │
└──────────┘     └──────────────────┘     │  (RM)   │
                                          └─────────┘
```

### SKU Naming Convention

Raw material SKUs encode semantic information:

```
RM-C{category}-{chemical-name}-{uuid}
e.g.  RM-C4-calcium-citrate-05c28cc3
      RM-C28-magnesium-citrate-d364c220
```

Finished good SKUs encode their retail source:

```
FG-{retailer}-{product-id}
e.g.  FG-amazon-b07z2x2xtc
      FG-cvs-342300
```

This naming scheme allows the system to reverse-engineer the product context (retailer + SKU → public product page) for formulation analysis.

### Data Scale

The demo database contains:
- **61 companies** spanning supplements, OTC health, and private-label brands
- **876 raw material SKUs** across minerals, vitamins, botanicals, and excipients
- **149 finished good products** with full Bill of Materials (1,528 BOM components total)
- **40 suppliers** with 1,633 supplier-product linkages (many-to-many)

---

## 3. System Architecture

The system is organized into three distinct layers:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                          │
│  Browser (Vanilla JS)                                               │
│  • Product/company selector     • Real-time progress tracker        │
│  • Compliance evidence viewer   • Purchasing plan cards             │
│  • Per-material due diligence   • Supplier ranking table            │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ HTTP (REST JSON)
┌─────────────────────────────▼───────────────────────────────────────┐
│                          REASONING LAYER                            │
│  Python HTTP Server (server.py)                                     │
│                                                                     │
│  ┌─────────────────────┐   ┌──────────────────────────────────────┐ │
│  │  Phase 1 Agent      │   │  Phase 2 Agent                       │ │
│  │  /suggest-alts      │   │  /screen-compliance                  │ │
│  │                     │   │                                      │ │
│  │  • Product page     │   │  • FDA GRAS verification             │ │
│  │    web scraping     │   │  • USP heavy metal audit             │ │
│  │  • Functional role  │   │  • Organic/Vegan/Non-GMO screening   │ │
│  │    inference        │   │  • Bioavailability hierarchy check   │ │
│  │  • TOP 10 ranked    │   │  • Inline-cited evidence report      │ │
│  │    alternatives     │   │                                      │ │
│  └─────────────────────┘   └──────────────────────────────────────┘ │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │  Consolidation Engine  /compute-consolidation                   ││
│  │  • Builds supplier × RM coverage matrix                        ││
│  │  • Greedy set-cover algorithm                                   ││
│  │  • Outputs 3 procurement strategy plans                         ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────┬───────────────────────────────────────┘
                              │ Vertex AI REST API
┌─────────────────────────────▼───────────────────────────────────────┐
│                           DATA & AI LAYER                           │
│                                                                     │
│  ┌──────────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │  data.json       │  │ Gemini 2.5    │  │  Google Search       │ │
│  │  (local DB)      │  │ Flash         │  │  Grounding           │ │
│  │                  │  │ (Vertex AI)   │  │  (real-time web)     │ │
│  └──────────────────┘  └───────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. End-to-End Processing Pipeline

### Input

User selects a **Company** and a **Finished Good Product** from the UI. The system loads all raw materials in the product's Bill of Materials.

### Map Phase — Parallel Per-Material Analysis

For each raw material, two sequential AI calls are made concurrently across all materials:

#### Step 1 — Phase 1: Functional Similarity Sourcing

```
Input:  material_sku, parent_product_sku
Output: Top 10 candidate alternative SKUs, ranked by functional fit
```

**How it works:**

1. If the parent product is a finished good (`FG-` prefix), the system extracts the retailer name and product ID from the SKU, then **scrapes the public product page** using a Python `urllib` scraper to obtain the real product description, ingredient list, and marketing claims.

2. The scraped text and the full supplier/product database JSON are passed to **Gemini 2.5 Flash with Google Grounding enabled**. The AI is prompted to:
   - Understand the specific functional role this raw material plays in the formulation (not generic chemistry — e.g., *"acts as a flow agent for tablet compression"*, not just *"is silicon dioxide"*)
   - Rank ALL database candidates by functional substitutability
   - Output the **top 10 most equivalent SKUs** with accurate supplier attribution pulled from the `Supplier_Product` table

3. Every claim supported by a web search result must be cited inline with a Markdown URL: `claim[1](https://source)`.

#### Step 2 — Phase 2: Regulatory Compliance Audit

```
Input:  Phase 1 candidate list, parent_product_sku, scraped product intro
Output: Disqualified SKU list + Final Compliant Approvals list with evidence
```

**How it works:**

1. The product description scraped in Phase 1 is re-analyzed to **identify all mandatory compliance constraints** — the AI extracts claims like "USDA Organic", "100% Vegan", "Non-GMO" from the product marketing copy.

2. Each candidate SKU's underlying chemical compound is evaluated against:
   | Check | Standard |
   |-------|----------|
   | Food safety baseline | Food-Grade classification |
   | Safety recognition | FDA GRAS (Generally Recognized as Safe) list |
   | Purity | USP heavy metal limits (e.g., Pb < 0.5 ppm) |
   | Bioavailability | Premium forms (citrate, malate, gluconate) preferred; carbonate/oxide disqualified for premium products |
   | Product-specific | Organic, Vegan, Non-GMO, Gluten-Free as inferred from product claims |

3. Every compliance assertion is supported by a cited web source, appended inline at the exact sentence where the claim is made — never collected at the bottom.

4. The output is a structured Markdown report with:
   - `🚫 Disqualified Candidates` — each rejected SKU with a one-sentence rationale
   - `🏆 Final Compliant Approvals` — each accepted SKU with full `RM-` code, supplier name, and compliance justification

### Reduce Phase — Greedy Supplier Consolidation

```
Input:  rm_compliant_map  { rm_sku → [{ sku, suppliers[] }] }
Output: 3 purchasing plans + supplier coverage ranking
```

**How it works:**

1. The frontend builds a `compliantMap` — a dictionary mapping each original RM to its list of compliant alternatives (always including the original RM itself as a valid procurement option).

2. This is sent to the `/api/compute-consolidation` endpoint, which builds a **supplier × RM coverage matrix**:
   - For each supplier: which original RMs can it fulfill (via its compliant SKUs)?
   - What is its total coverage count?

3. A **greedy set-cover algorithm** runs three times with different exclusion constraints to produce three purchasing plans:

```python
# Pseudocode
def compute_greedy(exclude_suppliers={}):
    uncovered = all_rm_skus
    plan = []
    for supplier in ranked_by_coverage:           # descending coverage
        if supplier in exclude_suppliers: continue
        new_coverage = supplier.covers ∩ uncovered
        if new_coverage:
            plan.append(supplier → new_coverage)
            uncovered -= new_coverage
    # Safety net: force-cover remaining RMs
    for rm in uncovered:
        plan.append(rm.first_compliant_alt → rm)
    return plan
```

4. A **supplier coverage ranking table** is also returned, showing each supplier's total compliant SKU count and the specific RMs they qualify to supply.

---

## 5. AI Reasoning Capabilities

### Functional Role Inference

The system does not perform naive keyword matching. It asks the AI to reason about **formulation-level functionality**:

> *"Calcium Carbonate in a chewable antacid tablet functions primarily as the active buffering agent. Calcium Citrate, while chemically similar, would serve the same function at a lower dose due to superior solubility — making it a valid and preferable substitute in this context."*

This is distinct from simply knowing that both are calcium salts.

### Compliance Reasoning with Evidence

The AI auditor reasons about compliance at the **chemical compound level**, not just at the SKU label level. Because the supplier-assigned SKU codes are internal identifiers (not publicly searchable), the AI extracts the chemical identity from the SKU name and searches the web for that compound's regulatory status:

```
RM-C28-magnesium-citrate-d364c220
         ↓
  compound: "magnesium citrate"
         ↓
  Google Search: "magnesium citrate FDA GRAS status"
         ↓
  Finding: "Magnesium citrate is affirmed GRAS under 21 CFR 184.1205[1](https://www.ecfr.gov/...)"
```

This means the compliance audit is grounded in **real regulatory databases** accessed in real-time, not static rule tables.

### Anti-Hallucination Valve

All AI-generated SKU codes in the Final Compliant Approvals section are validated against the local `data.json` database before being passed to the consolidation engine. Any SKU that does not exist in the database is silently discarded. This prevents hallucinated supplier relationships from corrupting the procurement plan.

---

## 6. Procurement Plan Output & Trade-offs

The system outputs three procurement strategies to reflect different business priorities:

| Plan | Algorithm | Rationale | Best For |
|------|-----------|-----------|----------|
| **Plan 1: Extreme Consolidation** | Pure greedy max-coverage | Minimize the number of supplier relationships | Small teams, cost efficiency |
| **Plan 2: Resilient Distributed** | Greedy excluding #1 supplier | Avoid single-point-of-failure dependency | Risk-sensitive supply chains |
| **Plan 3: Multi-Source Diversification** | Greedy excluding top 2 | Actively build secondary supplier network | Strategic diversification |

### Interpreting a Plan

Each plan shows:
- The ordered set of suppliers selected
- The specific compliant alternative SKUs each supplier will fulfill
- The number of original RM requirements each supplier covers exclusively

Example output:
```
Plan 1: Extreme Consolidation
1. Jost Chemical  → Covers 7 RMs: RM-C1-calcium-citrate-..., RM-C17-potassium-chloride-..., ...
2. Ashland        → Covers 2 RMs: RM-C11-silica-..., RM-C3-cellulose-...
```

This means the procurement team only needs to negotiate with **2 suppliers** instead of the original 9, while maintaining 100% material coverage with fully compliant alternatives.

### Evidence Trail

For each approved alternative, the system retains the full Phase 1 + Phase 2 AI due diligence report, accessible in the "Individual Material Due Diligence Reports" section of the UI. This provides an auditable justification chain for every procurement decision.

---

## 7. Getting Started

### Prerequisites

- Python 3.10+
- A Google Cloud project with **Vertex AI API** enabled
- A **Service Account** with the `Vertex AI User` IAM role
- The service account key downloaded as a JSON file

### Installation

```bash
git clone https://github.com/yunyooo0525-glitch/Hackathon-of-supply-chain-AI-Agent.git
cd Hackathon-of-supply-chain-AI-Agent

pip install google-auth google-auth-httplib2 requests
```

### Configuration

```bash
# Set credentials via environment variables (never commit your key file)
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your-service-account-key.json"
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
```

### Start the Server

```bash
cd material-tracer
python3 server.py
# Server starts at http://localhost:8000
```

Open your browser at **http://localhost:8000**

---

## 8. Demo Walkthrough

### Step 1 — Select a Company and Product

Choose a company (e.g., *NatureMade*) from the dropdown. Select a finished product (e.g., *FG-amazon-b07z2x2xtc* — an Organic Turmeric Curcumin supplement on Amazon).

### Step 2 — Launch Full-Company Analysis

Click **🔗 Full Company Raw Materials × Supplier Consolidation Analysis**.

The system reads the BOM graph and identifies all raw materials. A real-time progress tracker shows each material moving through two analysis stages:

```
[Function Search..]  RM-C4-calcium-c77f1de7
[Deep Audit..]       RM-C4-calcium-c77f1de7
[✅ Validation Complete]  RM-C4-calcium-c77f1de7   Compliant: 7 items
```

### Step 3 — Review Compliance Reports

After all materials complete, scroll down to **📑 Individual Material Due Diligence Reports**.

Each material's report contains:
- **Phase 1**: Full formulation analysis explaining *why* the material plays its specific role, plus the ranked list of alternatives with supplier attribution
- **Phase 2**: Compliance audit with inline citations — e.g.:

> *"Calcium Citrate is recognized as GRAS under 21 CFR 184.1191`[1](https://www.ecfr.gov/current/title-21/chapter-I/subchapter-B/part-184/subpart-B/section-184.1191)` and readily meets USP purity standards for heavy metals`[2](https://www.usp.org/...)`."*

### Step 4 — Review Procurement Plans

The **🎯 Intelligent Purchasing Plans** section displays three calculated strategies:

- Each plan shows the minimum supplier set required
- Each supplier's exclusive coverage count and specific SKUs are listed
- The **📊 Supplier Coverage Ranking** table shows which suppliers have the broadest footprint across compliant materials

### Step 5 — Single-Material Deep Dive (Optional)

For any individual material card, click **🏆 Start Optimal Solution Selection** and enter a monthly demand quantity (kg/month). The system queries real-time pricing from PureBulk's website and combines it with the pre-calculated consolidation score to rank all candidates by a composite score:

```
Total Score = Price Score (40) + Consolidation Score (45) + Scale Fit Score (15)
```

---

## 9. API Reference

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `/api/db` | GET | — | Full database JSON |
| `/api/companies` | GET | — | Company list |
| `/api/products` | GET | `company_id` | Product list |
| `/api/materials` | GET | `product_sku` | BOM raw materials |
| `/api/company-rm-list` | POST | `company_id` | All RMs across company products |
| `/api/suggest-alternatives` | POST | `material_sku`, `parent_product_sku` | Phase 1 Markdown report |
| `/api/screen-compliance` | POST | `material_sku`, `parent_product_sku`, `alternatives_context` | Phase 2 Markdown report |
| `/api/compute-consolidation` | POST | `company_id`, `rm_compliant_map` | 3 plans + supplier rankings |
| `/api/optimize-material` | POST | `material_sku`, `company_id`, `quantity_kg`, `compliant_report` | Scored candidate ranking |

---

## 10. Commercial Value

### System Capabilities vs. Traditional Approach

| Dimension | Traditional Manual Process | Material Tracer |
|-----------|---------------------------|------------------|
| Alternative discovery | Analyst research, often incomplete | Exhaustive DB scan ranked by functional fit |
| Compliance evidence | Informal notes, undocumented | Inline citations with live regulatory URLs |
| Supplier selection logic | Judgment-based, not reproducible | Deterministic greedy algorithm, fully auditable |
| Coverage guarantee | Best-effort | 100% RM coverage with algorithmic safety net |
| Audit trail | None | Full per-material Phase 1 + Phase 2 AI report |
| Risk scenario planning | Manual re-analysis required | 3 strategies generated simultaneously (Plans 1–3) |

### Extensibility

The system is designed to be extended along three dimensions:

1. **Live Database Integration**: Replace `data.json` with a live PostgreSQL or BigQuery connection to reflect real-time inventory and supplier catalog changes

2. **Additional Compliance Jurisdictions**: The Phase 2 prompt can be extended with EU Novel Food regulations, Health Canada standards, or market-specific Halal/Kosher requirements

3. **Automated Re-optimization**: Trigger the consolidation pipeline on supply disruption events (e.g., a supplier's FDA warning letter) to instantly recompute alternative procurement plans

---

## License

MIT — see [LICENSE](LICENSE)