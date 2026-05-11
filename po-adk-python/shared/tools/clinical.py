"""
layer2_tools.py
---------------
Layer 2 â€” Intelligence Tools
These tools apply clinical reasoning OVER verified Layer 1 data.
The LLM reasons about confirmed facts â€” it cannot invent lab values,
medication names, or patient demographics.

Architecture: Hybrid approach
  - Python deterministic rules  â†’ flag specific clinical issues
  - LLM (via agent)            â†’ explain findings in clinical language
"""

from datetime import datetime, date, timedelta

from google.adk.tools import ToolContext

from shared.tools.fhir import (
    _error_result,
    get_patient_demographics, get_active_medications, get_active_conditions,
    get_lab_results, get_vital_signs, get_social_history,
    get_allergies, get_immunizations, get_procedures,
)
from shared.protocols.clinical_rules import (
    BEERS_CRITERIA, DRUG_INTERACTIONS, DRUG_CLASS_MAP, RENAL_DOSING,
    ALLERGY_CROSS_REACTIVITY, HF_GDMT_PILLARS, HF_DIAGNOSIS_CODES,
    DIABETES_CODES, DIABETES_HEDIS_MEASURES, VACCINE_SCHEDULE,
    FALL_RISK_MEDICATIONS, FALL_RISK_CONDITIONS,
    INFECTION_SNOMED_CODES, INFECTION_ICD_PREFIXES, ALTERED_MENTATION_CODES,
    calculate_egfr, stage_ckd,
    NEWS2_PARAMS, NEWS2_RESPONSE,
    QT_PROLONGING_DRUGS, QT_ELECTROLYTE_LOINC,
    SEROTONERGIC_DRUGS, SEROTONIN_CRITICAL_COMBOS,
    OPIOID_DRUGS, CNS_DEPRESSANT_DRUGS,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_drug_name(name: str) -> str:
    """Lowercase and strip for substring matching."""
    return name.lower().replace("-", " ").strip()


def _drug_matches(medication_name: str, drug_substring: str) -> bool:
    """Check if a drug substring appears in a medication display name."""
    norm_med = _normalize_drug_name(medication_name)
    norm_sub = _normalize_drug_name(drug_substring)
    return norm_sub in norm_med


def _days_since(date_str: str) -> int:
    """Return days elapsed since a date string (YYYY-MM-DD or ISO8601)."""
    if not date_str:
        return 99999
    try:
        dt = datetime.fromisoformat(date_str[:10]).date()
        return (date.today() - dt).days
    except Exception:
        return 99999


def _extract_med_names(meds_data: dict) -> list[str]:
    return [m.get("medication", "") for m in meds_data.get("data", {}).get("medications", [])]


def _extract_conditions(cond_data: dict) -> list[dict]:
    return cond_data.get("data", {}).get("conditions", [])


def _extract_observations(obs_data: dict) -> list[dict]:
    return obs_data.get("data", {}).get("observations", [])


def _condition_matches(condition: dict, keyword: str) -> bool:
    cond_name = condition.get("condition", "").lower()
    codes = condition.get("codes", [])
    if keyword.lower() in cond_name:
        return True
    for c in codes:
        if keyword in c.get("code", "") or keyword.lower() in c.get("display", "").lower():
            return True
    return False


def _get_obs_value_by_loinc(observations: list[dict], loinc_code: str) -> tuple:
    """Find first observation matching LOINC code, return (value, unit, date)."""
    for obs in observations:
        if obs.get("loinc_code") == loinc_code:
            return obs.get("value"), obs.get("unit", ""), obs.get("effective_date", "")
    return None, "", ""


# =============================================================================
# I1: check_drug_allergy_conflicts
# =============================================================================

def check_drug_allergy_conflicts(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” DETERMINISTIC PYTHON RULES
    Cross-reference active medications against recorded allergies.
    Checks both exact matches and drug-class cross-reactivity.
    Uses: T2 (medications) + T7 (allergies)
    """
    meds_result = get_active_medications(tool_context)
    allergy_result = get_allergies(tool_context)

    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result['message']}")
    if allergy_result["status"] == "error":
        return _error_result(f"Cannot fetch allergies: {allergy_result['message']}")

    medications = meds_result["data"]["medications"]
    allergies = allergy_result["data"]["allergies"]

    if not medications:
        return {"status": "success", "alerts": [], "summary": "No active medications found."}
    if not allergies:
        return {"status": "success", "alerts": [], "summary": "No recorded allergies found."}

    alerts = []

    for allergy in allergies:
        allergen_name = allergy.get("allergen", "").lower()
        criticality = allergy.get("criticality", "unknown")
        reactions = allergy.get("reactions", [])
        reaction_desc = ", ".join(
            m for r in reactions for m in r.get("manifestations", [])
        ) or "unspecified reaction"

        for med in medications:
            med_name = med.get("medication", "")

            # Direct match
            if allergen_name and allergen_name in _normalize_drug_name(med_name):
                alerts.append({
                    "severity": "CRITICAL" if criticality == "high" else "HIGH",
                    "type": "direct_allergy_conflict",
                    "medication": med_name,
                    "allergen": allergy["allergen"],
                    "criticality": criticality,
                    "prior_reaction": reaction_desc,
                    "message": (
                        f"âš ï¸ ALLERGY CONFLICT: {med_name} matches recorded allergy to "
                        f"'{allergy['allergen']}' (prior reaction: {reaction_desc}). "
                        f"Criticality: {criticality.upper()}."
                    ),
                })
                continue

            # Cross-reactivity check
            for allergen_key, cross_reactive_drugs in ALLERGY_CROSS_REACTIVITY.items():
                if allergen_key in allergen_name:
                    for cr_drug in cross_reactive_drugs:
                        if _drug_matches(med_name, cr_drug):
                            alerts.append({
                                "severity": "HIGH",
                                "type": "cross_reactivity_conflict",
                                "medication": med_name,
                                "allergen": allergy["allergen"],
                                "cross_reactive_class": allergen_key,
                                "prior_reaction": reaction_desc,
                                "message": (
                                    f"âš ï¸ CROSS-REACTIVITY RISK: {med_name} may cross-react with "
                                    f"recorded '{allergy['allergen']}' allergy ({allergen_key} class). "
                                    f"Prior reaction: {reaction_desc}. Clinical review required."
                                ),
                            })

    # Deduplicate
    seen = set()
    unique_alerts = []
    for a in alerts:
        key = (a["medication"], a["allergen"])
        if key not in seen:
            seen.add(key)
            unique_alerts.append(a)

    critical_count = sum(1 for a in unique_alerts if a["severity"] == "CRITICAL")
    high_count = sum(1 for a in unique_alerts if a["severity"] == "HIGH")

    return {
        "status": "success",
        "alert_count": len(unique_alerts),
        "critical_count": critical_count,
        "high_count": high_count,
        "alerts": unique_alerts,
        "medications_checked": len(medications),
        "allergies_checked": len(allergies),
        "summary": (
            f"Found {len(unique_alerts)} allergy conflict(s): "
            f"{critical_count} CRITICAL, {high_count} HIGH."
            if unique_alerts else
            "No drug-allergy conflicts detected."
        ),
    }


# =============================================================================
# I2: screen_beers_criteria
# =============================================================================

def screen_beers_criteria(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python rules + LLM synthesis)
    Screen active medications against 2023 AGS Beers Criteria for patients â‰¥65.
    Uses: T1 (demographics) + T2 (medications)
    """
    demographics = get_patient_demographics(tool_context)
    meds_result = get_active_medications(tool_context)

    if demographics["status"] == "error":
        return _error_result(f"Cannot fetch demographics: {demographics['message']}")
    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result['message']}")

    age = demographics["data"].get("age", 0)
    patient_name = demographics["data"].get("full_name", "Patient")

    if age is None or age < 65:
        return {
            "status": "success",
            "applicable": False,
            "age": age,
            "summary": f"Beers Criteria not applicable â€” patient age {age} is under 65.",
            "flagged_medications": [],
        }

    medications = meds_result["data"]["medications"]
    flagged = []

    for med in medications:
        med_name = med.get("medication", "")
        norm_name = _normalize_drug_name(med_name)

        for drug_key, reason in BEERS_CRITERIA.items():
            if drug_key in norm_name:
                flagged.append({
                    "medication": med_name,
                    "beers_drug": drug_key,
                    "reason": reason,
                    "dose": med.get("dose", ""),
                    "frequency": med.get("frequency", ""),
                    "authored_on": med.get("authored_on", ""),
                    "message": f"ðŸ”´ BEERS FLAG: {med_name} â€” {reason}",
                })
                break  # One flag per medication

    # Sort by risk: conditions mentioning "falls" or "death" first
    high_priority_keywords = ["falls", "fatal", "mortality", "contraindicated", "avoid entirely"]
    flagged.sort(
        key=lambda x: any(kw in x["reason"].lower() for kw in high_priority_keywords),
        reverse=True,
    )

    return {
        "status": "success",
        "applicable": True,
        "patient_age": age,
        "medications_screened": len(medications),
        "beers_flagged_count": len(flagged),
        "flagged_medications": flagged,
        "summary": (
            f"Beers screening for {patient_name} (age {age}): "
            f"{len(flagged)} of {len(medications)} active medications flagged."
            if flagged else
            f"No Beers Criteria violations found in {len(medications)} active medications for patient age {age}."
        ),
    }


# =============================================================================
# I3: generate_patient_summary (Pure LLM — called last)
# =============================================================================

def generate_patient_summary(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence — PURE LLM SYNTHESIS
    Gathers all Layer 1 data (cached from prior tool calls) and returns
    a compact dict for the agent to synthesize into a clinical summary.
    Does NOT re-run safety tools — those should already have been called
    earlier in the conversation. Uses cached Layer 1 data only.
    Uses: T1 + T2 + T3 + T4 + T5 + T7
    """
    demographics = get_patient_demographics(tool_context)
    medications  = get_active_medications(tool_context)
    conditions   = get_active_conditions(tool_context)
    labs         = get_lab_results(tool_context)
    vitals       = get_vital_signs(tool_context)
    allergies    = get_allergies(tool_context)

    return {
        "status": "success",
        "data": {
            "patient_demographics": demographics.get("data", {}),
            "active_medications":   medications.get("data", {}),
            "active_conditions":    conditions.get("data", {}),
            "recent_labs":          labs.get("data", {}),
            "recent_vitals":        vitals.get("data", {}),
            "allergies":            allergies.get("data", {}),
        },
        "note": (
            "Compile all verified data AND any safety alerts already reported "
            "in this conversation into a structured clinical summary. "
            "Do not re-run safety tools — reference their earlier results."
        ),
    }


# =============================================================================
# I4: check_duplicate_therapy
# =============================================================================

def check_duplicate_therapy(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” DETERMINISTIC PYTHON RULES
    Detect two or more active drugs from the same pharmacological class.
    Uses: T2 (medications)
    """
    meds_result = get_active_medications(tool_context)
    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result['message']}")

    medications = meds_result["data"]["medications"]
    med_names = _extract_med_names(meds_result)

    duplicates = []

    for drug_class, class_members in DRUG_CLASS_MAP.items():
        matched_meds = []
        for med in medications:
            med_name = med.get("medication", "")
            for member in class_members:
                if _drug_matches(med_name, member):
                    matched_meds.append(med_name)
                    break

        if len(matched_meds) >= 2:
            # Determine severity
            high_risk_classes = {"Anticoagulants", "Antiplatelets", "Opioids",
                                 "SSRIs (Selective Serotonin Reuptake Inhibitors)"}
            severity = "HIGH" if drug_class in high_risk_classes else "MODERATE"

            duplicates.append({
                "severity": severity,
                "drug_class": drug_class,
                "duplicated_medications": matched_meds,
                "count": len(matched_meds),
                "message": (
                    f"âš ï¸ DUPLICATE THERAPY: {len(matched_meds)} active {drug_class} detected: "
                    f"{', '.join(matched_meds)}. Review intended therapeutic rationale."
                ),
            })

    return {
        "status": "success",
        "duplicate_classes_found": len(duplicates),
        "duplicates": duplicates,
        "medications_screened": len(medications),
        "summary": (
            f"Found {len(duplicates)} drug class duplication(s) requiring clinical review."
            if duplicates else
            "No duplicate therapy detected across active medications."
        ),
    }


# =============================================================================
# I5: check_drug_interactions
# =============================================================================

def check_drug_interactions(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python lookup table + LLM explanation)
    Screen active medication pairs against curated interaction database.
    Uses: T2 (medications)
    """
    meds_result = get_active_medications(tool_context)
    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result['message']}")

    medications = meds_result["data"]["medications"]
    if len(medications) < 2:
        return {"status": "success", "alerts": [], "summary": "Less than 2 medications â€” no interactions to check."}

    alerts = []

    for interaction in DRUG_INTERACTIONS:
        drug_a = interaction["drug_a"]
        drug_b = interaction["drug_b"]

        # Find matching medications for drug_a
        meds_with_a = [m["medication"] for m in medications if _drug_matches(m["medication"], drug_a)]
        meds_with_b = [m["medication"] for m in medications if _drug_matches(m["medication"], drug_b)]

        if meds_with_a and meds_with_b:
            for med_a in meds_with_a:
                for med_b in meds_with_b:
                    alerts.append({
                        "severity": interaction["severity"],
                        "drug_a": med_a,
                        "drug_b": med_b,
                        "mechanism": interaction["mechanism"],
                        "clinical_effect": interaction["effect"],
                        "message": (
                            f"{'ðŸ”´' if interaction['severity'] == 'CRITICAL' else 'ðŸŸ '} "
                            f"[{interaction['severity']}] {med_a} + {med_b}: "
                            f"{interaction['effect']} "
                            f"(Mechanism: {interaction['mechanism']})"
                        ),
                    })

    # Sort by severity
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}
    alerts.sort(key=lambda x: severity_order.get(x["severity"], 3))

    critical = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    high = sum(1 for a in alerts if a["severity"] == "HIGH")
    moderate = sum(1 for a in alerts if a["severity"] == "MODERATE")

    return {
        "status": "success",
        "alert_count": len(alerts),
        "critical_count": critical,
        "high_count": high,
        "moderate_count": moderate,
        "alerts": alerts,
        "medications_screened": len(medications),
        "summary": (
            f"Drug interaction screening: {len(alerts)} interaction(s) detected "
            f"({critical} CRITICAL, {high} HIGH, {moderate} MODERATE) "
            f"across {len(medications)} active medications."
            if alerts else
            f"No significant drug interactions detected in {len(medications)} active medications."
        ),
    }


# =============================================================================
# I6: screen_sepsis_risk (qSOFA)
# =============================================================================

def screen_sepsis_risk(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (deterministic qSOFA score + LLM context)
    Calculates qSOFA score from vitals. Requires suspected infection prerequisite.
    qSOFA criteria: SBP â‰¤ 100, RR â‰¥ 22, altered mentation.
    Score â‰¥ 2 = high sepsis suspicion.
    Uses: T3 (conditions for infection prereq + mentation) + T5 (vitals)
    """
    conditions_result = get_active_conditions(tool_context)
    vitals_result = get_vital_signs(tool_context)

    if conditions_result["status"] == "error":
        return _error_result(f"Cannot fetch conditions: {conditions_result['message']}")
    if vitals_result["status"] == "error":
        return _error_result(f"Cannot fetch vitals: {vitals_result['message']}")

    conditions = _extract_conditions(conditions_result)
    observations = _extract_observations(vitals_result)

    # --- Prerequisite: Check for suspected infection ---
    infection_found = False
    infection_conditions = []
    for cond in conditions:
        cond_text = cond.get("condition", "").lower()
        codes = cond.get("codes", [])
        # Check text
        infection_keywords = ["pneumonia", "sepsis", "infection", "uti", "cellulitis",
                              "bacteremia", "abscess", "peritonitis", "meningitis",
                              "pyelonephritis", "endocarditis"]
        if any(kw in cond_text for kw in infection_keywords):
            infection_found = True
            infection_conditions.append(cond.get("condition"))
            continue
        # Check codes
        for c in codes:
            code_val = c.get("code", "")
            if code_val in INFECTION_SNOMED_CODES:
                infection_found = True
                infection_conditions.append(cond.get("condition"))
                break
            if any(code_val.upper().startswith(pfx) for pfx in INFECTION_ICD_PREFIXES):
                infection_found = True
                infection_conditions.append(cond.get("condition"))
                break

    # --- qSOFA Criteria ---
    qsofa_criteria = []
    qsofa_score = 0
    details = {}

    # 1. Systolic BP â‰¤ 100 mmHg
    sbp_value = None
    for obs in observations:
        components = obs.get("components", [])
        for comp in components:
            if "systolic" in comp.get("name", "").lower():
                sbp_value = comp.get("value")
                break
        if sbp_value is None and "8480-6" == obs.get("loinc_code", ""):
            sbp_value = obs.get("value")
        if sbp_value is not None:
            break

    sbp_met = sbp_value is not None and float(sbp_value) <= 100
    details["sbp"] = {"value": sbp_value, "threshold": "â‰¤100 mmHg", "met": sbp_met}
    if sbp_met:
        qsofa_score += 1
        qsofa_criteria.append(f"SBP {sbp_value} mmHg (â‰¤100)")

    # 2. Respiratory rate â‰¥ 22
    rr_value = None
    for obs in observations:
        if obs.get("loinc_code") == "9279-1" or "respiratory" in obs.get("observation", "").lower():
            rr_value = obs.get("value")
            if rr_value is not None:
                break

    rr_met = rr_value is not None and float(rr_value) >= 22
    details["respiratory_rate"] = {"value": rr_value, "threshold": "â‰¥22/min", "met": rr_met}
    if rr_met:
        qsofa_score += 1
        qsofa_criteria.append(f"RR {rr_value}/min (â‰¥22)")

    # 3. Altered mentation â€” check active conditions
    mentation_met = False
    mentation_conditions = []
    for cond in conditions:
        cond_text = cond.get("condition", "").lower()
        codes = cond.get("codes", [])
        mentation_keywords = ["confusion", "delirium", "encephalopathy", "altered mental",
                              "agitation", "altered consciousness", "disorientation"]
        if any(kw in cond_text for kw in mentation_keywords):
            mentation_met = True
            mentation_conditions.append(cond.get("condition"))
            continue
        for c in codes:
            if c.get("code", "") in ALTERED_MENTATION_CODES:
                mentation_met = True
                mentation_conditions.append(cond.get("condition"))
                break

    details["altered_mentation"] = {"met": mentation_met, "conditions": mentation_conditions}
    if mentation_met:
        qsofa_score += 1
        qsofa_criteria.append(f"Altered mentation ({', '.join(mentation_conditions)})")

    # --- Risk stratification ---
    risk_level = "LOW"
    recommendation = "No sepsis alert â€” continue monitoring."
    if qsofa_score >= 2:
        risk_level = "HIGH"
        recommendation = ("qSOFA â‰¥ 2: High suspicion for sepsis or septic shock. "
                          "Recommend immediate blood cultures, lactate, IV access, "
                          "fluid resuscitation, and urgent antimicrobial therapy.")
    elif qsofa_score == 1:
        risk_level = "MODERATE"
        recommendation = "qSOFA = 1: Increased vigilance warranted. Monitor closely for deterioration."

    return {
        "status": "success",
        "qsofa_score": qsofa_score,
        "risk_level": risk_level,
        "infection_suspected": infection_found,
        "infection_conditions": list(set(infection_conditions)),
        "criteria_met": qsofa_criteria,
        "details": details,
        "recommendation": recommendation,
        "summary": (
            f"qSOFA Score: {qsofa_score}/3 â€” {risk_level} RISK. "
            f"Criteria met: {', '.join(qsofa_criteria) or 'None'}. "
            f"Infection basis: {', '.join(set(infection_conditions)) or 'Not identified in coded diagnoses'}."
        ),
    }


# =============================================================================
# I7: screen_polypharmacy
# =============================================================================

def screen_polypharmacy(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python count + LLM risk assessment)
    Flag polypharmacy (â‰¥5 meds) and high polypharmacy (â‰¥10 meds).
    Identifies highest-risk drug combinations from the list.
    Uses: T2 (medications)
    """
    meds_result = get_active_medications(tool_context)
    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result['message']}")

    medications = meds_result["data"]["medications"]
    count = len(medications)
    med_names = [m.get("medication", "") for m in medications]

    if count < 5:
        return {
            "status": "success",
            "polypharmacy_level": "NONE",
            "medication_count": count,
            "summary": f"No polypharmacy â€” patient has {count} active medications.",
        }

    level = "HIGH POLYPHARMACY" if count >= 10 else "POLYPHARMACY"

    # Identify high-risk drug categories present
    cns_meds = [n for n in med_names if any(_drug_matches(n, d)
                for d in ["lorazepam", "diazepam", "alprazolam", "clonazepam", "temazepam",
                           "zolpidem", "oxycodone", "hydrocodone", "morphine", "tramadol",
                           "amitriptyline", "quetiapine", "haloperidol"])]

    anticholinergic_count = sum(1 for n in med_names
                                 if any(_drug_matches(n, d) for d in BEERS_CRITERIA.keys()
                                        if "anticholinergic" in BEERS_CRITERIA[d].lower()
                                        or "anticholinergic" in BEERS_CRITERIA.get(d, "").lower()))

    anticoagulants = [n for n in med_names if any(_drug_matches(n, d)
                      for d in ["warfarin", "rivaroxaban", "apixaban", "dabigatran",
                                "enoxaparin", "heparin"])]

    risk_factors = []
    if cns_meds:
        risk_factors.append(f"CNS/sedating medications: {', '.join(cns_meds)}")
    if anticoagulants:
        risk_factors.append(f"Anticoagulants present (bleed risk): {', '.join(anticoagulants)}")
    if anticholinergic_count >= 2:
        risk_factors.append(f"Multiple anticholinergic medications ({anticholinergic_count}) â€” cumulative anticholinergic burden risk")

    return {
        "status": "success",
        "polypharmacy_level": level,
        "medication_count": count,
        "threshold_5_met": count >= 5,
        "threshold_10_met": count >= 10,
        "high_risk_factors": risk_factors,
        "all_medications": med_names,
        "summary": (
            f"{level}: {count} active medications. "
            f"High-risk factors: {'; '.join(risk_factors) or 'None identified beyond count'}. "
            "Medication reconciliation and deprescribing review recommended."
        ),
    }


# =============================================================================
# I8: assess_renal_safety (merged I3 + I5)
# =============================================================================

def assess_renal_safety(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (CKD-EPI + Python rule lookup + LLM)
    1. Calculates eGFR from most recent serum creatinine
    2. Stages CKD and detects un-coded (silent) CKD
    3. Flags active medications requiring dose adjustment or avoidance
    Uses: T1 (demographics) + T2 (medications) + T3 (conditions) + T4 (labs)
    """
    demographics = get_patient_demographics(tool_context)
    meds_result  = get_active_medications(tool_context)
    cond_result  = get_active_conditions(tool_context)
    labs_result  = get_lab_results(tool_context)

    for r, name in [(demographics, "demographics"), (meds_result, "medications"),
                    (labs_result, "labs")]:
        if r["status"] == "error":
            return _error_result(f"Cannot fetch {name}: {r.get('message', '')}")

    age = demographics["data"].get("age")
    sex = demographics["data"].get("gender", "male")
    observations = _extract_observations(labs_result)
    conditions = _extract_conditions(cond_result)
    medications = meds_result["data"]["medications"]

    # --- Find most recent creatinine ---
    creatinine_loinc = "2160-0"
    creatinine_value = None
    creatinine_date = ""
    for obs in observations:
        if obs.get("loinc_code") == creatinine_loinc:
            val = obs.get("value")
            if val is not None:
                try:
                    creatinine_value = float(val)
                    creatinine_date = obs.get("effective_date", "")
                    break
                except (ValueError, TypeError):
                    pass

    if creatinine_value is None or age is None:
        return {
            "status": "success",
            "egfr": None,
            "ckd_stage": None,
            "alerts": [],
            "summary": "Cannot calculate eGFR â€” creatinine or age not available in records.",
        }

    # --- Calculate eGFR + Stage ---
    egfr = calculate_egfr(creatinine_value, age, sex)
    ckd_stage, ckd_description = stage_ckd(egfr)

    # --- Silent CKD detection ---
    ckd_coded = any(
        any(kw in cond.get("condition", "").lower()
            for kw in ["chronic kidney", "ckd", "renal failure", "renal insufficiency"])
        for cond in conditions
    )
    silent_ckd = egfr < 60 and not ckd_coded

    # --- Medication safety check ---
    renal_alerts = []
    for drug_info in RENAL_DOSING:
        drug_sub = drug_info["drug"]
        threshold = drug_info["threshold"]
        action = drug_info["action"]
        note = drug_info["note"]

        if egfr < threshold:
            for med in medications:
                med_name = med.get("medication", "")
                if _drug_matches(med_name, drug_sub):
                    renal_alerts.append({
                        "severity": "CRITICAL" if action == "AVOID" else "HIGH",
                        "action": action,
                        "medication": med_name,
                        "egfr_threshold": threshold,
                        "patient_egfr": egfr,
                        "note": note,
                        "message": (
                            f"{'ðŸ”´ AVOID' if action == 'AVOID' else 'ðŸŸ  REDUCE DOSE'}: "
                            f"{med_name} â€” eGFR {egfr} mL/min/1.73mÂ² is below threshold "
                            f"of {threshold}. {note}"
                        ),
                    })

    renal_alerts.sort(key=lambda x: 0 if x["severity"] == "CRITICAL" else 1)

    return {
        "status": "success",
        "creatinine_mg_dl": creatinine_value,
        "creatinine_date": creatinine_date,
        "egfr": egfr,
        "ckd_stage": ckd_stage,
        "ckd_stage_description": ckd_description,
        "ckd_previously_coded": ckd_coded,
        "silent_ckd_detected": silent_ckd,
        "renal_drug_alerts": renal_alerts,
        "alert_count": len(renal_alerts),
        "summary": (
            f"eGFR: {egfr} mL/min/1.73mÂ² (CKD Stage {ckd_stage} â€” {ckd_description}). "
            f"{'âš ï¸ SILENT CKD: Renal impairment not coded in active conditions. ' if silent_ckd else ''}"
            f"Medication alerts: {len(renal_alerts)} drug(s) require renal dosing review."
            if renal_alerts else
            f"eGFR: {egfr} mL/min/1.73mÂ² (Stage {ckd_stage}). "
            f"{'Silent CKD detected â€” not coded in problem list. ' if silent_ckd else ''}"
            "No active medications require renal dose adjustments at this eGFR."
        ),
    }


# =============================================================================
# I9: assess_fall_risk
# =============================================================================

def assess_fall_risk(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python scoring + LLM recommendations)
    Score fall risk from age, high-risk medications, and diagnoses.
    Uses: T1 (demographics) + T2 (medications) + T3 (conditions)
    """
    demographics = get_patient_demographics(tool_context)
    meds_result  = get_active_medications(tool_context)
    cond_result  = get_active_conditions(tool_context)

    for r, name in [(demographics, "demographics"), (meds_result, "medications"), (cond_result, "conditions")]:
        if r["status"] == "error":
            return _error_result(f"Cannot fetch {name}: {r.get('message', '')}")

    age = demographics["data"].get("age", 0) or 0
    medications = meds_result["data"]["medications"]
    conditions = _extract_conditions(cond_result)

    score = 0
    risk_factors = []

    # --- Age scoring ---
    if age >= 85:
        score += 3
        risk_factors.append(f"Age â‰¥85 (+3 pts): {age} years old")
    elif age >= 75:
        score += 2
        risk_factors.append(f"Age 75â€“84 (+2 pts): {age} years old")
    elif age >= 65:
        score += 1
        risk_factors.append(f"Age 65â€“74 (+1 pt): {age} years old")

    # --- Medication scoring ---
    flagged_meds = []
    for med in medications:
        med_name = med.get("medication", "")
        for drug_key, pts in FALL_RISK_MEDICATIONS.items():
            if _drug_matches(med_name, drug_key):
                score += pts
                flagged_meds.append({"medication": med_name, "points": pts})
                break

    if flagged_meds:
        med_pts = sum(m["points"] for m in flagged_meds)
        risk_factors.append(
            f"High-risk medications (+{med_pts} pts): "
            + ", ".join(f"{m['medication']}(+{m['points']})" for m in flagged_meds)
        )

    # --- Condition scoring ---
    flagged_conditions = []
    for cond in conditions:
        cond_name = cond.get("condition", "")
        for kw, pts in FALL_RISK_CONDITIONS.items():
            if kw.lower() in cond_name.lower():
                score += pts
                flagged_conditions.append({"condition": cond_name, "points": pts})
                break

    if flagged_conditions:
        cond_pts = sum(c["points"] for c in flagged_conditions)
        risk_factors.append(
            f"Risk conditions (+{cond_pts} pts): "
            + ", ".join(f"{c['condition']}(+{c['points']})" for c in flagged_conditions)
        )

    # Cap score for display
    score = min(score, 20)

    # Risk tier
    if score >= 10:
        risk_level = "VERY HIGH"
        action = "Immediate fall prevention protocol. PT/OT referral. Medication deprescribing review."
    elif score >= 6:
        risk_level = "HIGH"
        action = "Fall prevention protocol. Review and reduce high-risk medications. Assess home safety."
    elif score >= 3:
        risk_level = "MODERATE"
        action = "Fall risk education. Review medications. Consider occupational therapy assessment."
    else:
        risk_level = "LOW"
        action = "Standard fall precautions. Reassess at next visit."

    return {
        "status": "success",
        "fall_risk_score": score,
        "risk_level": risk_level,
        "patient_age": age,
        "risk_factors": risk_factors,
        "flagged_medications": flagged_meds,
        "flagged_conditions": flagged_conditions,
        "recommended_action": action,
        "summary": (
            f"Fall Risk Assessment: {risk_level} (Score: {score}). "
            f"{len(flagged_meds)} high-risk medication(s) and {len(flagged_conditions)} "
            f"risk condition(s) identified. Action: {action}"
        ),
    }


# =============================================================================
# I10: optimize_hf_therapy
# =============================================================================

def optimize_hf_therapy(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python drug-class check + LLM)
    Verify HFrEF patients are on all 4 GDMT pillars (ACC/AHA 2022).
    Uses: T2 (medications) + T3 (conditions)
    """
    cond_result = get_active_conditions(tool_context)
    meds_result = get_active_medications(tool_context)

    for r, name in [(cond_result, "conditions"), (meds_result, "medications")]:
        if r["status"] == "error":
            return _error_result(f"Cannot fetch {name}: {r.get('message', '')}")

    conditions = _extract_conditions(cond_result)
    medications = meds_result["data"]["medications"]
    med_names = [m.get("medication", "") for m in medications]

    # Check if patient has heart failure
    hf_present = False
    hf_condition = None
    for cond in conditions:
        cond_name = cond.get("condition", "")
        if any(kw.lower() in cond_name.lower() for kw in
               ["heart failure", "hfref", "systolic heart failure", "cardiomyopathy"]):
            hf_present = True
            hf_condition = cond_name
            break
        for c in cond.get("codes", []):
            if c.get("code", "").startswith(("I50", "I42")):
                hf_present = True
                hf_condition = cond_name
                break

    if not hf_present:
        return {
            "status": "success",
            "applicable": False,
            "summary": "No heart failure diagnosis found in active conditions. Tool not applicable.",
        }

    # Check each pillar
    pillar_status = {}
    for pillar_name, pillar_info in HF_GDMT_PILLARS.items():
        found_drug = None
        for drug_key in pillar_info["drugs"]:
            for med_name in med_names:
                if _drug_matches(med_name, drug_key):
                    found_drug = med_name
                    break
            if found_drug:
                break
        pillar_status[pillar_name] = {
            "present": found_drug is not None,
            "medication_found": found_drug,
            "class": pillar_info["class"],
            "evidence": pillar_info["evidence"],
        }

    pillars_met = sum(1 for p in pillar_status.values() if p["present"])
    missing_pillars = [name for name, p in pillar_status.items() if not p["present"]]

    return {
        "status": "success",
        "applicable": True,
        "hf_diagnosis": hf_condition,
        "gdmt_pillars_met": pillars_met,
        "gdmt_pillars_total": 4,
        "pillar_status": pillar_status,
        "missing_pillars": missing_pillars,
        "summary": (
            f"HF GDMT Audit for '{hf_condition}': "
            f"{pillars_met}/4 guideline-directed therapy pillars in use. "
            f"Missing: {', '.join(missing_pillars) or 'None â€” fully optimized! âœ…'}."
            if missing_pillars else
            f"HF GDMT: All 4 pillars present for '{hf_condition}'. Therapy is guideline-optimized. âœ…"
        ),
    }


# =============================================================================
# I11: track_diabetic_care_gaps
# =============================================================================

def track_diabetic_care_gaps(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python HEDIS logic + LLM report)
    Audit diabetes patients against HEDIS 2024 quality measures.
    Uses: T2 (medications) + T3 (conditions) + T4 (labs)
    """
    cond_result = get_active_conditions(tool_context)
    labs_result = get_lab_results(tool_context)
    meds_result = get_active_medications(tool_context)
    vitals_result = get_vital_signs(tool_context)

    conditions = _extract_conditions(cond_result)
    observations = _extract_observations(labs_result)
    vital_obs = _extract_observations(vitals_result) if vitals_result["status"] == "success" else []
    medications = meds_result["data"]["medications"] if meds_result["status"] == "success" else []

    # Check if diabetic
    has_diabetes = any(
        any(kw.lower() in cond.get("condition", "").lower()
            for kw in ["diabetes", "diabetic", "type 2", "type 1", "t2dm", "t1dm"])
        or any(c.get("code", "").startswith(("E10", "E11", "E13"))
               for c in cond.get("codes", []))
        for cond in conditions
    )

    if not has_diabetes:
        return {
            "status": "success",
            "applicable": False,
            "summary": "No diabetes diagnosis found in active conditions.",
        }

    all_obs = observations + vital_obs
    gaps = []
    met = []

    for measure in DIABETES_HEDIS_MEASURES:
        measure_name = measure["measure"]

        if "loinc" in measure:
            # Lab/vital measure
            found_obs = None
            for loinc in measure["loinc"]:
                for obs in all_obs:
                    if obs.get("loinc_code") == loinc:
                        found_obs = obs
                        break
                if found_obs:
                    break

            if found_obs is None:
                gaps.append({
                    "measure": measure_name,
                    "status": "MISSING",
                    "last_value": None,
                    "last_date": None,
                    "target": measure["target"],
                    "message": f"âš ï¸ CARE GAP: {measure_name} â€” No result found in records.",
                })
            else:
                days_old = _days_since(found_obs.get("effective_date", ""))
                value = found_obs.get("value")
                is_stale = measure["max_age_days"] and days_old > measure["max_age_days"]

                if is_stale:
                    gaps.append({
                        "measure": measure_name,
                        "status": "OVERDUE",
                        "last_value": value,
                        "last_date": found_obs.get("effective_date", ""),
                        "days_overdue": days_old - (measure["max_age_days"] or 0),
                        "target": measure["target"],
                        "message": f"âš ï¸ OVERDUE: {measure_name} â€” Last result {days_old} days ago. {measure['target']}.",
                    })
                elif measure.get("poor_threshold") and value is not None:
                    try:
                        if float(value) >= measure["poor_threshold"]:
                            gaps.append({
                                "measure": measure_name,
                                "status": "POOR_CONTROL",
                                "last_value": f"{value} {found_obs.get('unit', '')}",
                                "last_date": found_obs.get("effective_date", ""),
                                "target": measure["target"],
                                "message": f"âš ï¸ POOR CONTROL: {measure_name} = {value} {found_obs.get('unit', '')} â€” Target: {measure['target']}.",
                            })
                        else:
                            met.append({"measure": measure_name, "value": f"{value} {found_obs.get('unit', '')}", "status": "MET"})
                    except (ValueError, TypeError):
                        met.append({"measure": measure_name, "value": str(value), "status": "MET"})
                else:
                    met.append({"measure": measure_name, "value": str(value) if value else "Present", "status": "MET"})

        elif "drugs" in measure:
            # Medication-based measure (statin therapy)
            has_drug = any(
                any(_drug_matches(m.get("medication", ""), d) for d in measure["drugs"])
                for m in medications
            )
            if has_drug:
                matched = next(
                    (m.get("medication") for m in medications
                     if any(_drug_matches(m.get("medication", ""), d) for d in measure["drugs"])),
                    "Unknown"
                )
                met.append({"measure": measure_name, "value": matched, "status": "MET"})
            else:
                gaps.append({
                    "measure": measure_name,
                    "status": "MISSING",
                    "message": f"âš ï¸ CARE GAP: {measure_name} â€” No statin prescription found. Recommended for CV risk reduction in diabetes.",
                })

    return {
        "status": "success",
        "applicable": True,
        "measures_checked": len(DIABETES_HEDIS_MEASURES),
        "gaps_count": len(gaps),
        "met_count": len(met),
        "care_gaps": gaps,
        "measures_met": met,
        "summary": (
            f"Diabetic care gap audit: {len(gaps)} gap(s) found, {len(met)} measure(s) met. "
            f"Gaps: {', '.join(g['measure'] for g in gaps) or 'None'}."
        ),
    }


# =============================================================================
# I12: screen_immunization_gaps
# =============================================================================

def screen_immunization_gaps(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence â€” HYBRID (Python schedule logic + LLM)
    Identify overdue vaccines per ACIP 2024 schedule.
    Cross-check allergy contraindications.
    Uses: T1 (demographics) + T7 (allergies) + T8 (immunizations) + T3 (conditions)
    """
    demographics = get_patient_demographics(tool_context)
    allergy_result = get_allergies(tool_context)
    imm_result = get_immunizations(tool_context)
    cond_result = get_active_conditions(tool_context)

    if demographics["status"] == "error":
        return _error_result(f"Cannot fetch demographics: {demographics['message']}")

    age = demographics["data"].get("age", 0) or 0
    immunizations = imm_result["data"]["immunizations"] if imm_result["status"] == "success" else []
    allergies = allergy_result["data"]["allergies"] if allergy_result["status"] == "success" else []
    conditions = _extract_conditions(cond_result) if cond_result["status"] == "success" else []

    # Check immunosuppression (for live vaccine contraindication)
    is_immunocompromised = any(
        any(kw in c.get("condition", "").lower()
            for kw in ["immunodeficiency", "hiv", "transplant", "chemotherapy",
                       "leukemia", "lymphoma"])
        for c in conditions
    )

    # Allergy check: egg allergy affects flu vaccine (though most can still receive)
    has_egg_allergy = any(
        "egg" in a.get("allergen", "").lower() for a in allergies
    )

    gaps = []
    current_vaccines = []

    # Build set of received vaccines
    for imm in immunizations:
        vac_name = imm.get("vaccine", "").lower()
        cvx = imm.get("cvx_code", "")
        occ_date = imm.get("occurrence_date", "")
        current_vaccines.append({
            "name": vac_name, "cvx": cvx,
            "days_ago": _days_since(occ_date),
            "date": occ_date,
        })

    for schedule in VACCINE_SCHEDULE:
        if not (schedule["min_age"] <= age <= schedule["max_age"]):
            continue

        vaccine_name = schedule["vaccine"]
        display_names = schedule["display_names"]
        max_days = schedule["max_age_days"]
        cvx_codes = schedule["cvx_codes"]

        # Find most recent matching vaccination
        best_match = None
        for cv in current_vaccines:
            name_match = any(dn in cv["name"] for dn in display_names)
            cvx_match = cv["cvx"] in cvx_codes
            if name_match or cvx_match:
                if best_match is None or cv["days_ago"] < best_match["days_ago"]:
                    best_match = cv

        is_due = False
        reason = ""
        if best_match is None:
            is_due = True
            reason = "No record of vaccination"
        elif max_days and best_match["days_ago"] > max_days:
            is_due = True
            reason = f"Last given {best_match['days_ago']} days ago (overdue â€” {max_days}-day interval)"

        if is_due:
            # Check contraindications
            contraindications = []
            if vaccine_name == "Influenza" and has_egg_allergy:
                contraindications.append("Egg allergy â€” use egg-free formulation (Flucelvax/Flublok) or administer under observation")

            gaps.append({
                "vaccine": vaccine_name,
                "reason": reason,
                "description": schedule["description"],
                "frequency": schedule["frequency"],
                "contraindications": contraindications,
                "message": (
                    f"ðŸ’‰ VACCINE DUE: {vaccine_name} â€” {reason}. "
                    f"{' âš ï¸ CONTRAINDICATIONS: ' + '; '.join(contraindications) if contraindications else ''}"
                ),
            })

    return {
        "status": "success",
        "patient_age": age,
        "vaccines_on_record": len(immunizations),
        "gaps_found": len(gaps),
        "immunization_gaps": gaps,
        "is_immunocompromised": is_immunocompromised,
        "summary": (
            f"Immunization review for age-{age} patient: "
            f"{len(gaps)} vaccine gap(s) found. "
            f"{'Patient may be immunocompromised â€” avoid live vaccines. ' if is_immunocompromised else ''}"
            f"Gaps: {', '.join(g['vaccine'] for g in gaps) or 'None â€” up to date!'}."
        ),
    }


# =============================================================================
# I13: compute_news2_score
# =============================================================================

def compute_news2_score(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence - DETERMINISTIC (NEWS2 scoring tables).
    Computes National Early Warning Score 2 from most recent vital signs.
    Guideline: Royal College of Physicians 2017.
    Uses: T5 (vital signs)
    """
    vitals_result = get_vital_signs(tool_context)
    if vitals_result["status"] == "error":
        return _error_result(f"Cannot fetch vitals: {vitals_result.get('message', '')}")

    observations = _extract_observations(vitals_result)
    if not observations:
        return {"status": "success", "news2_score": None,
                "summary": "Cannot compute NEWS2 - no vital signs available."}

    def _find_vital(loinc_codes, name_keywords):
        for obs in observations:
            if obs.get("loinc_code") in loinc_codes:
                return obs.get("value"), obs.get("effective_date", "")
            if any(kw in obs.get("observation", "").lower() for kw in name_keywords):
                return obs.get("value"), obs.get("effective_date", "")
            for comp in obs.get("components", []):
                if any(kw in comp.get("name", "").lower() for kw in name_keywords):
                    return comp.get("value"), obs.get("effective_date", "")
        return None, ""

    rr_val, _ = _find_vital(["9279-1"], ["respiratory rate", "resp rate"])
    spo2_val, _ = _find_vital(["2708-6", "59408-5"], ["oxygen saturation", "spo2"])
    hr_val, _ = _find_vital(["8867-4"], ["heart rate", "pulse"])
    temp_val, _ = _find_vital(["8310-5"], ["temperature", "body temp"])

    sbp_val = None
    for obs in observations:
        if obs.get("loinc_code") == "8480-6":
            sbp_val = obs.get("value")
            break
        for comp in obs.get("components", []):
            if "systolic" in comp.get("name", "").lower():
                sbp_val = comp.get("value")
                break
        if sbp_val is not None:
            break

    def _score_param(value, param_name):
        if value is None:
            return None, "Not available"
        try:
            v = float(value)
        except (ValueError, TypeError):
            return None, f"Invalid value: {value}"
        for rng in NEWS2_PARAMS.get(param_name, []):
            if rng["min"] <= v <= rng["max"]:
                return rng["score"], f"{v} -> {rng['score']} pts"
        return 0, f"{v} -> 0 pts (default)"

    scores = {}
    details = {}
    for param, val, label in [
        ("respiratory_rate", rr_val, "RR"),
        ("spo2_scale1", spo2_val, "SpO2"),
        ("systolic_bp", sbp_val, "SBP"),
        ("heart_rate", hr_val, "HR"),
        ("temperature", temp_val, "Temp"),
    ]:
        s, desc = _score_param(val, param)
        scores[param] = s
        details[label] = {"value": val, "score": s, "detail": desc}

    available_scores = [v for v in scores.values() if v is not None]
    if not available_scores:
        return {"status": "success", "news2_score": None,
                "summary": "Cannot compute NEWS2 - no scorable vital parameters found."}

    total = sum(available_scores)
    max_single = max(available_scores) if available_scores else 0

    if total >= 7:
        tier = "HIGH"
    elif total >= 5:
        tier = "MEDIUM"
    elif max_single >= 3:
        tier = "LOW_KEY"
    else:
        tier = "LOW"

    response_info = NEWS2_RESPONSE[tier]

    return {
        "status": "success",
        "news2_score": total,
        "risk_tier": tier,
        "parameters_scored": len(available_scores),
        "parameters_missing": 5 - len(available_scores),
        "parameter_details": details,
        "clinical_response": response_info,
        "guideline": "Royal College of Physicians NEWS2 (2017)",
        "summary": (
            f"NEWS2 Score: {total}/20 - {tier} risk. "
            f"Response: {response_info['response']}. "
            f"Monitoring: {response_info['frequency']}. "
            f"({len(available_scores)}/5 parameters scored)"
        ),
    }


# =============================================================================
# I14: screen_qt_prolongation_risk
# =============================================================================

def screen_qt_prolongation_risk(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence - DETERMINISTIC (CredibleMeds drug list + electrolyte check).
    Screens active medications for QT-prolonging risk and checks electrolytes.
    Guideline: CredibleMeds / AHA 2023.
    Uses: T2 (medications) + T4 (labs)
    """
    meds_result = get_active_medications(tool_context)
    labs_result = get_lab_results(tool_context)

    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result.get('message', '')}")

    medications = meds_result["data"]["medications"]
    observations = _extract_observations(labs_result) if labs_result.get("status") == "success" else []

    qt_flags = []
    for med in medications:
        med_name = med.get("medication", "")
        for qt_drug in QT_PROLONGING_DRUGS:
            if _drug_matches(med_name, qt_drug["drug"]):
                qt_flags.append({
                    "medication": med_name,
                    "risk_level": qt_drug["risk"],
                    "drug_class": qt_drug["class"],
                    "note": qt_drug["note"],
                    "dose": med.get("dose", ""),
                })
                break

    electrolyte_risks = []
    for elec_name, elec_info in QT_ELECTROLYTE_LOINC.items():
        for obs in observations:
            if obs.get("loinc_code") in elec_info["loinc"]:
                try:
                    val = float(obs.get("value", 0))
                    if val < elec_info["low_threshold"]:
                        electrolyte_risks.append({
                            "electrolyte": elec_name,
                            "value": val,
                            "threshold": elec_info["low_threshold"],
                            "unit": elec_info["unit"],
                        })
                except (ValueError, TypeError):
                    pass
                break

    known_count = sum(1 for f in qt_flags if f["risk_level"] == "KNOWN")
    multi_qt = len(qt_flags) >= 2
    has_electrolyte_risk = len(electrolyte_risks) > 0

    severity = "LOW"
    if known_count >= 2 or (known_count >= 1 and has_electrolyte_risk):
        severity = "CRITICAL"
    elif known_count >= 1 or multi_qt:
        severity = "HIGH"
    elif qt_flags:
        severity = "MODERATE"

    return {
        "status": "success",
        "severity": severity,
        "qt_drugs_found": len(qt_flags),
        "known_risk_count": known_count,
        "qt_medications": qt_flags,
        "electrolyte_risks": electrolyte_risks,
        "multiple_qt_drugs": multi_qt,
        "guideline": "CredibleMeds / AHA 2023",
        "summary": (
            f"QT Prolongation Risk: {severity}. "
            f"{len(qt_flags)} QT-prolonging drug(s) ({known_count} KNOWN risk). "
            + ("MULTIPLE QT drugs - additive Torsades risk! " if multi_qt else "")
            + ("Electrolyte abnormality amplifying risk. " if has_electrolyte_risk else "")
            + ("ECG monitoring recommended." if severity in ("CRITICAL", "HIGH") else "")
        ),
    }


# =============================================================================
# I15: screen_opioid_serotonin_risk
# =============================================================================

def screen_opioid_serotonin_risk(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence - DETERMINISTIC (FDA REMS 2023 + Hunter Criteria).
    Screens for opioid+CNS depressant combos (FDA black box) and
    serotonin syndrome risk from serotonergic drug combinations.
    Uses: T2 (medications)
    """
    meds_result = get_active_medications(tool_context)
    if meds_result["status"] == "error":
        return _error_result(f"Cannot fetch medications: {meds_result.get('message', '')}")

    medications = meds_result["data"]["medications"]
    med_names = [m.get("medication", "") for m in medications]

    alerts = []

    # Part 1: Opioid + CNS Depressant (FDA Black Box)
    active_opioids = []
    for med_name in med_names:
        for opioid in OPIOID_DRUGS:
            if _drug_matches(med_name, opioid):
                active_opioids.append(med_name)
                break

    active_cns_depressants = []
    for med_name in med_names:
        for cns_class, drugs in CNS_DEPRESSANT_DRUGS.items():
            for drug in drugs:
                if _drug_matches(med_name, drug):
                    active_cns_depressants.append({"medication": med_name, "class": cns_class})
                    break

    if active_opioids and active_cns_depressants:
        for opioid in active_opioids:
            for cns in active_cns_depressants:
                sev = "CRITICAL" if cns["class"] == "Benzodiazepine" else "HIGH"
                alerts.append({
                    "type": "opioid_cns_depression",
                    "severity": sev,
                    "drug_a": opioid,
                    "drug_b": cns["medication"],
                    "cns_class": cns["class"],
                    "guideline": "FDA REMS 2023 / FDA Black Box Warning",
                    "message": (
                        f"{sev}: {opioid} + {cns['medication']} ({cns['class']}) "
                        f"-- risk of fatal respiratory depression. FDA black box warning."
                    ),
                })

    # Part 2: Serotonin Syndrome Risk
    med_serotonin_cats = {}
    for med_name in med_names:
        for cat, drugs in SEROTONERGIC_DRUGS.items():
            for drug in drugs:
                if _drug_matches(med_name, drug):
                    if cat not in med_serotonin_cats:
                        med_serotonin_cats[cat] = []
                    med_serotonin_cats[cat].append(med_name)
                    break

    if len(med_serotonin_cats) >= 2:
        active_cats = list(med_serotonin_cats.keys())
        for combo in SEROTONIN_CRITICAL_COMBOS:
            if combo["cat_a"] in active_cats and combo["cat_b"] in active_cats:
                meds_a = med_serotonin_cats[combo["cat_a"]]
                meds_b = med_serotonin_cats[combo["cat_b"]]
                alerts.append({
                    "type": "serotonin_syndrome_risk",
                    "severity": combo["severity"],
                    "category_a": combo["cat_a"],
                    "category_b": combo["cat_b"],
                    "medications_a": meds_a,
                    "medications_b": meds_b,
                    "guideline": "Hunter Serotonin Toxicity Criteria",
                    "message": (
                        f"{combo['severity']}: Serotonin syndrome risk -- "
                        f"{', '.join(meds_a)} ({combo['cat_a']}) + "
                        f"{', '.join(meds_b)} ({combo['cat_b']}). "
                        f"{combo['note']}"
                    ),
                })

    alerts.sort(key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}.get(x["severity"], 3))

    critical = sum(1 for a in alerts if a["severity"] == "CRITICAL")
    high = sum(1 for a in alerts if a["severity"] == "HIGH")

    return {
        "status": "success",
        "alert_count": len(alerts),
        "critical_count": critical,
        "high_count": high,
        "active_opioids": active_opioids,
        "active_cns_depressants": [c["medication"] for c in active_cns_depressants],
        "serotonergic_categories": list(med_serotonin_cats.keys()),
        "alerts": alerts,
        "summary": (
            (
                f"Opioid/Serotonin Safety Screen: {len(alerts)} alert(s) "
                f"({critical} CRITICAL, {high} HIGH). "
                f"Opioids active: {len(active_opioids)}. "
                f"CNS depressants active: {len(active_cns_depressants)}. "
                f"Serotonergic categories: {len(med_serotonin_cats)}."
            ) if alerts else
            "No opioid-CNS or serotonin syndrome risks detected."
        ),
    }


# =============================================================================
# I16: compute_data_completeness
# =============================================================================

def compute_data_completeness(tool_context: ToolContext) -> dict:
    """
    Layer 2 Intelligence - DETERMINISTIC PYTHON.
    Audits what Layer 1 data is available for this patient and scores
    the confidence level of each safety screen based on data completeness.
    This explicitly flags when data is insufficient for reliable screening,
    strengthening the anti-hallucination guarantee.
    Uses: All Layer 1 tools (cached)
    """
    demographics = get_patient_demographics(tool_context)
    medications = get_active_medications(tool_context)
    conditions = get_active_conditions(tool_context)
    labs = get_lab_results(tool_context)
    vitals = get_vital_signs(tool_context)
    allergies = get_allergies(tool_context)

    def _has_data(result, key):
        return bool(result.get("data", {}).get(key, []))

    data_status = {
        "demographics": demographics.get("status") == "success" and demographics.get("data", {}).get("age") is not None,
        "medications": _has_data(medications, "medications"),
        "conditions": _has_data(conditions, "conditions"),
        "labs": _has_data(labs, "observations"),
        "vitals": _has_data(vitals, "observations"),
        "allergies": _has_data(allergies, "allergies"),
    }

    available = sum(1 for v in data_status.values() if v)
    total = len(data_status)

    tool_confidence = {
        "drug_allergy_conflicts":  "HIGH" if data_status["medications"] and data_status["allergies"] else "INSUFFICIENT",
        "beers_criteria":          "HIGH" if data_status["demographics"] and data_status["medications"] else "INSUFFICIENT",
        "drug_interactions":       "HIGH" if data_status["medications"] else "INSUFFICIENT",
        "polypharmacy":            "HIGH" if data_status["medications"] else "INSUFFICIENT",
        "duplicate_therapy":       "HIGH" if data_status["medications"] else "INSUFFICIENT",
        "renal_safety":            "HIGH" if data_status["demographics"] and data_status["medications"] and data_status["labs"] else ("MODERATE" if data_status["medications"] else "INSUFFICIENT"),
        "sepsis_risk":             "HIGH" if data_status["conditions"] and data_status["vitals"] else ("LOW" if data_status["vitals"] else "INSUFFICIENT"),
        "fall_risk":               "HIGH" if data_status["demographics"] and data_status["medications"] and data_status["conditions"] else ("MODERATE" if data_status["medications"] else "INSUFFICIENT"),
        "news2":                   "HIGH" if data_status["vitals"] else "INSUFFICIENT",
        "qt_prolongation":         "HIGH" if data_status["medications"] and data_status["labs"] else ("MODERATE" if data_status["medications"] else "INSUFFICIENT"),
        "opioid_serotonin":        "HIGH" if data_status["medications"] else "INSUFFICIENT",
    }

    high_confidence = sum(1 for v in tool_confidence.values() if v == "HIGH")
    insufficient = sum(1 for v in tool_confidence.values() if v == "INSUFFICIENT")

    overall = "HIGH" if available >= 5 else ("MODERATE" if available >= 3 else "LOW")

    return {
        "status": "success",
        "data_available": data_status,
        "data_completeness_score": f"{available}/{total}",
        "overall_confidence": overall,
        "tool_confidence": tool_confidence,
        "high_confidence_tools": high_confidence,
        "insufficient_data_tools": insufficient,
        "summary": (
            f"Data completeness: {available}/{total} categories available. "
            f"Overall confidence: {overall}. "
            f"{high_confidence} tools at HIGH confidence, "
            f"{insufficient} tools with INSUFFICIENT data. "
            f"Missing: {', '.join(k for k, v in data_status.items() if not v) or 'None'}."
        ),
    }
