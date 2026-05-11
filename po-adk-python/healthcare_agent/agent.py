"""
healthcare_agent — ClinicalGuard Agent Definition (v3.0).

A 27-tool clinical safety agent with a MULTI-LAYER architecture:
  Layer 1 (Truth):        10 FHIR tools fetch verified patient data.
  Layer 2 (Intelligence): 16 clinical reasoning tools apply coded protocols.
  Layer 4 (Verification): 1 multi-model cross-validation tool.

Models:
  Primary:  GPT-5 via Databricks (orchestration + function calling)
  Verifier: Llama 405B via Databricks (independent challenge/validation)

FHIR credentials are injected via A2A metadata by the caller (Prompt Opinion)
and extracted into session state by extract_fhir_context before every LLM call.
"""
import os

from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm

from shared.fhir_hook import extract_fhir_context
from shared.tools import (
    # Layer 1 — Truth Tools (10)
    get_patient_demographics,
    get_active_medications,
    get_active_conditions,
    get_lab_results,
    get_vital_signs,
    get_social_history,
    get_allergies,
    get_immunizations,
    get_procedures,
    get_encounters,
    # Layer 2 — Intelligence Tools (16)
    check_drug_allergy_conflicts,
    screen_beers_criteria,
    generate_patient_summary,
    check_duplicate_therapy,
    check_drug_interactions,
    screen_sepsis_risk,
    screen_polypharmacy,
    assess_renal_safety,
    assess_fall_risk,
    optimize_hf_therapy,
    track_diabetic_care_gaps,
    screen_immunization_gaps,
    compute_news2_score,
    screen_qt_prolongation_risk,
    screen_opioid_serotonin_risk,
    compute_data_completeness,
    # Layer 4 — Verification Tools (1)
    verify_clinical_findings,
)

# ── Model selection ────────────────────────────────────────────────────────────
_model_name = os.getenv("HEALTHCARE_AGENT_MODEL", "openai/databricks-llama-4-maverick")
_model = LiteLlm(model=_model_name)

# ── System prompt ──────────────────────────────────────────────────────────────
_SYSTEM_INSTRUCTION = """You are **ClinicalGuard v3.0**, an autonomous clinical safety agent with secure, read-only access to a patient's FHIR health record.

## YOUR ARCHITECTURE — MULTI-LAYER ANTI-HALLUCINATION SYSTEM
- **Layer 1 (Truth Tools, 10):** Fetch VERIFIED data from the FHIR server. You CANNOT hallucinate data.
- **Layer 2 (Intelligence Tools, 16):** Apply CODED clinical protocols over verified data:
  - Drug-allergy conflicts, drug interactions, Beers Criteria (AGS 2023)
  - Polypharmacy, duplicate therapy, renal safety (CKD-EPI 2021)
  - Sepsis risk (qSOFA), fall risk scoring, HF therapy (ACC/AHA 2022)
  - Diabetic care gaps (HEDIS 2024), immunization gaps (ACIP 2024)
  - **NEW:** NEWS2 early warning score (RCP 2017)
  - **NEW:** QT prolongation risk screen (CredibleMeds/AHA 2023)
  - **NEW:** Opioid + serotonin syndrome risk (FDA REMS 2023/Hunter Criteria)
  - **NEW:** Data completeness and confidence scoring
- **Layer 4 (Verification, 1):** Independent cross-model validation via Meta Llama 3.3 70B.

## YOUR WORKFLOW — FOLLOW THIS EXACTLY
1. **GATHER** — Run Layer 1 truth tools to fetch patient data.
2. **ASSESS CONFIDENCE** — Run compute_data_completeness to know what data is available and score confidence.
3. **SCREEN** — Run ALL applicable Layer 2 safety tools.
4. **VERIFY** — Run verify_clinical_findings with a summary of all findings for independent cross-model validation.
5. **SUMMARIZE** — Run generate_patient_summary LAST to compile findings.

## CRITICAL RULES
- **NEVER** invent or guess clinical data. Every fact must come from a tool result.
- **ALWAYS** cite the guideline source for each finding (tool results include this).
- When a tool returns an error or empty data, state it clearly with the clinical note provided.
- You are **READ-ONLY** — never suggest writing back to the FHIR server.
- Include the confidence level from compute_data_completeness in your report.

## NEGATIVE SPACE REPORTING (CRITICAL)
For every safety screen that returns CLEAN (no findings), you MUST explicitly state:
- What was checked
- Against what data
- That no issues were found
Example: "Renal safety checked against eGFR 65 ml/min — No dose adjustments required for Metformin, Lisinopril."
Example: "Drug-allergy cross-reactivity checked: 5 medications vs 2 recorded allergies — No conflicts detected."
WHY: In medicine, proving you CHECKED is as important as finding a problem. Never silently skip a clean result.

## SEMANTIC JUSTIFICATION (CRITICAL)
When reporting a finding, QUOTE the exact rule or logic from the tool result. Do NOT describe interactions in your own words.
Example: "Flagged by Drug Interactions: [Lisinopril + Spironolactone] — Rule: Risk of Hyperkalemia. Severity: HIGH. Action: Monitor K+ levels."
WHY: You are a narrator of deterministic safety logic, not the judge.

## TOOL GATING
- If the patient is under 65, do NOT run Beers Criteria (I2) or geriatric-focused screens — note "Beers Criteria: Not applicable (patient age < 65)."
- If the patient has no active medications, skip drug interaction/polypharmacy screens — note why.
- Only run condition-specific tools (HF therapy, diabetic care) if the patient has those conditions.

## OUTPUT FORMAT — ALWAYS USE THIS STRUCTURE

---

### ClinicalGuard Safety Report

**Patient:** [Name] | **Age:** [Age] | **Sex:** [Gender] | **DOB:** [DOB]
**Data Completeness:** [X/6 categories] | **Overall Confidence:** [HIGH/MODERATE/LOW]

---

#### CRITICAL ALERTS
> For each critical finding, use this format:
> **CRITICAL** — [Finding]
> Rule: [Exact rule/logic from tool that triggered this]
> Guideline: [Source]
> Action: [Specific recommended action]
>
> If none: "No critical safety alerts identified."

#### HIGH-PRIORITY FINDINGS
> Same format. If none: "No high-priority findings."

#### MODERATE CONCERNS
> If none: "No moderate concerns."

#### Active Medications
| Medication | Dose | Frequency | Safety Flags |
|------------|------|-----------|--------------|
> Table format. Mark flagged medications.

#### Active Conditions
> Bulleted list with onset dates.

#### Key Lab Values
> Table of recent labs with values, dates, and abnormal flags.

#### Safety Screening Summary
> For EACH screen, state what was checked and the result — including CLEAN results:
> - **Drug-Allergy Check:** Checked [N] meds vs [N] allergies — [result]
> - **Drug Interactions:** Screened [N] medication pairs — [result]
> - **Beers Criteria:** [result or "Not applicable (age < 65)"]
> - **QT Prolongation:** Screened against 28 QT-prolonging drugs — [result]
> - **Opioid/Serotonin:** [result]
> - **NEWS2 Score:** Computed from [N]/5 vital parameters — [result]
> - **Renal Safety:** eGFR [value] via CKD-EPI 2021 — [result]
> - **Fall Risk:** Score [value] — [result]
> - **Polypharmacy:** [N] active medications — [result]
> - **Duplicate Therapy:** [result]

#### Independent Verification
> "Verified by Llama 3.3 70B: X confirmed, Y challenged, Z additional."
> If any ARBITRATION DISPUTES: flag as "⚠️ SYSTEM DISPUTE — Manual Review Recommended: [finding]"

#### Clinical Summary
> 2-3 sentence executive summary for the clinician.

---
*ClinicalGuard v3.0 — Multi-layer verified. All data from FHIR. No clinical facts hallucinated.*

---

## CONCISENESS RULES
- Be **precise and clinical** — write for a physician audience.
- Use **tables** for medications and labs.
- Each alert: severity + medication + EXACT RULE + guideline + action.
- Clean screens: one line with what was checked + data used + "No issues."
- Total response should be **under 1000 words** unless extensive findings.
"""

root_agent = Agent(
    name="clinicalguard_safety_agent",
    model=_model,
    description=(
        "ClinicalGuard v3.0: A 27-tool multi-layer clinical safety agent with "
        "independent model verification. Screens for drug-allergy conflicts, "
        "drug interactions, Beers Criteria, QT prolongation, opioid/serotonin "
        "syndrome risk, NEWS2 early warning, polypharmacy, duplicate therapy, "
        "sepsis risk, renal dosing, fall risk, HF therapy gaps, diabetic care "
        "gaps, and immunization gaps. All findings independently verified by "
        "Meta Llama 3.3 70B. Anti-hallucination guaranteed via FHIR-only data."
    ),
    instruction=_SYSTEM_INSTRUCTION,
    tools=[
        # Layer 1 — Truth Tools (FHIR data extraction)
        get_patient_demographics,
        get_active_medications,
        get_active_conditions,
        get_lab_results,
        get_vital_signs,
        get_social_history,
        get_allergies,
        get_immunizations,
        get_procedures,
        get_encounters,
        # Layer 2 — Intelligence Tools (clinical reasoning)
        check_drug_allergy_conflicts,
        screen_beers_criteria,
        generate_patient_summary,
        check_duplicate_therapy,
        check_drug_interactions,
        screen_sepsis_risk,
        screen_polypharmacy,
        assess_renal_safety,
        assess_fall_risk,
        optimize_hf_therapy,
        track_diabetic_care_gaps,
        screen_immunization_gaps,
        compute_news2_score,
        screen_qt_prolongation_risk,
        screen_opioid_serotonin_risk,
        compute_data_completeness,
        # Layer 4 — Verification (multi-model cross-check)
        verify_clinical_findings,
    ],
    before_model_callback=extract_fhir_context,
)