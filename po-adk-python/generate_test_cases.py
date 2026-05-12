"""
generate_test_cases.py
─────────────────────
Generates 5 FHIR R4 transaction bundles that can be uploaded to
Prompt Opinion via their FHIR bundle import feature.

Format rules (learned from previous session):
  - Bundle type: "transaction"
  - All entries use POST method (not PUT)
  - Patient has no "id" field (server assigns)
  - All references use urn:uuid: format (server resolves)
  - No _sort params in any queries (PO doesn't support them)
"""

import json, uuid, os

def u():
    return str(uuid.uuid4())

def med(patient_ref, rxnorm, display, dose_mg, freq="Once daily", authored="2024-06-01"):
    uid = u()
    return {
        "fullUrl": f"urn:uuid:{uid}",
        "resource": {
            "resourceType": "MedicationRequest",
            "status": "active", "intent": "order",
            "subject": {"reference": patient_ref},
            "medicationCodeableConcept": {
                "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": rxnorm, "display": display}],
                "text": display
            },
            "authoredOn": authored,
            "dosageInstruction": [{"text": f"Take {dose_mg}mg {freq}", "timing": {"code": {"text": freq}},
                "doseAndRate": [{"doseQuantity": {"value": dose_mg, "unit": "mg"}}], "route": {"text": "Oral"}}]
        },
        "request": {"method": "POST", "url": "MedicationRequest"}
    }

def condition(patient_ref, snomed, display, onset="2023-01-15"):
    uid = u()
    return {
        "fullUrl": f"urn:uuid:{uid}",
        "resource": {
            "resourceType": "Condition",
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-clinical", "code": "active"}]},
            "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/condition-ver-status", "code": "confirmed"}]},
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": snomed, "display": display}], "text": display},
            "subject": {"reference": patient_ref},
            "onsetDateTime": onset
        },
        "request": {"method": "POST", "url": "Condition"}
    }

def obs_lab(patient_ref, loinc, display, value, unit, date="2025-04-20"):
    uid = u()
    return {
        "fullUrl": f"urn:uuid:{uid}",
        "resource": {
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "laboratory", "display": "Laboratory"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}], "text": display},
            "subject": {"reference": patient_ref},
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org"}
        },
        "request": {"method": "POST", "url": "Observation"}
    }

def obs_vital(patient_ref, loinc, display, value, unit, date="2025-04-20"):
    uid = u()
    return {
        "fullUrl": f"urn:uuid:{uid}",
        "resource": {
            "resourceType": "Observation",
            "status": "final",
            "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs", "display": "Vital Signs"}]}],
            "code": {"coding": [{"system": "http://loinc.org", "code": loinc, "display": display}], "text": display},
            "subject": {"reference": patient_ref},
            "effectiveDateTime": date,
            "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org"}
        },
        "request": {"method": "POST", "url": "Observation"}
    }

def allergy(patient_ref, snomed, display, category="medication"):
    uid = u()
    return {
        "fullUrl": f"urn:uuid:{uid}",
        "resource": {
            "resourceType": "AllergyIntolerance",
            "clinicalStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical", "code": "active"}]},
            "verificationStatus": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/allergyintolerance-verification", "code": "confirmed"}]},
            "type": "allergy", "category": [category],
            "code": {"coding": [{"system": "http://snomed.info/sct", "code": snomed, "display": display}], "text": display},
            "patient": {"reference": patient_ref}
        },
        "request": {"method": "POST", "url": "AllergyIntolerance"}
    }

def patient(given, family, gender, birth_date, city="Boston", state="MA"):
    uid = u()
    pat_ref = f"urn:uuid:{uid}"
    return pat_ref, {
        "fullUrl": pat_ref,
        "resource": {
            "resourceType": "Patient",
            "name": [{"use": "official", "given": [given], "family": family}],
            "gender": gender, "birthDate": birth_date, "active": True,
            "address": [{"use": "home", "city": city, "state": state}]
        },
        "request": {"method": "POST", "url": "Patient"}
    }

def bundle(entries):
    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 1: Robert Chen — 76yo Complex Elderly (Triggers EVERYTHING)
# ═══════════════════════════════════════════════════════════════════════════════
def case1():
    p_ref, p = patient("Robert", "Chen", "male", "1948-07-22")
    entries = [p]
    # 7 medications — polypharmacy, Beers, interactions
    entries.append(med(p_ref, "197884", "Lisinopril 20 MG Oral Tablet", 20))
    entries.append(med(p_ref, "198222", "Spironolactone 25 MG Oral Tablet", 25))
    entries.append(med(p_ref, "855332", "Warfarin 5 MG Oral Tablet", 5))
    entries.append(med(p_ref, "212033", "Aspirin 81 MG Oral Tablet", 81))
    entries.append(med(p_ref, "861007", "Metformin 1000 MG Oral Tablet", 1000))
    entries.append(med(p_ref, "197589", "Diazepam 5 MG Oral Tablet", 5))           # Beers flag!
    entries.append(med(p_ref, "310798", "Amoxicillin 500 MG Oral Tablet", 500))    # Allergy conflict!
    # Conditions
    entries.append(condition(p_ref, "44054006", "Type 2 diabetes mellitus"))
    entries.append(condition(p_ref, "84114007", "Heart failure"))
    entries.append(condition(p_ref, "38341003", "Hypertensive disorder"))
    entries.append(condition(p_ref, "709044004", "Chronic kidney disease stage 3"))
    # Allergy — penicillin (conflicts with amoxicillin)
    entries.append(allergy(p_ref, "91936005", "Allergy to penicillin"))
    # Labs
    entries.append(obs_lab(p_ref, "2160-0", "Creatinine", 1.9, "mg/dL"))
    entries.append(obs_lab(p_ref, "33914-3", "eGFR", 32, "mL/min/1.73m2"))
    entries.append(obs_lab(p_ref, "4548-4", "Hemoglobin A1c", 8.4, "%"))
    entries.append(obs_lab(p_ref, "2823-3", "Potassium", 5.3, "mmol/L"))
    # Vitals
    entries.append(obs_vital(p_ref, "8480-6", "Systolic blood pressure", 154, "mmHg"))
    entries.append(obs_vital(p_ref, "8462-4", "Diastolic blood pressure", 92, "mmHg"))
    entries.append(obs_vital(p_ref, "8867-4", "Heart rate", 88, "/min"))
    entries.append(obs_vital(p_ref, "9279-1", "Respiratory rate", 18, "/min"))
    entries.append(obs_vital(p_ref, "2708-6", "Oxygen saturation", 95, "%"))
    entries.append(obs_vital(p_ref, "8310-5", "Body temperature", 36.8, "Cel"))
    return bundle(entries)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 2: Sarah Mitchell — 28yo Serotonin Syndrome Risk
# ═══════════════════════════════════════════════════════════════════════════════
def case2():
    p_ref, p = patient("Sarah", "Mitchell", "female", "1998-02-14", "Portland", "OR")
    entries = [p]
    # Serotonergic drug combo — serotonin syndrome risk
    entries.append(med(p_ref, "312938", "Sertraline 100 MG Oral Tablet", 100))
    entries.append(med(p_ref, "856845", "Tramadol 50 MG Oral Tablet", 50))          # SS risk with SSRI!
    entries.append(med(p_ref, "835564", "Sumatriptan 50 MG Oral Tablet", 50))       # SS risk with SSRI!
    # Conditions
    entries.append(condition(p_ref, "35489007", "Depressive disorder"))
    entries.append(condition(p_ref, "37796009", "Migraine"))
    # Vitals
    entries.append(obs_vital(p_ref, "8480-6", "Systolic blood pressure", 118, "mmHg"))
    entries.append(obs_vital(p_ref, "8867-4", "Heart rate", 72, "/min"))
    entries.append(obs_vital(p_ref, "8310-5", "Body temperature", 36.6, "Cel"))
    return bundle(entries)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 3: Dorothy Williams — 82yo Massive Polypharmacy + Fall Risk
# ═══════════════════════════════════════════════════════════════════════════════
def case3():
    p_ref, p = patient("Dorothy", "Williams", "female", "1943-11-08", "Tampa", "FL")
    entries = [p]
    # 10 medications — HIGH polypharmacy + multiple Beers flags
    entries.append(med(p_ref, "197884", "Lisinopril 10 MG Oral Tablet", 10))
    entries.append(med(p_ref, "310798", "Amoxicillin 250 MG Oral Tablet", 250))
    entries.append(med(p_ref, "197361", "Amlodipine 5 MG Oral Tablet", 5))
    entries.append(med(p_ref, "316672", "Simvastatin 20 MG Oral Tablet", 20))
    entries.append(med(p_ref, "316049", "Atorvastatin 40 MG Oral Tablet", 40))     # Duplicate statin!
    entries.append(med(p_ref, "197589", "Diazepam 5 MG Oral Tablet", 5))           # Beers!
    entries.append(med(p_ref, "197900", "Lorazepam 1 MG Oral Tablet", 1))          # Beers + duplicate benzo!
    entries.append(med(p_ref, "197381", "Amitriptyline 25 MG Oral Tablet", 25))    # Beers (anticholinergic)!
    entries.append(med(p_ref, "198240", "Ranitidine 150 MG Oral Tablet", 150))
    entries.append(med(p_ref, "312961", "Oxycodone 5 MG Oral Tablet", 5))          # Opioid + benzo = black box!
    # Conditions
    entries.append(condition(p_ref, "38341003", "Hypertensive disorder"))
    entries.append(condition(p_ref, "161891005", "Back pain"))
    entries.append(condition(p_ref, "35489007", "Depressive disorder"))
    entries.append(condition(p_ref, "129839007", "Osteoporosis"))
    # Allergy
    entries.append(allergy(p_ref, "91936005", "Allergy to penicillin"))
    # Vitals
    entries.append(obs_vital(p_ref, "8480-6", "Systolic blood pressure", 142, "mmHg"))
    entries.append(obs_vital(p_ref, "8867-4", "Heart rate", 76, "/min"))
    entries.append(obs_vital(p_ref, "8310-5", "Body temperature", 36.5, "Cel"))
    return bundle(entries)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 4: James Park — 35yo Healthy Adult (Negative Space Demo)
# ═══════════════════════════════════════════════════════════════════════════════
def case4():
    p_ref, p = patient("James", "Park", "male", "1991-05-20", "Seattle", "WA")
    entries = [p]
    # 1 benign medication
    entries.append(med(p_ref, "316077", "Cetirizine 10 MG Oral Tablet", 10))
    # No conditions, no allergies
    # Normal vitals
    entries.append(obs_vital(p_ref, "8480-6", "Systolic blood pressure", 120, "mmHg"))
    entries.append(obs_vital(p_ref, "8462-4", "Diastolic blood pressure", 78, "mmHg"))
    entries.append(obs_vital(p_ref, "8867-4", "Heart rate", 68, "/min"))
    entries.append(obs_vital(p_ref, "9279-1", "Respiratory rate", 14, "/min"))
    entries.append(obs_vital(p_ref, "2708-6", "Oxygen saturation", 99, "%"))
    entries.append(obs_vital(p_ref, "8310-5", "Body temperature", 36.7, "Cel"))
    # Normal labs
    entries.append(obs_lab(p_ref, "2160-0", "Creatinine", 0.9, "mg/dL"))
    entries.append(obs_lab(p_ref, "33914-3", "eGFR", 105, "mL/min/1.73m2"))
    return bundle(entries)


# ═══════════════════════════════════════════════════════════════════════════════
# CASE 5: Maria Garcia — 58yo Uncontrolled Diabetes (HEDIS Gaps)
# ═══════════════════════════════════════════════════════════════════════════════
def case5():
    p_ref, p = patient("Maria", "Garcia", "female", "1968-03-25", "Phoenix", "AZ")
    entries = [p]
    # 4 medications
    entries.append(med(p_ref, "861007", "Metformin 1000 MG Oral Tablet", 1000))
    entries.append(med(p_ref, "197884", "Lisinopril 20 MG Oral Tablet", 20))
    entries.append(med(p_ref, "197361", "Amlodipine 5 MG Oral Tablet", 5))
    entries.append(med(p_ref, "860975", "Glipizide 10 MG Oral Tablet", 10))        # No statin = HEDIS gap
    # Conditions
    entries.append(condition(p_ref, "44054006", "Type 2 diabetes mellitus"))
    entries.append(condition(p_ref, "38341003", "Hypertensive disorder"))
    # Labs — uncontrolled diabetes
    entries.append(obs_lab(p_ref, "4548-4", "Hemoglobin A1c", 9.1, "%"))           # Way above 7% target
    entries.append(obs_lab(p_ref, "2160-0", "Creatinine", 1.1, "mg/dL"))
    entries.append(obs_lab(p_ref, "33914-3", "eGFR", 68, "mL/min/1.73m2"))
    entries.append(obs_lab(p_ref, "14959-1", "Microalbumin/Creatinine ratio", 45, "mg/g"))  # Early nephropathy
    # Vitals — BP above target
    entries.append(obs_vital(p_ref, "8480-6", "Systolic blood pressure", 148, "mmHg"))
    entries.append(obs_vital(p_ref, "8462-4", "Diastolic blood pressure", 94, "mmHg"))
    entries.append(obs_vital(p_ref, "8867-4", "Heart rate", 82, "/min"))
    return bundle(entries)


# ═══════════════════════════════════════════════════════════════════════════════
# Generate all cases
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    cases = {
        "case1_robert_chen_complex_elderly.json": case1(),
        "case2_sarah_mitchell_serotonin_risk.json": case2(),
        "case3_dorothy_williams_polypharmacy.json": case3(),
        "case4_james_park_healthy_adult.json": case4(),
        "case5_maria_garcia_diabetes_gaps.json": case5(),
    }

    out_dir = os.path.join(os.path.dirname(__file__), "test_cases")
    os.makedirs(out_dir, exist_ok=True)

    for filename, data in cases.items():
        path = os.path.join(out_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        n = len(data["entry"])
        print(f"OK {filename} -- {n} entries")

    print(f"\nAll 5 cases written to {out_dir}")
