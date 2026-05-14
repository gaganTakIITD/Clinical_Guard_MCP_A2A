<p align="center">
  <h1 align="center">🛡️ ClinicalGuard v3.0</h1>
  <p align="center">
    <strong>Multi-Layer Clinical Safety Agent with Cross-Model Verification</strong>
  </p>
  <p align="center">
    <a href="#architecture">Architecture</a> •
    <a href="#features">Features</a> •
    <a href="#quick-start">Quick Start</a> •
    <a href="#how-it-works">How It Works</a> •
    <a href="#tech-stack">Tech Stack</a>
  </p>
</p>

## ⚠️ JUDGES: How to Test ClinicalGuard ⚠️

**[ Watch this video on exactly how to test the agent](https://www.youtube.com/watch?v=jWFwxVi0Kko)**

If the "Try it out" link on Devpost sent you to a private workspace, please follow these steps to test the live agent:
1. **Load the Patient Data:** First, download the `po-adk-python/test_cases/case4_james_park_healthy_adult.json` file from this repository.
2. In the **Prompt Opinion Platform**, look at the left sidebar, click **Patient Data -> Import**, and upload that JSON file to load James Park's FHIR records.
3. Navigate to the **Marketplace** on the left sidebar.
4. Search for **"clinicalguard"**.
5. Look for the agent named **`agent_deployed_on_render`** published by **Gagan Tak** and click **Add**.
6. Open your Launchpad and test it with this prompt: 
   > *"Please run a complete clinical safety test for James Park (ID: a46eff17-dde1-42c3-8a5a-67a2d71a6412)."*

*(Note: The Prompt Opinion platform should automatically handle authentication. However, if you are ever prompted for an API Key to connect to this agent, use: **`clinicalguard-hackathon-2025`**)*

---
## What is ClinicalGuard?

ClinicalGuard is a **27-tool autonomous clinical safety agent** that screens patients for medication risks, care gaps, and clinical deterioration by analyzing their FHIR health records. It uses a **4-layer anti-hallucination architecture** where clinical facts are fetched from verified FHIR servers, safety findings are computed by deterministic Python rules (not LLMs), and all conclusions are independently verified by a second AI model.

### Key Innovation

> **Zero-hallucination clinical safety screening** — Every clinical fact traces to a FHIR record. Every safety finding is computed by 738 lines of deterministic Python. Every conclusion is independently verified by a second AI model from a different architecture.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    ClinicalGuard v3.0 Architecture                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Layer 0: SEMANTIC ROUTER                                           │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Age/condition-based tool gating (skip Beers for <65, etc.) │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ↓                                      │
│  Layer 1: TRUTH TOOLS (10 FHIR fetchers)                            │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Parallel prefetch via ThreadPoolExecutor(10)               │    │
│  │  Demographics │ Meds │ Conditions │ Labs │ Vitals           │    │
│  │  Social Hx │ Allergies │ Immunizations │ Procedures │ Enc   │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ↓                                      │
│  Layer 2: INTELLIGENCE TOOLS (16 deterministic screens)             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Drug-Allergy │ Beers (AGS 2023) │ Drug Interactions        │    │
│  │  Polypharmacy │ Duplicate Therapy │ Renal Safety (CKD-EPI)  │    │
│  │  Sepsis (qSOFA) │ Fall Risk │ HF GDMT (ACC/AHA 2022)       │    │
│  │  Diabetic Care (HEDIS) │ Immunization Gaps (ACIP 2024)      │    │
│  │  NEWS2 (RCP 2017) │ QT Prolongation (CredibleMeds)          │    │
│  │  Opioid/Serotonin (FDA REMS) │ Confidence Scoring           │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ↓                                      │
│  Layer 3: ORCHESTRATION                                             │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Primary LLM (configurable via LiteLLM)                     │    │
│  │  • Negative space reporting (clean results stated)          │    │
│  │  • Semantic justification (exact rules quoted)              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                              ↓                                      │
│  Layer 4: INDEPENDENT VERIFICATION + ARBITRATION                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  Verifier LLM (independent model via LiteLLM)              │    │
│  │  Verified │ Challenged │ Missed                              │    │
│  │  If challenged → Arbitration Loop:                           │    │
│  │    Primary ACCEPTS (corrects) or REJECTS (cites guideline)  │    │
│  │  If unresolved → "⚠️ System Dispute: Manual Review"          │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Features

### 27 Clinical Safety Tools

| Layer | Count | Tools |
|-------|-------|-------|
| **Layer 1 — Truth** | 10 | FHIR data fetchers with parallel prefetch |
| **Layer 2 — Intelligence** | 16 | Deterministic clinical protocols |
| **Layer 4 — Verification** | 1 | Cross-model verification with arbitration |

### 14 Deterministic Knowledge Bases (738 lines)

| Knowledge Base | Source |
|---------------|--------|
| Beers Criteria (75+ drugs) | AGS 2023 |
| Drug Interactions (60+ pairs) | FDA guidance |
| Drug Class Map (19 classes, 150+ drugs) | Clinical pharmacology |
| Renal Dosing (34 drugs) | KDIGO/FDA |
| eGFR Calculator (race-free) | CKD-EPI 2021 |
| HF GDMT (4 pillars, 30+ drugs) | ACC/AHA 2022 |
| Diabetes HEDIS (5 measures) | HEDIS 2024 |
| Vaccine Schedule (6 vaccines, CVX) | ACIP 2024 |
| Fall Risk Scoring (30+ meds, 15+ conditions) | Composite |
| Allergy Cross-Reactivity (7 families) | Clinical immunology |
| NEWS2 Parameters (5 vitals) | RCP 2017 |
| QT-Prolonging Drugs (28 drugs, 3 tiers) | CredibleMeds/AHA 2023 |
| Serotonergic Drugs (7 categories, 8 combos) | Hunter Criteria |
| Opioid + CNS Combos (11 opioids, 6 classes) | FDA REMS 2023 |

### Anti-Hallucination Guarantee

| Layer | Can Hallucinate? | Why? |
|-------|-----------------|------|
| Layer 1 (FHIR) | ❌ No | HTTP GET from verified server |
| Layer 2 (Python) | ❌ No | Hardcoded lookup tables, no LLM |
| Layer 3 (LLM) | ⚠️ Constrained | Only formats tool results, cannot invent data |
| Layer 4 (Verifier) | ⚠️ Independent | Different model architecture catches issues |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Google API key (for Gemini) or any LiteLLM-supported provider

### Setup

```bash
# Clone the repository
git clone https://github.com/gaganTakIITD/hackathon-test.git
cd hackathon-test/po-adk-python

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys (see .env.example)
```

### Run

```bash
# Start the agent
python -m uvicorn healthcare_agent.app:a2a_app --host 0.0.0.0 --port 8001

# In another terminal, start ngrok tunnel
ngrok http 8001
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `GOOGLE_API_KEY` | Google API key (for Gemini models) |
| `HEALTHCARE_AGENT_MODEL` | Primary model (default: `gemini/gemini-2.5-flash`) |
| `VERIFIER_MODEL` | Verification model (default: `gemini/gemini-2.5-flash-lite`) |

---

## How It Works

### 1. Parallel Data Fetch (Layer 1)
When a patient request arrives, **all 10 FHIR resources are fetched concurrently** using `ThreadPoolExecutor(max_workers=10)` in the `before_model_callback`. The LLM wakes up to fully populated data — zero HTTP latency during orchestration.

### 2. Deterministic Safety Screening (Layer 2)
16 clinical protocols run as **pure Python** — no LLM involvement. Every drug interaction, every Beers flag, every eGFR calculation is a hardcoded lookup table. This is the anti-hallucination core.

### 3. Intelligent Orchestration (Layer 3)
The primary LLM synthesizes findings with:
- **Negative space reporting** — explicitly states clean results ("No renal adjustments needed for eGFR 65")
- **Semantic justification** — quotes the exact deterministic rule, not its own interpretation
- **Tool gating** — skips irrelevant screens (no Beers Criteria for a 25-year-old)

### 4. Cross-Model Verification (Layer 4)
An independent verifier model reviews all findings:
- **Verified** — confirms the finding
- **Challenged** — disputes it → triggers Arbitration Loop
- **Missed** — identifies additional concerns

**Arbitration Loop:** If challenged, the primary model must either ACCEPT (correct its output) or REJECT (cite the specific clinical guideline). Unresolved disputes are flagged as "⚠️ System Dispute — Manual Review Recommended."

---

## Project Structure

```
po-adk-python/
├── healthcare_agent/
│   ├── agent.py              # Agent definition, 27-tool registration, system prompt
│   ├── app.py                # A2A app entry point, skill declarations
│   └── __init__.py
├── shared/
│   ├── tools/
│   │   ├── fhir.py           # Layer 1: 10 FHIR truth tools (with prefetch support)
│   │   ├── clinical.py       # Layer 2: 16 deterministic intelligence tools
│   │   ├── verification.py   # Layer 4: Multi-model verification + arbitration
│   │   └── __init__.py       # Tool registry (27 tools exported)
│   ├── protocols/
│   │   └── clinical_rules.py # 738 lines of deterministic knowledge bases
│   ├── fhir_hook.py          # Before-model callback + parallel prefetch engine
│   ├── middleware.py          # A2A protocol middleware
│   ├── logging_utils.py      # Structured logging
│   └── app_factory.py        # App initialization
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Agent Framework** | Google ADK (Agent Development Kit) |
| **Protocol** | A2A (Agent-to-Agent) |
| **Primary Model** | Gemini 2.5 Flash (configurable via LiteLLM) |
| **Verification Model** | Gemini 2.5 Flash Lite (configurable via LiteLLM) |
| **LLM Router** | LiteLLM |
| **Health Data** | HL7 FHIR R4 |
| **Platform** | Prompt Opinion |
| **Deployment** | Uvicorn + ngrok |
| **Language** | Python 3.11 |

---

## Clinical Guidelines Referenced

- AGS Beers Criteria 2023
- AHA/CredibleMeds QT Risk Classification 2023
- FDA REMS Opioid Safety 2023
- Hunter Serotonin Toxicity Criteria
- Royal College of Physicians NEWS2 (2017)
- ACC/AHA Heart Failure GDMT (2022)
- CKD-EPI eGFR Equation (2021, race-free)
- HEDIS Diabetes Care Measures (2024)
- ACIP Immunization Schedule (2024)
- qSOFA Sepsis Screening Criteria

---

## Team

Built for the **Agents Assemble Hackathon** on Prompt Opinion.

---

## License

This project is submitted as part of a hackathon competition. All rights reserved.
