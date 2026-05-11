"""
FHIR tools — Layer 1 Truth Tools for ClinicalGuard.

These tools fetch VERIFIED data directly from the FHIR R4 server.
The LLM cannot hallucinate these values — they are raw facts.

Architecture:
  - 10 named tools (T1–T10) covering every clinical data dimension
  - All use httpx (already a transitive dep of google-adk)
  - All inject FHIR credentials from session state (via fhir_hook)
  - All return {"status": "success", "data": {...}} on success
  - All return {"status": "error", "message": "..."} on failure

Adding new FHIR tools:
  1. Write a new function in this file.
  2. Add tool_context: ToolContext as the LAST parameter.
  3. Start with ctx = _get_fhir_context(tool_context)
  4. Export from shared/tools/__init__.py.
  5. Add to tools=[...] in healthcare_agent/agent.py.
"""

import logging
from datetime import datetime, date
from typing import Optional, Any

import httpx
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

_FHIR_TIMEOUT = 15  # seconds


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS — shared by all tools
# ═══════════════════════════════════════════════════════════════════════════════

# Session-level FHIR cache key prefix — avoids redundant HTTP calls when
# multiple Layer 2 tools fetch the same Layer 1 data in a single turn.
_CACHE_PREFIX = "_fhir_cache_"


def _cache_key(name: str) -> str:
    return f"{_CACHE_PREFIX}{name}"


def _get_cached(tool_context: ToolContext, name: str) -> Optional[dict]:
    """Return cached FHIR result if available."""
    return tool_context.state.get(_cache_key(name))


def _set_cached(tool_context: ToolContext, name: str, result: dict) -> None:
    """Store a FHIR result in session cache."""
    tool_context.state[_cache_key(name)] = result


def _get_prefetched_bundle(tool_context: ToolContext, prefetch_key: str) -> Optional[dict]:
    """
    Return the raw FHIR bundle from parallel prefetch (if available).
    The prefetch runs in the before_model_callback and stores raw bundles
    under '_fhir_prefetch_<key>' in session state. This avoids the HTTP
    round-trip when the LLM calls the tool.
    """
    return tool_context.state.get(f"_fhir_prefetch_{prefetch_key}")


def _get_fhir_context(tool_context: ToolContext) -> dict:
    """Read FHIR credentials from session state (injected by fhir_hook)."""
    return {
        "fhir_url":   tool_context.state.get("fhir_url", "").rstrip("/"),
        "fhir_token": tool_context.state.get("fhir_token", ""),
        "patient_id": tool_context.state.get("patient_id", ""),
    }


def _check_context(ctx: dict) -> Optional[dict]:
    """Return an error dict if any credential is missing, else None."""
    missing = [k for k in ("fhir_url", "fhir_token", "patient_id") if not ctx[k]]
    if missing:
        return _error_result(
            f"FHIR context missing: {', '.join(missing)}. "
            "Ensure the caller includes 'fhir-context' in the A2A metadata."
        )
    return None


def _fhir_get(fhir_url: str, token: str, path: str,
              params: Optional[dict] = None) -> dict:
    """Authenticated FHIR GET. Returns parsed JSON. Never raises."""
    try:
        resp = httpx.get(
            f"{fhir_url}/{path}",
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/fhir+json",
            },
            timeout=_FHIR_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        return {"entry": [], "_error": f"HTTP {e.response.status_code}: {e.response.text[:200]}"}
    except Exception as e:
        return {"entry": [], "_error": f"FHIR connection failed: {e}"}


def _extract_entries(bundle: dict) -> list[dict]:
    """Pull resource dicts from a FHIR Bundle."""
    return [e["resource"] for e in bundle.get("entry", []) if e.get("resource")]


def _error_result(msg: str) -> dict:
    return {"status": "error", "message": msg}


def _safe_get(data: Any, *keys, default=None) -> Any:
    """Navigate nested dict/list safely."""
    cur = data
    for key in keys:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list) and isinstance(key, int):
            cur = cur[key] if key < len(cur) else None
        else:
            return default
        if cur is None:
            return default
    return cur


def _coding_display(codings: list, default: str = "Unknown") -> str:
    """Return best display text from a list of FHIR Coding objects."""
    if not codings:
        return default
    for c in codings:
        if c.get("display"):
            return c["display"]
    for c in codings:
        if c.get("code"):
            return c["code"]
    return default


def _concept_text(concept: Optional[dict], default: str = "Unknown") -> str:
    """Return text from a FHIR CodeableConcept."""
    if not concept:
        return default
    if concept.get("text"):
        return concept["text"]
    return _coding_display(concept.get("coding", []), default)


def _quantity_value(qty: Optional[dict]) -> tuple:
    """Return (value, unit) from a FHIR Quantity."""
    if not qty:
        return None, ""
    return qty.get("value"), qty.get("unit", qty.get("code", ""))


def _calculate_age(birth_date_str: str) -> Optional[int]:
    """Age in years from a YYYY-MM-DD string."""
    try:
        bd = datetime.strptime(birth_date_str[:10], "%Y-%m-%d").date()
        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# T1: get_patient_demographics
# ═══════════════════════════════════════════════════════════════════════════════

def get_patient_demographics(tool_context: ToolContext) -> dict:
    """
    Fetches verified patient demographic data from the FHIR server.
    Returns name, date of birth, age, gender, address, phone, email,
    marital status, and active status. No arguments required.
    """
    cached = _get_cached(tool_context, "demographics")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    resource = _fhir_get(ctx["fhir_url"], ctx["fhir_token"],
                         f"Patient/{ctx['patient_id']}")
    if resource.get("_error"):
        return _error_result(resource["_error"])

    names = resource.get("name", [])
    official = next((n for n in names if n.get("use") == "official"),
                    names[0] if names else {})
    full_name = f"{' '.join(official.get('given', []))} {official.get('family', '')}".strip()

    birth_date = resource.get("birthDate", "")
    age = _calculate_age(birth_date) if birth_date else None

    addresses = resource.get("address", [])
    addr = next((a for a in addresses if a.get("use") == "home"),
                addresses[0] if addresses else {})
    address = ", ".join(p for p in [
        " ".join(addr.get("line", [])),
        addr.get("city", ""), addr.get("state", ""),
        addr.get("postalCode", ""), addr.get("country", ""),
    ] if p)

    telecoms = resource.get("telecom", [])
    phone = next((t["value"] for t in telecoms if t.get("system") == "phone"), None)
    email = next((t["value"] for t in telecoms if t.get("system") == "email"), None)

    result = {
        "status": "success",
        "data": {
            "patient_id": ctx["patient_id"],
            "full_name": full_name or "Unknown",
            "birth_date": birth_date,
            "age": age,
            "gender": resource.get("gender", "unknown"),
            "active": resource.get("active", True),
            "address": address,
            "phone": phone,
            "email": email,
            "marital_status": _concept_text(resource.get("maritalStatus"), "unknown"),
        },
    }
    _set_cached(tool_context, "demographics", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# T2: get_active_medications
# ═══════════════════════════════════════════════════════════════════════════════

def get_active_medications(tool_context: ToolContext) -> dict:
    """
    Retrieves all active medication prescriptions from the FHIR server.
    Returns drug names, doses, frequency, route, prescriber, and date.
    No arguments required.
    """
    cached = _get_cached(tool_context, "medications")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, "medications")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"], "MedicationRequest", {
            "patient": ctx["patient_id"], "status": "active",
            "_count": "100",
        })
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    medications = []
    for res in _extract_entries(bundle):
        med_concept = res.get("medicationCodeableConcept")
        if med_concept:
            med_name = _concept_text(med_concept)
        else:
            med_name = _safe_get(res, "medicationReference", "display",
                                 default="Unknown medication")

        dosage_list = res.get("dosageInstruction", [])
        dosage = dosage_list[0] if dosage_list else {}
        dose_qty = _safe_get(dosage, "doseAndRate", 0, "doseQuantity")
        dose_val, dose_unit = _quantity_value(dose_qty)
        dose_str = f"{dose_val} {dose_unit}".strip() if dose_val else ""
        timing = _safe_get(dosage, "timing", "code", "text", default="")
        route = _concept_text(dosage.get("route"), "")
        instructions = dosage.get("text", "")

        medications.append({
            "medication": med_name,
            "status": res.get("status", "active"),
            "dose": dose_str or instructions,
            "frequency": timing,
            "route": route,
            "authored_on": res.get("authoredOn", ""),
            "requester": _safe_get(res, "requester", "display", default=""),
        })

    result = {
        "status": "success",
        "data": {"medications": medications, "count": len(medications)},
    }
    if not medications:
        result["note"] = "No active medications on record — verify medication list with patient."
    _set_cached(tool_context, "medications", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# T3: get_active_conditions
# ═══════════════════════════════════════════════════════════════════════════════

def get_active_conditions(tool_context: ToolContext) -> dict:
    """
    Retrieves active conditions and diagnoses from the FHIR server.
    Returns condition names, SNOMED/ICD codes, severity, onset dates.
    No arguments required.
    """
    cached = _get_cached(tool_context, "conditions")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, "conditions")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"], "Condition", {
            "patient": ctx["patient_id"], "clinical-status": "active", "_count": "100",
        })
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    conditions = []
    for res in _extract_entries(bundle):
        code_obj = res.get("code", {})
        codings = code_obj.get("coding", [])
        conditions.append({
            "condition": _concept_text(code_obj, "Unknown condition"),
            "codes": [{"system": c.get("system", ""), "code": c.get("code", ""),
                       "display": c.get("display", "")} for c in codings],
            "clinical_status": _concept_text(res.get("clinicalStatus"), "active"),
            "severity": _concept_text(res.get("severity"), ""),
            "onset": res.get("onsetDateTime", res.get("onsetString", "")),
            "recorded_date": res.get("recordedDate", ""),
        })

    result = {
        "status": "success",
        "data": {"conditions": conditions, "count": len(conditions)},
    }
    if not conditions:
        result["note"] = "No active diagnoses on record — clinical history review recommended."
    _set_cached(tool_context, "conditions", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# T4/T5/T6: Observation wrappers (lab, vitals, social history)
# ═══════════════════════════════════════════════════════════════════════════════

def _get_observations(tool_context: ToolContext, category: str,
                      count: int = 50) -> dict:
    """Shared implementation for Observation-based tools."""
    cached = _get_cached(tool_context, f"obs_{category}")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, f"obs_{category}")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"], "Observation", {
            "patient": ctx["patient_id"], "category": category,
            "_count": str(count),
        })
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    observations = []
    for res in _extract_entries(bundle):
        obs_name = _concept_text(res.get("code"), "Unknown observation")
        codings = res.get("code", {}).get("coding", [])
        loinc_code = next((c["code"] for c in codings
                           if "loinc" in c.get("system", "").lower()), None)

        value, unit = None, ""
        if "valueQuantity" in res:
            value, unit = _quantity_value(res["valueQuantity"])
        elif "valueString" in res:
            value = res["valueString"]
        elif "valueCodeableConcept" in res:
            value = _concept_text(res["valueCodeableConcept"])

        components = []
        for comp in res.get("component", []):
            cname = _concept_text(comp.get("code"), "")
            cval, cunit = _quantity_value(comp.get("valueQuantity"))
            if cval is not None:
                components.append({"name": cname, "value": cval, "unit": cunit})

        interp = ""
        interp_list = res.get("interpretation", [])
        if interp_list and isinstance(interp_list, list):
            interp = _concept_text(interp_list[0], "")

        ref_range_str = ""
        for rr in res.get("referenceRange", []):
            low_val, low_unit = _quantity_value(rr.get("low"))
            high_val, _ = _quantity_value(rr.get("high"))
            if low_val is not None and high_val is not None:
                ref_range_str = f"{low_val}-{high_val} {low_unit}".strip()
                break

        observations.append({
            "observation": obs_name,
            "loinc_code": loinc_code,
            "value": value,
            "unit": unit,
            "components": components,
            "effective_date": res.get("effectiveDateTime",
                                     _safe_get(res, "effectivePeriod", "start", default="")),
            "status": res.get("status", ""),
            "interpretation": interp,
            "reference_range": ref_range_str,
        })

    result = {
        "status": "success",
        "data": {"observations": observations, "count": len(observations),
                 "category": category},
    }
    if not observations:
        cat_labels = {"laboratory": "lab results", "vital-signs": "vital signs", "social-history": "social history"}
        result["note"] = f"No recent {cat_labels.get(category, category)} available — baseline assessment may be needed."
    _set_cached(tool_context, f"obs_{category}", result)
    return result


def get_lab_results(tool_context: ToolContext) -> dict:
    """Fetches recent laboratory results (CBC, CMP, HbA1c, lipids, etc.) from the FHIR server. No arguments required."""
    return _get_observations(tool_context, "laboratory", count=50)


def get_vital_signs(tool_context: ToolContext) -> dict:
    """Fetches recent vital signs (BP, HR, RR, Temp, SpO2, weight) from the FHIR server. No arguments required."""
    return _get_observations(tool_context, "vital-signs", count=30)


def get_social_history(tool_context: ToolContext) -> dict:
    """Fetches social history observations (smoking, alcohol, etc.) from the FHIR server. No arguments required."""
    return _get_observations(tool_context, "social-history", count=20)


# ═══════════════════════════════════════════════════════════════════════════════
# T7: get_allergies
# ═══════════════════════════════════════════════════════════════════════════════

def get_allergies(tool_context: ToolContext) -> dict:
    """
    Fetches AllergyIntolerance resources from the FHIR server.
    Returns allergens, type, category, criticality, reactions.
    No arguments required.
    """
    cached = _get_cached(tool_context, "allergies")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, "allergies")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"],
                           "AllergyIntolerance",
                           {"patient": ctx["patient_id"], "_count": "50"})
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    allergies = []
    for res in _extract_entries(bundle):
        reactions = []
        for rxn in res.get("reaction", []):
            manifestations = [_concept_text(m) for m in rxn.get("manifestation", [])]
            reactions.append({
                "manifestations": manifestations,
                "severity": rxn.get("severity", ""),
            })

        allergies.append({
            "allergen": _concept_text(res.get("code"), "Unknown allergen"),
            "type": res.get("type", ""),
            "category": res.get("category", []),
            "criticality": res.get("criticality", ""),
            "clinical_status": _concept_text(res.get("clinicalStatus"), "active"),
            "reactions": reactions,
            "recorded_date": res.get("recordedDate", ""),
        })

    result = {
        "status": "success",
        "data": {"allergies": allergies, "count": len(allergies)},
    }
    if not allergies:
        result["note"] = "No allergies documented — confirm NKDA (No Known Drug Allergies) with patient."
    _set_cached(tool_context, "allergies", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# T8: get_immunizations
# ═══════════════════════════════════════════════════════════════════════════════

def get_immunizations(tool_context: ToolContext) -> dict:
    """
    Fetches Immunization records from the FHIR server.
    Returns vaccine names, CVX codes, dates, dose numbers, status.
    No arguments required.
    """
    cached = _get_cached(tool_context, "immunizations")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, "immunizations")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"], "Immunization", {
            "patient": ctx["patient_id"], "_count": "100",
        })
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    immunizations = []
    for res in _extract_entries(bundle):
        codings = res.get("vaccineCode", {}).get("coding", [])
        cvx = next((c["code"] for c in codings
                     if "cvx" in c.get("system", "").lower()), None)
        immunizations.append({
            "vaccine": _concept_text(res.get("vaccineCode"), "Unknown vaccine"),
            "cvx_code": cvx,
            "status": res.get("status", "completed"),
            "occurrence_date": res.get("occurrenceDateTime",
                                       res.get("occurrenceString", "")),
            "dose_number": _safe_get(res, "protocolApplied", 0,
                                     "doseNumberPositiveInt"),
        })

    result = {
        "status": "success",
        "data": {"immunizations": immunizations, "count": len(immunizations)},
    }
    if not immunizations:
        result["note"] = "No immunization records found — vaccination history may be incomplete."
    _set_cached(tool_context, "immunizations", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# T9: get_procedures
# ═══════════════════════════════════════════════════════════════════════════════

def get_procedures(tool_context: ToolContext) -> dict:
    """
    Fetches recent Procedure resources from the FHIR server.
    Returns procedure names, codes, dates, status.
    No arguments required.
    """
    cached = _get_cached(tool_context, "procedures")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, "procedures")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"], "Procedure", {
            "patient": ctx["patient_id"], "_count": "50",
        })
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    procedures = []
    for res in _extract_entries(bundle):
        code_obj = res.get("code", {})
        codings = code_obj.get("coding", [])
        procedures.append({
            "procedure": _concept_text(code_obj, "Unknown procedure"),
            "codes": [{"system": c.get("system", ""), "code": c.get("code", ""),
                       "display": c.get("display", "")} for c in codings],
            "status": res.get("status", ""),
            "performed_date": res.get("performedDateTime",
                                      _safe_get(res, "performedPeriod", "start",
                                                default="")),
        })

    result = {
        "status": "success",
        "data": {"procedures": procedures, "count": len(procedures)},
    }
    if not procedures:
        result["note"] = "No procedures on record."
    _set_cached(tool_context, "procedures", result)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# T10: get_encounters
# ═══════════════════════════════════════════════════════════════════════════════

def get_encounters(tool_context: ToolContext) -> dict:
    """
    Fetches recent Encounter resources from the FHIR server.
    Returns visit types, class, dates, reasons, disposition.
    No arguments required.
    """
    cached = _get_cached(tool_context, "encounters")
    if cached:
        return cached
    ctx = _get_fhir_context(tool_context)
    err = _check_context(ctx)
    if err:
        return err

    bundle = _get_prefetched_bundle(tool_context, "encounters")
    if bundle is None:
        bundle = _fhir_get(ctx["fhir_url"], ctx["fhir_token"], "Encounter", {
            "patient": ctx["patient_id"], "_count": "20",
        })
    if bundle.get("_error"):
        return _error_result(bundle["_error"])

    encounters = []
    for res in _extract_entries(bundle):
        types = res.get("type", [])
        visit_type = _concept_text(types[0], "Unknown") if types else "Unknown"
        enc_class = _safe_get(res, "class", "display",
                              default=_safe_get(res, "class", "code", default=""))
        reason_codes = [_concept_text(r) for r in res.get("reasonCode", [])]
        period = res.get("period", {})
        disposition = _concept_text(
            _safe_get(res, "hospitalization", "dischargeDisposition"), "")

        encounters.append({
            "encounter_id": res.get("id", ""),
            "visit_type": visit_type,
            "class": enc_class,
            "status": res.get("status", ""),
            "start_date": period.get("start", ""),
            "end_date": period.get("end", ""),
            "reasons": reason_codes,
            "disposition": disposition,
        })

    result = {
        "status": "success",
        "data": {"encounters": encounters, "count": len(encounters)},
    }
    if not encounters:
        result["note"] = "No encounter history available."
    _set_cached(tool_context, "encounters", result)
    return result
