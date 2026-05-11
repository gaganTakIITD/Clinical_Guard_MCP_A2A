"""
Shared tools catalogue — ClinicalGuard 27-tool suite.

Layer 1 — Truth Tools (10):  FHIR data extraction, no hallucination possible.
Layer 2 — Intelligence Tools (16):  Clinical reasoning over verified data.
Layer 4 — Verification Tools (1):  Multi-model cross-validation.
"""

# ── Layer 1: Truth Tools (fhir.py) ────────────────────────────────────────────
from .fhir import (
    get_patient_demographics,     # T1
    get_active_medications,       # T2
    get_active_conditions,        # T3
    get_lab_results,              # T4
    get_vital_signs,              # T5
    get_social_history,           # T6
    get_allergies,                # T7
    get_immunizations,            # T8
    get_procedures,               # T9
    get_encounters,               # T10
)

# ── Layer 2: Intelligence Tools (clinical.py) ─────────────────────────────────
from .clinical import (
    check_drug_allergy_conflicts, # I1  — meds vs allergies
    screen_beers_criteria,        # I2  — inappropriate meds for elderly
    generate_patient_summary,     # I3  — comprehensive SOAP-style summary
    check_duplicate_therapy,      # I4  — same-class drug duplication
    check_drug_interactions,      # I5  — drug-drug interaction pairs
    screen_sepsis_risk,           # I6  — qSOFA scoring
    screen_polypharmacy,          # I7  — ≥5/≥10 medication flags
    assess_renal_safety,          # I8  — eGFR + CKD + renal dosing
    assess_fall_risk,             # I9  — fall risk scoring
    optimize_hf_therapy,          # I10 — HF 4-pillar GDMT check
    track_diabetic_care_gaps,     # I11 — HEDIS diabetes audit
    screen_immunization_gaps,     # I12 — ACIP vaccine gaps
    compute_news2_score,          # I13 — NEWS2 early warning score
    screen_qt_prolongation_risk,  # I14 — QT prolongation risk
    screen_opioid_serotonin_risk, # I15 — opioid/serotonin screen
    compute_data_completeness,    # I16 — confidence scoring
)

# ── Layer 4: Verification Tools (verification.py) ────────────────────────────
from .verification import (
    verify_clinical_findings,     # V1  — multi-model cross-check
)

__all__ = [
    # Layer 1
    "get_patient_demographics", "get_active_medications",
    "get_active_conditions", "get_lab_results", "get_vital_signs",
    "get_social_history", "get_allergies", "get_immunizations",
    "get_procedures", "get_encounters",
    # Layer 2
    "check_drug_allergy_conflicts", "screen_beers_criteria",
    "generate_patient_summary", "check_duplicate_therapy",
    "check_drug_interactions", "screen_sepsis_risk",
    "screen_polypharmacy", "assess_renal_safety",
    "assess_fall_risk", "optimize_hf_therapy",
    "track_diabetic_care_gaps", "screen_immunization_gaps",
    "compute_news2_score", "screen_qt_prolongation_risk",
    "screen_opioid_serotonin_risk", "compute_data_completeness",
    # Layer 4
    "verify_clinical_findings",
]
