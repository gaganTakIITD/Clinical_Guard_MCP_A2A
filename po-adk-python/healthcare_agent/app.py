"""
healthcare_agent — ClinicalGuard A2A application entry point.

Start:  uvicorn healthcare_agent.app:a2a_app --host 0.0.0.0 --port 8001
Card:   GET http://localhost:8001/.well-known/agent-card.json
"""
import os

from a2a.types import AgentSkill
from shared.app_factory import create_a2a_app

from .agent import root_agent

a2a_app = create_a2a_app(
    agent=root_agent,
    name="clinicalguard_safety_agent",
    description=(
        "ClinicalGuard v3.0: A 27-tool multi-layer clinical safety agent with "
        "independent model verification. 10 FHIR truth tools, 16 intelligence "
        "tools (Beers, drug interactions, qSOFA, CKD-EPI, GDMT, HEDIS, NEWS2, "
        "QT prolongation, opioid/serotonin safety), and 1 multi-model verification "
        "tool. Model-agnostic via LiteLLM (supports Gemini, OpenAI, Anthropic, etc.)."
    ),
    url=os.getenv("HEALTHCARE_AGENT_URL", os.getenv("BASE_URL", "http://localhost:8001")),
    port=8001,
    fhir_extension_uri=f"{os.getenv('PO_PLATFORM_BASE_URL', 'http://localhost:5139')}/schemas/a2a/v1/fhir-context",
    fhir_scopes=[
        # Layer 1 Truth Tool scopes
        {"name": "patient/Patient.rs",              "required": True},
        {"name": "patient/MedicationRequest.rs",    "required": True},
        {"name": "patient/Condition.rs",            "required": True},
        {"name": "patient/Observation.rs",          "required": True},
        {"name": "patient/AllergyIntolerance.rs",   "required": True},
        {"name": "patient/Immunization.rs",         "required": True},
        {"name": "patient/Procedure.rs",            "required": True},
        {"name": "patient/Encounter.rs",            "required": True},
    ],
    skills=[
        # --- Layer 2 Intelligence Skills ---
        AgentSkill(
            id="drug-allergy-safety",
            name="Drug-Allergy Conflict Check",
            description="Cross-check active medications against recorded allergies, including drug-class cross-reactivity (e.g., penicillin allergy → amoxicillin flag).",
            tags=["safety", "allergies", "medications"],
        ),
        AgentSkill(
            id="beers-criteria-screen",
            name="Beers Criteria Screen",
            description="Screen active medications against 2023 AGS Beers Criteria for patients aged 65 and older. Flags high-risk medications with clinical rationale.",
            tags=["safety", "elderly", "medications"],
        ),
        AgentSkill(
            id="drug-interaction-check",
            name="Drug Interaction Check",
            description="Screen all active medication pairs against a curated database of 60+ critical drug-drug interactions with severity ratings and mechanisms.",
            tags=["safety", "medications", "interactions"],
        ),
        AgentSkill(
            id="polypharmacy-screen",
            name="Polypharmacy Screen",
            description="Flag polypharmacy (≥5 meds) and high polypharmacy (≥10 meds). Identifies CNS-active, anticholinergic, and anticoagulant risk factors.",
            tags=["safety", "medications"],
        ),
        AgentSkill(
            id="duplicate-therapy-check",
            name="Duplicate Therapy Check",
            description="Detect two or more active drugs from the same pharmacological class (e.g., two statins, two SSRIs, two anticoagulants).",
            tags=["safety", "medications"],
        ),
        AgentSkill(
            id="sepsis-risk-screen",
            name="Sepsis Risk Screen (qSOFA)",
            description="Calculate qSOFA sepsis score from vital signs and active infection conditions. Score ≥2 triggers high sepsis alert.",
            tags=["critical-care", "sepsis", "vitals"],
        ),
        AgentSkill(
            id="renal-safety",
            name="Renal Safety Assessment",
            description="Calculate eGFR via CKD-EPI 2021, stage CKD, detect un-coded (silent) CKD, and flag medications requiring dose adjustment or avoidance.",
            tags=["nephrology", "medications", "labs"],
        ),
        AgentSkill(
            id="fall-risk",
            name="Fall Risk Assessment",
            description="Score fall risk from patient age, high-risk medications (benzos, opioids, anticholinergics), and fall-associated diagnoses.",
            tags=["safety", "elderly", "falls"],
        ),
        AgentSkill(
            id="hf-therapy-optimization",
            name="Heart Failure Therapy Optimization",
            description="Verify heart failure patients are on all 4 ACC/AHA guideline-directed therapy pillars (ACEi/ARB/ARNi, beta-blocker, MRA, SGLT2i).",
            tags=["cardiology", "medications", "guidelines"],
        ),
        AgentSkill(
            id="diabetic-care-gaps",
            name="Diabetic Care Gap Tracker",
            description="Audit diabetic patients against HEDIS 2024 quality measures: HbA1c, BP, nephropathy monitoring, statin therapy.",
            tags=["endocrine", "quality", "diabetes"],
        ),
        AgentSkill(
            id="immunization-gaps",
            name="Immunization Gap Screen",
            description="Identify overdue vaccines per ACIP 2024 schedule and cross-check allergy contraindications (e.g., egg allergy → flu vaccine formulation).",
            tags=["preventive", "immunizations", "allergies"],
        ),
        AgentSkill(
            id="clinical-summary",
            name="Comprehensive Patient Summary",
            description="Generate a SOAP-style clinical summary compiling all verified patient data and safety findings into a structured clinician brief.",
            tags=["summary", "clinical", "comprehensive"],
        ),
        # --- v3.0 New Skills ---
        AgentSkill(
            id="news2-early-warning",
            name="NEWS2 Early Warning Score",
            description="Compute National Early Warning Score 2 from vital signs. Scores RR, SpO2, SBP, HR, temperature. Risk tiers: LOW/MEDIUM/HIGH with clinical response guidance.",
            tags=["critical-care", "vitals", "deterioration"],
        ),
        AgentSkill(
            id="qt-prolongation-screen",
            name="QT Prolongation Risk Screen",
            description="Screen active medications against 28+ QT-prolonging drugs (CredibleMeds/AHA 2023). Check electrolytes (K+, Mg2+, Ca2+) for amplifying factors. Flags Torsades de Pointes risk.",
            tags=["safety", "cardiology", "medications"],
        ),
        AgentSkill(
            id="opioid-serotonin-screen",
            name="Opioid and Serotonin Syndrome Screen",
            description="Screen for opioid+CNS depressant combos (FDA black box) and serotonin syndrome risk from serotonergic drug combinations (Hunter Criteria). Covers FDA REMS 2023.",
            tags=["safety", "opioids", "serotonin"],
        ),
        AgentSkill(
            id="multi-model-verification",
            name="Multi-Model Verification",
            description="Independent cross-validation of clinical findings by a separate AI model. Verifies, challenges, and supplements primary analysis findings.",
            tags=["verification", "safety", "multi-model"],
        ),
    ],
)
