"""
clinical_rules.py
-----------------
All hardcoded clinical knowledge bases used by Layer 2 intelligence tools.
These are DETERMINISTIC Python structures — no LLM hallucination possible here.

Sources:
  - 2023 AGS Beers Criteria
  - FDA drug interaction guidance
  - CKD-EPI 2021 (race-free) equation
  - ACIP immunization schedule 2024
  - ACC/AHA HF guidelines 2022
  - HEDIS 2024 diabetes measures
"""

import math


# =============================================================================
# 1. BEERS CRITERIA (AGS 2023)
#    Format: {lowercase_drug_substring: reason_for_flagging}
# =============================================================================

BEERS_CRITERIA: dict[str, str] = {
    # Anticholinergics — CNS effects, falls, cognitive impairment
    "diphenhydramine":   "Anticholinergic: high CNS risk (sedation, delirium, falls) in elderly",
    "hydroxyzine":       "Anticholinergic: sedation, falls, cognitive impairment",
    "promethazine":      "Anticholinergic: high CNS toxicity risk in elderly",
    "amitriptyline":     "Tricyclic antidepressant: strong anticholinergic + cardiac conduction risk",
    "imipramine":        "Tricyclic antidepressant: strong anticholinergic + cardiac conduction risk",
    "clomipramine":      "Tricyclic antidepressant: strong anticholinergic + cardiac conduction risk",
    "doxepin":           "Tricyclic antidepressant: anticholinergic (avoid doses >6mg)",
    "nortriptyline":     "Tricyclic antidepressant: anticholinergic, safer than amitriptyline but still avoid",
    "paroxetine":        "SSRI with high anticholinergic burden — prefer sertraline/citalopram",
    "oxybutynin":        "Anticholinergic: strong CNS penetration, falls risk, confusion",
    "tolterodine":       "Anticholinergic: falls and cognitive risk",
    "solifenacin":       "Anticholinergic: falls and cognitive risk",
    "darifenacin":       "Anticholinergic: falls and cognitive risk",
    "trospium":          "Anticholinergic: falls and cognitive risk",
    "benztropine":       "Anticholinergic: avoid in elderly — may worsen cognition",
    "trihexyphenidyl":   "Anticholinergic: avoid in elderly",
    "scopolamine":       "Anticholinergic: high toxicity risk",
    "meclizine":         "Anticholinergic: sedation + falls in elderly",
    "cyclobenzaprine":   "Muscle relaxant with anticholinergic effects: sedation, falls, confusion",

    # Benzodiazepines and Z-drugs — falls, fractures, cognitive impairment
    "lorazepam":         "Benzodiazepine: falls, fractures, cognitive impairment, dependence",
    "diazepam":          "Benzodiazepine: long half-life → excess sedation, falls in elderly",
    "alprazolam":        "Benzodiazepine: falls, fractures, cognitive impairment",
    "clonazepam":        "Benzodiazepine: falls, fractures, cognitive impairment",
    "temazepam":         "Benzodiazepine: falls, fractures, cognitive impairment",
    "oxazepam":          "Benzodiazepine: falls, fractures, cognitive impairment",
    "chlordiazepoxide":  "Benzodiazepine: long-acting, excess sedation",
    "flurazepam":        "Benzodiazepine: very long half-life, extreme fall risk",
    "triazolam":         "Benzodiazepine: falls, cognitive impairment",
    "zolpidem":          "Z-drug: falls, fractures, hallucinations, cognitive impairment",
    "zaleplon":          "Z-drug: falls risk in elderly",
    "eszopiclone":       "Z-drug: falls risk, next-day drowsiness",

    # Cardiovascular
    "digoxin":           "Narrow therapeutic index: dose-dependent toxicity, avoid >0.125mg/day in elderly",
    "nifedipine":        "Immediate-release form: hypotension, reflex tachycardia — use extended release only",
    "doxazosin":         "Alpha-blocker: orthostatic hypotension, falls — avoid for hypertension",
    "prazosin":          "Alpha-blocker: orthostatic hypotension, falls",
    "terazosin":         "Alpha-blocker: orthostatic hypotension, falls — avoid for hypertension",
    "amiodarone":        "Thyroid toxicity, pulmonary toxicity, QT prolongation; safer alternatives exist",
    "dronedarone":       "Avoid in permanent atrial fibrillation — increases mortality",
    "spironolactone":    "Avoid >25mg/day in HF: hyperkalemia risk in elderly",
    "methyldopa":        "Antihypertensive: orthostatic hypotension, CNS effects — avoid first-line",
    "reserpine":         "Depression risk, sedation, orthostatic hypotension",

    # Pain & NSAIDs
    "ibuprofen":         "NSAID: GI bleed, renal impairment, fluid retention, cardiovascular risk in elderly",
    "naproxen":          "NSAID: GI bleed, renal impairment — higher GI risk than ibuprofen",
    "indomethacin":      "NSAID: highest CNS toxicity among NSAIDs — headache, confusion, avoid entirely in elderly",
    "meloxicam":         "NSAID: GI bleed and renal risks (less than indomethacin but still significant)",
    "diclofenac":        "NSAID: cardiovascular and GI risks",
    "ketorolac":         "NSAID: GI ulcer/bleed, renal failure — avoid in elderly",
    "celecoxib":         "COX-2 inhibitor: cardiovascular risk, renal impairment",
    "meperidine":        "Opioid: normeperidine metabolite causes seizures, confusion — avoid entirely",
    "pentazocine":       "Opioid agonist-antagonist: CNS adverse effects higher than standard opioids",

    # Muscle relaxants
    "methocarbamol":     "Muscle relaxant: poorly tolerated in elderly (sedation, anticholinergic, falls)",
    "carisoprodol":      "Muscle relaxant: CNS depression, abuse potential — avoid in elderly",
    "chlorzoxazone":     "Muscle relaxant: poorly tolerated in elderly",
    "metaxalone":        "Muscle relaxant: poorly tolerated in elderly",

    # Endocrine
    "glyburide":         "Sulfonylurea: prolonged hypoglycemia risk — prefer glipizide or glimepiride",
    "glibenclamide":     "Sulfonylurea: prolonged hypoglycemia risk — avoid in elderly",
    "megestrol":         "Progestogen: VTE, adrenal suppression — minimal benefit for anorexia in elderly",

    # GI
    "metoclopramide":    "Tardive dyskinesia risk with prolonged use — avoid unless for gastroparesis",
    "mineral oil":       "Aspiration pneumonia risk, fat-soluble vitamin malabsorption",

    # Psychiatric
    "haloperidol":       "Antipsychotic: EPS, QT prolongation, mortality risk in dementia — use minimum dose",
    "quetiapine":        "Antipsychotic: used off-label for sleep/anxiety — falls, QT prolongation risk",
    "olanzapine":        "Antipsychotic: metabolic side effects, sedation, falls",
    "risperidone":       "Antipsychotic: EPS, falls, mortality risk in dementia",
    "chlorpromazine":    "First-gen antipsychotic: strong anticholinergic + orthostatic hypotension",
    "thioridazine":      "First-gen antipsychotic: QT prolongation, avoid entirely",

    # Other
    "nitrofurantoin":    "Pulmonary/hepatic toxicity with long-term use; ineffective when eGFR <30",
    "trimethoprim-sulfamethoxazole": "Hyperkalemia risk + raises creatinine artificially in elderly",
}


# =============================================================================
# 2. DRUG-DRUG INTERACTIONS
#    Format: list of {drug_a, drug_b, severity, mechanism, clinical_effect}
#    Match by substring on lowercased medication display names.
# =============================================================================

DRUG_INTERACTIONS: list[dict] = [
    # === BLEEDING RISKS ===
    {"drug_a": "warfarin",     "drug_b": "ibuprofen",       "severity": "CRITICAL",  "mechanism": "Anticoagulant + NSAID antiplatelet",           "effect": "Major GI/intracranial bleed risk"},
    {"drug_a": "warfarin",     "drug_b": "naproxen",        "severity": "CRITICAL",  "mechanism": "Anticoagulant + NSAID antiplatelet",           "effect": "Major GI/intracranial bleed risk"},
    {"drug_a": "warfarin",     "drug_b": "aspirin",         "severity": "HIGH",      "mechanism": "Anticoagulant + antiplatelet",                 "effect": "Bleeding risk — only acceptable if explicitly intended (e.g. ACS)"},
    {"drug_a": "warfarin",     "drug_b": "fluconazole",     "severity": "CRITICAL",  "mechanism": "CYP2C9 inhibition → warfarin accumulation",    "effect": "Severe INR elevation, bleeding risk"},
    {"drug_a": "warfarin",     "drug_b": "amiodarone",      "severity": "CRITICAL",  "mechanism": "CYP2C9/CYP3A4 inhibition",                    "effect": "INR elevation, major bleed risk"},
    {"drug_a": "warfarin",     "drug_b": "metronidazole",   "severity": "HIGH",      "mechanism": "CYP2C9 inhibition",                           "effect": "INR elevation, bleeding risk"},
    {"drug_a": "warfarin",     "drug_b": "trimethoprim",    "severity": "HIGH",      "mechanism": "CYP2C9 inhibition + anticoagulant synergy",   "effect": "INR elevation"},
    {"drug_a": "warfarin",     "drug_b": "rifampin",        "severity": "CRITICAL",  "mechanism": "CYP450 induction → warfarin metabolism↑",     "effect": "Sub-therapeutic INR, thrombosis risk"},
    {"drug_a": "warfarin",     "drug_b": "carbamazepine",   "severity": "HIGH",      "mechanism": "CYP450 induction",                            "effect": "Reduced warfarin efficacy"},
    {"drug_a": "sertraline",   "drug_b": "aspirin",         "severity": "MODERATE",  "mechanism": "SSRI antiplatelet effect + aspirin",          "effect": "GI bleed risk — consider PPI co-prescribing"},
    {"drug_a": "fluoxetine",   "drug_b": "aspirin",         "severity": "MODERATE",  "mechanism": "SSRI antiplatelet effect + aspirin",          "effect": "GI bleed risk"},

    # === SEROTONIN SYNDROME ===
    {"drug_a": "sertraline",   "drug_b": "tramadol",        "severity": "CRITICAL",  "mechanism": "Dual serotonin elevation",                    "effect": "Serotonin syndrome: agitation, hyperthermia, rigidity, seizures"},
    {"drug_a": "fluoxetine",   "drug_b": "tramadol",        "severity": "CRITICAL",  "mechanism": "Dual serotonin elevation + CYP2D6 inhibition","effect": "Serotonin syndrome"},
    {"drug_a": "paroxetine",   "drug_b": "tramadol",        "severity": "CRITICAL",  "mechanism": "Dual serotonin elevation + CYP2D6 inhibition","effect": "Serotonin syndrome"},
    {"drug_a": "linezolid",    "drug_b": "sertraline",      "severity": "CRITICAL",  "mechanism": "MAO inhibition + SSRI",                       "effect": "Serotonin syndrome — contraindicated"},
    {"drug_a": "linezolid",    "drug_b": "fluoxetine",      "severity": "CRITICAL",  "mechanism": "MAO inhibition + SSRI",                       "effect": "Serotonin syndrome — contraindicated"},
    {"drug_a": "linezolid",    "drug_b": "venlafaxine",     "severity": "CRITICAL",  "mechanism": "MAO inhibition + SNRI",                       "effect": "Serotonin syndrome — contraindicated"},

    # === RESPIRATORY DEPRESSION ===
    {"drug_a": "oxycodone",    "drug_b": "lorazepam",       "severity": "CRITICAL",  "mechanism": "CNS/respiratory depression synergy",          "effect": "Potentially fatal respiratory depression — FDA black box"},
    {"drug_a": "hydrocodone",  "drug_b": "lorazepam",       "severity": "CRITICAL",  "mechanism": "CNS/respiratory depression synergy",          "effect": "Potentially fatal respiratory depression"},
    {"drug_a": "morphine",     "drug_b": "diazepam",        "severity": "CRITICAL",  "mechanism": "CNS/respiratory depression synergy",          "effect": "Potentially fatal respiratory depression"},
    {"drug_a": "oxycodone",    "drug_b": "alprazolam",      "severity": "CRITICAL",  "mechanism": "CNS/respiratory depression synergy",          "effect": "Potentially fatal respiratory depression"},
    {"drug_a": "oxycodone",    "drug_b": "gabapentin",      "severity": "HIGH",      "mechanism": "CNS/respiratory depression synergy",          "effect": "Respiratory depression, sedation — review necessity"},
    {"drug_a": "morphine",     "drug_b": "gabapentin",      "severity": "HIGH",      "mechanism": "CNS/respiratory depression synergy",          "effect": "Respiratory depression"},

    # === CARDIAC — BRADYCARDIA / HEART BLOCK ===
    {"drug_a": "metoprolol",   "drug_b": "verapamil",       "severity": "CRITICAL",  "mechanism": "Additive AV node depression",                 "effect": "Complete heart block, bradycardia"},
    {"drug_a": "atenolol",     "drug_b": "diltiazem",       "severity": "HIGH",      "mechanism": "Additive AV node depression",                 "effect": "Bradycardia, heart block"},
    {"drug_a": "metoprolol",   "drug_b": "diltiazem",       "severity": "HIGH",      "mechanism": "Additive AV node depression",                 "effect": "Bradycardia, heart block"},
    {"drug_a": "digoxin",      "drug_b": "amiodarone",      "severity": "CRITICAL",  "mechanism": "P-gp/renal inhibition → digoxin toxicity",    "effect": "Digoxin toxicity: bradycardia, AV block, arrhythmia"},
    {"drug_a": "digoxin",      "drug_b": "verapamil",       "severity": "CRITICAL",  "mechanism": "P-gp inhibition + additive AV depression",    "effect": "Digoxin toxicity + bradycardia"},
    {"drug_a": "digoxin",      "drug_b": "clarithromycin",  "severity": "HIGH",      "mechanism": "P-gp inhibition → digoxin accumulation",     "effect": "Digoxin toxicity"},

    # === QT PROLONGATION (Torsades risk) ===
    {"drug_a": "amiodarone",   "drug_b": "azithromycin",    "severity": "CRITICAL",  "mechanism": "Additive QT prolongation",                    "effect": "Torsades de pointes, ventricular fibrillation"},
    {"drug_a": "haloperidol",  "drug_b": "clarithromycin",  "severity": "CRITICAL",  "mechanism": "Additive QT prolongation",                    "effect": "Torsades de pointes"},
    {"drug_a": "methadone",    "drug_b": "fluconazole",     "severity": "CRITICAL",  "mechanism": "CYP3A4 inhibition + additive QT",             "effect": "Torsades de pointes"},
    {"drug_a": "citalopram",   "drug_b": "azithromycin",    "severity": "HIGH",      "mechanism": "Additive QT prolongation",                    "effect": "QT prolongation, torsades risk"},
    {"drug_a": "ondansetron",  "drug_b": "amiodarone",      "severity": "HIGH",      "mechanism": "Additive QT prolongation",                    "effect": "QT prolongation, arrhythmia"},
    {"drug_a": "ciprofloxacin","drug_b": "amiodarone",      "severity": "HIGH",      "mechanism": "Additive QT prolongation",                    "effect": "QT prolongation"},

    # === MYOPATHY / RHABDOMYOLYSIS ===
    {"drug_a": "simvastatin",  "drug_b": "clarithromycin",  "severity": "HIGH",      "mechanism": "CYP3A4 inhibition → statin accumulation",    "effect": "Rhabdomyolysis — hold simvastatin during clarithromycin course"},
    {"drug_a": "atorvastatin", "drug_b": "clarithromycin",  "severity": "HIGH",      "mechanism": "CYP3A4 inhibition",                          "effect": "Myopathy risk — monitor or switch statin temporarily"},
    {"drug_a": "simvastatin",  "drug_b": "amiodarone",      "severity": "HIGH",      "mechanism": "CYP3A4 inhibition",                          "effect": "Rhabdomyolysis — cap simvastatin at 20mg"},
    {"drug_a": "simvastatin",  "drug_b": "amlodipine",      "severity": "MODERATE",  "mechanism": "CYP3A4 partial inhibition",                  "effect": "Myopathy — cap simvastatin at 20mg with amlodipine"},

    # === HYPERKALEMIA ===
    {"drug_a": "lisinopril",   "drug_b": "spironolactone",  "severity": "HIGH",      "mechanism": "Dual RAAS K+ retention",                     "effect": "Hyperkalemia — acceptable in HF with monitoring; dangerous in CKD"},
    {"drug_a": "ramipril",     "drug_b": "spironolactone",  "severity": "HIGH",      "mechanism": "Dual RAAS K+ retention",                     "effect": "Hyperkalemia"},
    {"drug_a": "lisinopril",   "drug_b": "losartan",        "severity": "HIGH",      "mechanism": "Dual RAAS blockade (ACEi + ARB)",            "effect": "Hyperkalemia, acute kidney injury — avoid combination"},
    {"drug_a": "enalapril",    "drug_b": "valsartan",       "severity": "HIGH",      "mechanism": "Dual RAAS blockade",                         "effect": "Hyperkalemia, AKI — avoid in most cases"},
    {"drug_a": "spironolactone","drug_b": "trimethoprim",   "severity": "HIGH",      "mechanism": "Both block distal K+ excretion",             "effect": "Hyperkalemia"},

    # === RENAL DAMAGE ===
    {"drug_a": "lisinopril",   "drug_b": "ibuprofen",       "severity": "HIGH",      "mechanism": "NSAID blunts prostaglandin → renal vasoconstriction + ACEi efferent dilation → AKI",  "effect": "Acute kidney injury ('triple whammy' if also diuretic)"},
    {"drug_a": "methotrexate", "drug_b": "ibuprofen",       "severity": "CRITICAL",  "mechanism": "NSAID reduces methotrexate renal clearance", "effect": "Methotrexate toxicity: mucositis, myelosuppression, nephrotoxicity"},
    {"drug_a": "methotrexate", "drug_b": "trimethoprim",    "severity": "CRITICAL",  "mechanism": "Additive folate antagonism",                  "effect": "Severe myelosuppression"},

    # === HYPOGLYCEMIA ===
    {"drug_a": "glipizide",    "drug_b": "fluconazole",     "severity": "HIGH",      "mechanism": "CYP2C9 inhibition → sulfonylurea accumulation","effect": "Prolonged severe hypoglycemia"},
    {"drug_a": "glyburide",    "drug_b": "fluconazole",     "severity": "CRITICAL",  "mechanism": "CYP2C9 inhibition → prolonged sulfonylurea",  "effect": "Severe hypoglycemia"},
    {"drug_a": "metformin",    "drug_b": "contrast",        "severity": "HIGH",      "mechanism": "Contrast-induced AKI → metformin accumulation","effect": "Lactic acidosis — hold metformin before contrast procedures"},

    # === NITRATE + PDE5 ===
    {"drug_a": "sildenafil",   "drug_b": "nitroglycerin",   "severity": "CRITICAL",  "mechanism": "Synergistic cGMP-mediated vasodilation",       "effect": "Severe refractory hypotension — contraindicated"},
    {"drug_a": "tadalafil",    "drug_b": "nitroglycerin",   "severity": "CRITICAL",  "mechanism": "Synergistic vasodilation",                     "effect": "Severe refractory hypotension — contraindicated"},
    {"drug_a": "sildenafil",   "drug_b": "isosorbide",      "severity": "CRITICAL",  "mechanism": "Synergistic cGMP-mediated vasodilation",       "effect": "Severe hypotension — contraindicated"},

    # === DRUG TOXICITY ===
    {"drug_a": "allopurinol",  "drug_b": "azathioprine",    "severity": "CRITICAL",  "mechanism": "Xanthine oxidase inhibition → 6-MP accumulation","effect": "Severe myelosuppression — reduce azathioprine by 75%"},
    {"drug_a": "allopurinol",  "drug_b": "mercaptopurine",  "severity": "CRITICAL",  "mechanism": "Xanthine oxidase inhibition",                  "effect": "Myelosuppression — contraindicated or major dose reduction"},
    {"drug_a": "colchicine",   "drug_b": "clarithromycin",  "severity": "CRITICAL",  "mechanism": "P-gp + CYP3A4 inhibition → colchicine toxicity","effect": "Potentially fatal colchicine toxicity"},
    {"drug_a": "ciprofloxacin","drug_b": "theophylline",    "severity": "HIGH",      "mechanism": "CYP1A2 inhibition → theophylline accumulation","effect": "Theophylline toxicity: seizures, arrhythmia"},
    {"drug_a": "fluoxetine",   "drug_b": "tamoxifen",       "severity": "HIGH",      "mechanism": "CYP2D6 inhibition → reduced tamoxifen → endoxifen conversion","effect": "Reduced breast cancer treatment efficacy"},
    {"drug_a": "clopidogrel",  "drug_b": "omeprazole",      "severity": "MODERATE",  "mechanism": "CYP2C19 inhibition → reduced clopidogrel activation","effect": "Reduced antiplatelet efficacy — use pantoprazole instead"},
    {"drug_a": "metronidazole","drug_b": "alcohol",         "severity": "HIGH",      "mechanism": "Aldehyde dehydrogenase inhibition",            "effect": "Disulfiram-like reaction: flushing, vomiting, tachycardia"},
    {"drug_a": "fluconazole",  "drug_b": "cyclosporine",    "severity": "HIGH",      "mechanism": "CYP3A4 inhibition → calcineurin inhibitor toxicity","effect": "Nephrotoxicity, immunosuppression toxicity"},

    # === TENDON/MUSCULOSKELETAL ===
    {"drug_a": "ciprofloxacin","drug_b": "prednisone",      "severity": "HIGH",      "mechanism": "Fluoroquinolone + corticosteroid → tendon damage","effect": "Tendon rupture risk (Achilles especially)"},
    {"drug_a": "levofloxacin", "drug_b": "prednisone",      "severity": "HIGH",      "mechanism": "Fluoroquinolone + corticosteroid",             "effect": "Tendon rupture risk"},

    # === LITHIUM TOXICITY ===
    {"drug_a": "lithium",      "drug_b": "ibuprofen",       "severity": "HIGH",      "mechanism": "NSAID reduces renal lithium clearance",       "effect": "Lithium toxicity: tremor, confusion, cardiac arrhythmias"},
    {"drug_a": "lithium",      "drug_b": "hydrochlorothiazide","severity": "HIGH",   "mechanism": "Thiazide reduces renal lithium clearance",    "effect": "Lithium toxicity"},
    {"drug_a": "lithium",      "drug_b": "lisinopril",      "severity": "HIGH",      "mechanism": "ACEi reduces renal lithium clearance",        "effect": "Lithium toxicity"},
]


# =============================================================================
# 3. DRUG CLASS MAP — for duplicate therapy detection
#    Format: {class_name: [list of drug substrings]}
# =============================================================================

DRUG_CLASS_MAP: dict[str, list[str]] = {
    "ACE Inhibitors": ["lisinopril", "enalapril", "ramipril", "benazepril", "captopril",
                       "fosinopril", "moexipril", "perindopril", "quinapril", "trandolapril"],
    "ARBs (Angiotensin Receptor Blockers)": ["losartan", "valsartan", "irbesartan", "candesartan",
                                              "olmesartan", "telmisartan", "azilsartan", "eprosartan"],
    "Beta-Blockers": ["metoprolol", "atenolol", "carvedilol", "bisoprolol", "nebivolol",
                      "propranolol", "labetalol", "nadolol", "timolol", "acebutolol"],
    "Statins (HMG-CoA Reductase Inhibitors)": ["atorvastatin", "rosuvastatin", "simvastatin",
                                                 "pravastatin", "lovastatin", "fluvastatin",
                                                 "pitavastatin", "cerivastatin"],
    "SSRIs (Selective Serotonin Reuptake Inhibitors)": ["sertraline", "fluoxetine", "escitalopram",
                                                          "citalopram", "paroxetine", "fluvoxamine"],
    "Benzodiazepines": ["lorazepam", "diazepam", "alprazolam", "clonazepam", "temazepam",
                        "oxazepam", "chlordiazepoxide", "flurazepam", "triazolam", "midazolam"],
    "Opioids": ["oxycodone", "hydrocodone", "morphine", "fentanyl", "tramadol", "codeine",
                "hydromorphone", "oxymorphone", "buprenorphine", "methadone", "tapentadol"],
    "NSAIDs": ["ibuprofen", "naproxen", "diclofenac", "indomethacin", "meloxicam",
               "celecoxib", "ketorolac", "sulindac", "etodolac", "piroxicam"],
    "PPI (Proton Pump Inhibitors)": ["omeprazole", "pantoprazole", "lansoprazole", "esomeprazole",
                                      "rabeprazole", "dexlansoprazole"],
    "Sulfonylureas": ["glipizide", "glyburide", "glibenclamide", "glimepiride", "gliclazide",
                      "tolbutamide", "chlorpropamide"],
    "Calcium Channel Blockers (Dihydropyridine)": ["amlodipine", "nifedipine", "felodipine",
                                                     "nicardipine", "isradipine", "nisoldipine"],
    "Anticoagulants": ["warfarin", "rivaroxaban", "apixaban", "dabigatran", "edoxaban",
                       "enoxaparin", "heparin", "fondaparinux"],
    "Antiplatelets": ["aspirin", "clopidogrel", "prasugrel", "ticagrelor", "ticlopidine"],
    "Diuretics (Thiazide)": ["hydrochlorothiazide", "chlorthalidone", "metolazone",
                              "indapamide", "bendroflumethiazide"],
    "SGLT2 Inhibitors": ["empagliflozin", "dapagliflozin", "canagliflozin", "ertugliflozin"],
    "GLP-1 Agonists": ["semaglutide", "liraglutide", "dulaglutide", "exenatide",
                        "albiglutide", "tirzepatide"],
    "Antipsychotics (Atypical)": ["quetiapine", "olanzapine", "risperidone", "aripiprazole",
                                   "ziprasidone", "lurasidone", "asenapine", "iloperidone"],
    "Alpha-1 Blockers": ["doxazosin", "prazosin", "terazosin", "tamsulosin",
                         "alfuzosin", "silodosin"],
    "Tricyclic Antidepressants": ["amitriptyline", "imipramine", "nortriptyline", "doxepin",
                                   "clomipramine", "desipramine", "trimipramine"],
    "Fluoroquinolones": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin"],
    "Muscle Relaxants": ["cyclobenzaprine", "methocarbamol", "carisoprodol",
                         "metaxalone", "chlorzoxazone", "baclofen", "tizanidine"],
}


# =============================================================================
# 4. RENAL DOSING — drugs requiring adjustment or avoidance in CKD
#    Format: {drug_substring: {egfr_threshold: action, note: explanation}}
# =============================================================================

RENAL_DOSING: list[dict] = [
    # Avoid entirely
    {"drug": "metformin",          "threshold": 30,  "action": "AVOID",  "note": "Lactic acidosis risk — avoid if eGFR <30. Caution 30–45 (max 1000mg/day)."},
    {"drug": "nitrofurantoin",     "threshold": 30,  "action": "AVOID",  "note": "Ineffective + peripheral neuropathy/pulmonary toxicity risk below eGFR 30."},
    {"drug": "indomethacin",       "threshold": 60,  "action": "AVOID",  "note": "NSAIDs worsen renal function. Indomethacin most nephrotoxic — avoid in any CKD."},
    {"drug": "ibuprofen",          "threshold": 45,  "action": "AVOID",  "note": "NSAIDs reduce renal prostaglandins → AKI risk, especially if volume-depleted."},
    {"drug": "naproxen",           "threshold": 45,  "action": "AVOID",  "note": "NSAID: GFR-dependent prostaglandin → AKI. Avoid if eGFR <45."},
    {"drug": "ketorolac",          "threshold": 60,  "action": "AVOID",  "note": "High-potency NSAID — avoid in all CKD."},
    {"drug": "triamterene",        "threshold": 30,  "action": "AVOID",  "note": "Potassium-sparing diuretic — hyperkalemia risk in CKD."},
    {"drug": "spironolactone",     "threshold": 30,  "action": "AVOID",  "note": "Hyperkalemia risk. Acceptable in HFrEF with close monitoring if eGFR 30–60."},

    # Significant dose reduction required
    {"drug": "gabapentin",         "threshold": 60,  "action": "REDUCE", "note": "Renally cleared. Dose should be halved at eGFR 30–60, further reduced <30. Major toxicity risk."},
    {"drug": "pregabalin",         "threshold": 60,  "action": "REDUCE", "note": "Renally cleared — reduce dose proportionally to eGFR. Max 75mg BID if eGFR 30–60."},
    {"drug": "digoxin",            "threshold": 60,  "action": "REDUCE", "note": "Narrow therapeutic index. Reduce dose and monitor levels carefully in CKD."},
    {"drug": "lithium",            "threshold": 60,  "action": "REDUCE", "note": "Renally excreted — toxicity risk. Increase monitoring frequency; consider alternatives."},
    {"drug": "atenolol",           "threshold": 35,  "action": "REDUCE", "note": "Renally cleared — halve dose if eGFR <35. Risk of bradycardia/hypotension."},
    {"drug": "sotalol",            "threshold": 40,  "action": "AVOID",  "note": "Renally excreted. Avoid if eGFR <40 — QT prolongation and torsades risk."},
    {"drug": "dabigatran",         "threshold": 30,  "action": "AVOID",  "note": "Renally cleared. Avoid if CrCl <30. Dose-adjust 30–50mL/min (110mg BID)."},
    {"drug": "rivaroxaban",        "threshold": 15,  "action": "AVOID",  "note": "Avoid if eGFR <15. Caution 15–30 — increased bleeding risk."},
    {"drug": "apixaban",           "threshold": 15,  "action": "AVOID",  "note": "Avoid if eGFR <15. Dose-reduce using serum Cr criteria (≥1.5 + age ≥80 or weight ≤60kg)."},
    {"drug": "allopurinol",        "threshold": 30,  "action": "REDUCE", "note": "Reduce dose — allopurinol hypersensitivity syndrome risk with standard doses in CKD."},
    {"drug": "colchicine",         "threshold": 30,  "action": "REDUCE", "note": "Avoid prolonged courses in severe CKD — neuromuscular toxicity."},
    {"drug": "methotrexate",       "threshold": 45,  "action": "AVOID",  "note": "Accumulates in renal impairment → myelosuppression, mucositis, nephrotoxicity."},
    {"drug": "trimethoprim",       "threshold": 30,  "action": "AVOID",  "note": "Raises creatinine by blocking tubular secretion. Hyperkalemia risk in CKD."},
    {"drug": "ciprofloxacin",      "threshold": 30,  "action": "REDUCE", "note": "Reduce dose if eGFR <30. Standard doses → seizure risk from drug accumulation."},
    {"drug": "levofloxacin",       "threshold": 50,  "action": "REDUCE", "note": "Dose-reduce if eGFR <50. Renally excreted — accumulation causes QT prolongation."},

    # Reduced efficacy
    {"drug": "empagliflozin",      "threshold": 20,  "action": "AVOID",  "note": "SGLT2i loses glycemic efficacy. Empagliflozin approved ≥20 for HF, not glycemia."},
    {"drug": "dapagliflozin",      "threshold": 25,  "action": "AVOID",  "note": "Avoid for T2DM if eGFR <25. Only heart failure/CKD indication below this."},
    {"drug": "canagliflozin",      "threshold": 30,  "action": "AVOID",  "note": "Avoid if eGFR <30. Reduced efficacy and maintained side-effect profile."},
    {"drug": "acyclovir",          "threshold": 25,  "action": "REDUCE", "note": "Renally cleared — reduce dose or dosing frequency in CKD."},
    {"drug": "valacyclovir",       "threshold": 50,  "action": "REDUCE", "note": "Dose-reduce in CKD to avoid crystalline nephropathy and neurotoxicity."},
]


# =============================================================================
# 5. eGFR CALCULATION — CKD-EPI 2021 (Race-Free)
# =============================================================================

def calculate_egfr(creatinine_mg_dl: float, age_years: int, sex: str) -> float:
    """
    CKD-EPI 2021 race-free eGFR equation.
    sex: 'female' / 'F' or 'male' / 'M'
    Returns eGFR in mL/min/1.73m²
    """
    is_female = sex.lower() in ("female", "f", "woman")
    kappa = 0.7 if is_female else 0.9
    alpha = -0.241 if is_female else -0.302
    sex_factor = 1.012 if is_female else 1.0

    ratio = creatinine_mg_dl / kappa
    egfr = (142
            * (min(ratio, 1.0) ** alpha)
            * (max(ratio, 1.0) ** -1.200)
            * (0.9938 ** age_years)
            * sex_factor)
    return round(egfr, 1)


def stage_ckd(egfr: float) -> tuple[str, str]:
    """
    Returns (stage, description) tuple for given eGFR value.
    """
    if egfr >= 90:   return ("G1", "Normal or high — monitor if other kidney damage markers present")
    elif egfr >= 60: return ("G2", "Mildly decreased")
    elif egfr >= 45: return ("G3a", "Mild-moderately decreased")
    elif egfr >= 30: return ("G3b", "Moderate-severely decreased")
    elif egfr >= 15: return ("G4", "Severely decreased")
    else:            return ("G5", "Kidney failure")


# =============================================================================
# 6. HEART FAILURE THERAPY — 4 GDMT Pillars (ACC/AHA 2022)
#    For HFrEF (EF ≤ 40%)
# =============================================================================

HF_GDMT_PILLARS: dict[str, dict] = {
    "ACEi/ARB/ARNi": {
        "drugs": ["lisinopril", "enalapril", "ramipril", "captopril", "quinapril", "fosinopril",
                  "losartan", "valsartan", "candesartan", "irbesartan",
                  "sacubitril"],  # sacubitril/valsartan = Entresto
        "class": "Renin-Angiotensin System Blocker",
        "evidence": "Class I; reduces mortality 20-25%",
    },
    "Beta-Blocker": {
        "drugs": ["carvedilol", "metoprolol succinate", "metoprolol xl", "bisoprolol"],
        "class": "Evidence-based beta-blocker for HF",
        "evidence": "Class I; evidence only for carvedilol, metoprolol succinate, bisoprolol",
    },
    "MRA (Mineralocorticoid Receptor Antagonist)": {
        "drugs": ["spironolactone", "eplerenone", "finerenone"],
        "class": "Aldosterone antagonist",
        "evidence": "Class I; reduces mortality and hospitalizations",
    },
    "SGLT2 Inhibitor": {
        "drugs": ["empagliflozin", "dapagliflozin"],
        "class": "Sodium-glucose cotransporter-2 inhibitor",
        "evidence": "Class I (2022 update); reduces HF hospitalizations and cardiovascular death",
    },
}

HF_DIAGNOSIS_CODES: list[str] = [
    "Heart failure", "Congestive heart failure", "Systolic heart failure",
    "HFrEF", "Cardiomyopathy", "Dilated cardiomyopathy",
    "I50", "I50.2", "I50.20", "I50.22", "I50.3",   # ICD-10 codes
    "42343007", "48447003", "84114007",             # SNOMED codes
]


# =============================================================================
# 7. DIABETES HEDIS CARE GAPS
# =============================================================================

DIABETES_CODES: list[str] = [
    "Diabetes", "Type 2 diabetes", "Type 1 diabetes", "Diabetes mellitus",
    "E11", "E10", "73211009", "44054006",
]

DIABETES_HEDIS_MEASURES: list[dict] = [
    {
        "measure": "HbA1c control",
        "loinc": ["4548-4", "17856-6", "59261-8"],  # HbA1c LOINC codes
        "max_age_days": 180,
        "target": "<9% (poor control if ≥9%)",
        "poor_threshold": 9.0,
    },
    {
        "measure": "Blood pressure control",
        "loinc": ["8480-6"],  # Systolic BP
        "max_age_days": 365,
        "target": "SBP <140 mmHg",
        "poor_threshold": 140.0,
    },
    {
        "measure": "Nephropathy monitoring (uACR)",
        "loinc": ["14957-5", "9318-7", "32294-1", "14959-1"],  # urine albumin/creatinine
        "max_age_days": 365,
        "target": "Annual urine albumin-to-creatinine ratio",
        "poor_threshold": None,
    },
    {
        "measure": "eGFR/creatinine monitoring",
        "loinc": ["2160-0", "38483-4"],  # creatinine
        "max_age_days": 365,
        "target": "Annual serum creatinine for eGFR calculation",
        "poor_threshold": None,
    },
    {
        "measure": "Statin therapy",
        "drugs": ["atorvastatin", "rosuvastatin", "simvastatin", "pravastatin",
                  "lovastatin", "fluvastatin", "pitavastatin"],
        "max_age_days": None,
        "target": "Active statin prescription for cardiovascular risk reduction",
        "poor_threshold": None,
    },
]


# =============================================================================
# 8. VACCINE SCHEDULE (ACIP 2024) — for gap detection
# =============================================================================

VACCINE_SCHEDULE: list[dict] = [
    {
        "vaccine": "Influenza",
        "cvx_codes": ["88", "141", "150", "158", "161"],
        "display_names": ["influenza", "flu"],
        "min_age": 6,
        "max_age": 999,
        "frequency": "annual",
        "max_age_days": 365,
        "description": "Annual flu vaccine for all patients ≥6 months",
    },
    {
        "vaccine": "Pneumococcal (PCV15/PCV20 or PPSV23)",
        "cvx_codes": ["33", "100", "109", "152", "133"],
        "display_names": ["pneumococcal", "prevnar", "pneumovax"],
        "min_age": 65,
        "max_age": 999,
        "frequency": "one-time (boosters per schedule)",
        "max_age_days": None,
        "description": "For adults ≥65 or high-risk conditions (COPD, diabetes, asplenia)",
    },
    {
        "vaccine": "Shingles (Shingrix)",
        "cvx_codes": ["187", "121"],
        "display_names": ["zoster", "shingrix", "varicella zoster"],
        "min_age": 50,
        "max_age": 999,
        "frequency": "2-dose series (once in lifetime)",
        "max_age_days": None,
        "description": "Recombinant Shingrix for all adults ≥50 (2 doses, 2-6 months apart)",
    },
    {
        "vaccine": "Tdap",
        "cvx_codes": ["115"],
        "display_names": ["tdap", "diphtheria", "pertussis", "tetanus"],
        "min_age": 19,
        "max_age": 999,
        "frequency": "once then Td every 10 years",
        "max_age_days": None,
        "description": "Tdap once in adulthood, then Td booster every 10 years",
    },
    {
        "vaccine": "COVID-19",
        "cvx_codes": ["207", "208", "210", "211", "212", "213", "217", "218", "219", "220", "221", "228", "229", "230"],
        "display_names": ["covid", "sars-cov-2", "coronavirus", "mrna-1273", "bnt162"],
        "min_age": 6,
        "max_age": 999,
        "frequency": "annual updated booster",
        "max_age_days": 365,
        "description": "Annual updated COVID-19 booster (current season formulation)",
    },
    {
        "vaccine": "RSV (Abrysvo/Arexvy)",
        "cvx_codes": ["300", "301"],
        "display_names": ["rsv", "abrysvo", "arexvy"],
        "min_age": 60,
        "max_age": 999,
        "frequency": "once (re-evaluate annually)",
        "max_age_days": None,
        "description": "RSV vaccine for adults ≥60 (shared decision making)",
    },
]


# =============================================================================
# 9. FALL RISK SCORING
# =============================================================================

FALL_RISK_MEDICATIONS: dict[str, int] = {
    # key: drug substring, value: risk points
    "lorazepam": 3, "diazepam": 3, "alprazolam": 3, "clonazepam": 3,
    "temazepam": 3, "zolpidem": 3, "eszopiclone": 3, "zaleplon": 3,
    "oxycodone": 2, "hydrocodone": 2, "morphine": 2, "fentanyl": 2,
    "tramadol": 2, "codeine": 2, "hydromorphone": 2, "methadone": 2,
    "amitriptyline": 2, "imipramine": 2, "nortriptyline": 2, "doxepin": 2,
    "cyclobenzaprine": 1, "methocarbamol": 1, "carisoprodol": 1,
    "diphenhydramine": 2, "hydroxyzine": 2, "promethazine": 2,
    "quetiapine": 2, "haloperidol": 2, "olanzapine": 1, "risperidone": 1,
    "doxazosin": 2, "prazosin": 2, "terazosin": 2,
    "furosemide": 1, "hydrochlorothiazide": 1, "chlorthalidone": 1,
    "metoprolol": 1, "atenolol": 1, "lisinopril": 1, "amlodipine": 1,
}

FALL_RISK_CONDITIONS: dict[str, int] = {
    "Parkinson": 3, "parkinson": 3,
    "stroke": 2, "cerebrovascular": 2, "hemiplegia": 2,
    "dementia": 2, "Alzheimer": 2, "cognitive impairment": 2,
    "osteoporosis": 2,
    "neuropathy": 1, "peripheral neuropathy": 1,
    "hypotension": 2, "orthostatic": 2,
    "syncope": 2, "presyncope": 1,
    "visual impairment": 1, "macular degeneration": 1, "glaucoma": 1,
    "arthritis": 1, "gout": 1,
    "depression": 1,
    "fall": 3,  # history of falls
    "fracture": 2,
}


# =============================================================================
# 10. ALLERGY CROSS-REACTIVITY MAP
#     key: allergen substring → list of drug substrings that share cross-reactivity
# =============================================================================

ALLERGY_CROSS_REACTIVITY: dict[str, list[str]] = {
    "penicillin": ["amoxicillin", "ampicillin", "piperacillin", "oxacillin",
                   "nafcillin", "dicloxacillin", "amoxicillin-clavulanate",
                   "piperacillin-tazobactam"],
    "sulfa": ["trimethoprim-sulfamethoxazole", "sulfamethoxazole", "sulfadiazine",
              "furosemide", "hydrochlorothiazide", "thiazide",
              "celecoxib", "chlorthalidone"],  # sulfonamide moiety controversy — flag for review
    "cephalosporin": ["cefalexin", "cefazolin", "cefuroxime", "cefdinir", "ceftriaxone",
                      "cefepime", "ceftazidime"],
    "fluoroquinolone": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "ofloxacin"],
    "aspirin": ["ibuprofen", "naproxen", "indomethacin", "diclofenac",
                "celecoxib", "ketorolac", "meloxicam"],  # NSAID cross-reactivity
    "codeine": ["oxycodone", "hydrocodone", "hydromorphone", "tramadol", "morphine"],
    "contrast": ["iodine", "shellfish"],  # cross-reactivity controversial but flagged clinically
}


# =============================================================================
# 11. INFECTION-RELATED SNOMED/ICD CODES — used for sepsis prerequisite check
# =============================================================================

INFECTION_SNOMED_CODES: set[str] = {
    # Pneumonia
    "233604007", "422587007", "275498002", "53084003",
    # UTI
    "68566005", "90688005",
    # Sepsis
    "91302008", "434156008", "76571007",
    # Cellulitis
    "385699009",
    # Bacteremia
    "5758002",
    # Abdominal infection
    "74474003", "47693006",
    # General infection
    "40733004",
}

INFECTION_ICD_PREFIXES: tuple[str, ...] = (
    "A0", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9",
    "B0", "B1", "B2", "B3", "B4",
    "J0", "J1", "J2",   # Respiratory
    "N10", "N11", "N12", "N30",  # UTI/pyelonephritis
    "L0",                # Cellulitis
    "K57", "K65",        # Abdominal
    "G00", "G01", "G02", # Meningitis
)

ALTERED_MENTATION_CODES: set[str] = {
    "R41.3", "R41.82", "F05", "G93.1", "R55", "R41.0",
    # SNOMED
    "40917007", "419284004", "130987000",
}


# =============================================================================
# 12. NEWS2 SCORING — National Early Warning Score 2
#     Royal College of Physicians 2017
#     Each parameter scores 0–3; total 0–20
# =============================================================================

NEWS2_PARAMS: dict[str, list[dict]] = {
    "respiratory_rate": [
        {"min": 25, "max": 999, "score": 3},
        {"min": 21, "max": 24,  "score": 2},
        {"min": 9,  "max": 11,  "score": 1},
        {"min": 12, "max": 20,  "score": 0},
        {"min": 0,  "max": 8,   "score": 3},
    ],
    "spo2_scale1": [
        {"min": 0,  "max": 91,  "score": 3},
        {"min": 92, "max": 93,  "score": 2},
        {"min": 94, "max": 95,  "score": 1},
        {"min": 96, "max": 100, "score": 0},
    ],
    "systolic_bp": [
        {"min": 0,   "max": 90,  "score": 3},
        {"min": 91,  "max": 100, "score": 2},
        {"min": 101, "max": 110, "score": 1},
        {"min": 111, "max": 219, "score": 0},
        {"min": 220, "max": 999, "score": 3},
    ],
    "heart_rate": [
        {"min": 0,   "max": 40,  "score": 3},
        {"min": 41,  "max": 50,  "score": 1},
        {"min": 51,  "max": 90,  "score": 0},
        {"min": 91,  "max": 110, "score": 1},
        {"min": 111, "max": 130, "score": 2},
        {"min": 131, "max": 999, "score": 3},
    ],
    "temperature": [
        {"min": 0,    "max": 35.0, "score": 3},
        {"min": 35.1, "max": 36.0, "score": 1},
        {"min": 36.1, "max": 38.0, "score": 0},
        {"min": 38.1, "max": 39.0, "score": 1},
        {"min": 39.1, "max": 999,  "score": 2},
    ],
}

NEWS2_RESPONSE: dict[str, dict] = {
    "LOW":      {"range": "0-4",  "frequency": "Minimum 12 hourly", "response": "Ward-based response"},
    "LOW_KEY":  {"range": "3 in single parameter", "frequency": "Minimum 1 hourly", "response": "Urgent ward-based response"},
    "MEDIUM":   {"range": "5-6",  "frequency": "Minimum 1 hourly", "response": "Key threshold — urgent response, consider critical care"},
    "HIGH":     {"range": "7+",   "frequency": "Continuous monitoring", "response": "Emergency response — immediate clinical review, consider ICU"},
}


# =============================================================================
# 13. QT-PROLONGING DRUGS — CredibleMeds / AHA 2023
#     risk: KNOWN (proven TdP risk), POSSIBLE, CONDITIONAL
# =============================================================================

QT_PROLONGING_DRUGS: list[dict] = [
    # Antiarrhythmics
    {"drug": "amiodarone",     "risk": "KNOWN",       "class": "Antiarrhythmic",   "note": "Class III — direct QT effect"},
    {"drug": "sotalol",        "risk": "KNOWN",       "class": "Antiarrhythmic",   "note": "Class III — dose-dependent QT"},
    {"drug": "dronedarone",    "risk": "KNOWN",       "class": "Antiarrhythmic",   "note": "Class III"},
    {"drug": "dofetilide",     "risk": "KNOWN",       "class": "Antiarrhythmic",   "note": "Class III — requires inpatient initiation"},
    {"drug": "procainamide",   "risk": "KNOWN",       "class": "Antiarrhythmic",   "note": "Class Ia"},
    {"drug": "quinidine",      "risk": "KNOWN",       "class": "Antiarrhythmic",   "note": "Class Ia"},
    # Antipsychotics
    {"drug": "haloperidol",    "risk": "KNOWN",       "class": "Antipsychotic",    "note": "IV route highest risk"},
    {"drug": "thioridazine",   "risk": "KNOWN",       "class": "Antipsychotic",    "note": "Withdrawn in many countries"},
    {"drug": "ziprasidone",    "risk": "KNOWN",       "class": "Antipsychotic",    "note": "Highest QT risk among atypicals"},
    {"drug": "chlorpromazine", "risk": "KNOWN",       "class": "Antipsychotic",    "note": "First-gen — dose-dependent"},
    {"drug": "quetiapine",     "risk": "POSSIBLE",    "class": "Antipsychotic",    "note": "Lower risk but still flagged"},
    {"drug": "risperidone",    "risk": "POSSIBLE",    "class": "Antipsychotic",    "note": "Modest QT effect"},
    {"drug": "olanzapine",     "risk": "POSSIBLE",    "class": "Antipsychotic",    "note": "Modest QT effect"},
    # Antibiotics
    {"drug": "azithromycin",   "risk": "KNOWN",       "class": "Macrolide",        "note": "FDA safety warning 2013"},
    {"drug": "clarithromycin", "risk": "KNOWN",       "class": "Macrolide",        "note": "CYP3A4 inhibitor amplifies risk"},
    {"drug": "erythromycin",   "risk": "KNOWN",       "class": "Macrolide",        "note": "IV form highest risk"},
    {"drug": "ciprofloxacin",  "risk": "POSSIBLE",    "class": "Fluoroquinolone",  "note": "Less than moxifloxacin"},
    {"drug": "levofloxacin",   "risk": "POSSIBLE",    "class": "Fluoroquinolone",  "note": "Moderate risk"},
    {"drug": "moxifloxacin",   "risk": "KNOWN",       "class": "Fluoroquinolone",  "note": "Highest QT among fluoroquinolones"},
    # Antifungals
    {"drug": "fluconazole",    "risk": "KNOWN",       "class": "Antifungal",       "note": "Dose-dependent + CYP inhibition"},
    # Antiemetics
    {"drug": "ondansetron",    "risk": "KNOWN",       "class": "Antiemetic",       "note": "FDA dose cap — max 16mg IV"},
    {"drug": "domperidone",    "risk": "KNOWN",       "class": "Antiemetic",       "note": "Restricted in many countries"},
    # Opioids
    {"drug": "methadone",      "risk": "KNOWN",       "class": "Opioid",           "note": "Dose-dependent — ECG monitoring required"},
    # SSRIs/SNRIs
    {"drug": "citalopram",     "risk": "KNOWN",       "class": "SSRI",             "note": "FDA max 40mg (20mg if >60yo)"},
    {"drug": "escitalopram",   "risk": "POSSIBLE",    "class": "SSRI",             "note": "Less than citalopram but still flagged"},
    # Other
    {"drug": "hydroxychloroquine", "risk": "KNOWN",   "class": "Antimalarial",     "note": "COVID-era awareness"},
    {"drug": "donepezil",      "risk": "POSSIBLE",    "class": "Cholinesterase inhibitor", "note": "Bradycardia + QT"},
    {"drug": "tamoxifen",      "risk": "CONDITIONAL", "class": "Antineoplastic",   "note": "Risk with CYP2D6 poor metabolizers"},
]

# Electrolyte LOINC codes for QT risk assessment
QT_ELECTROLYTE_LOINC: dict[str, dict] = {
    "potassium":  {"loinc": ["2823-3", "6298-4"], "low_threshold": 3.5, "unit": "mEq/L"},
    "magnesium":  {"loinc": ["19123-9", "2601-3"], "low_threshold": 1.7, "unit": "mg/dL"},
    "calcium":    {"loinc": ["17861-6", "49765-1"], "low_threshold": 8.5, "unit": "mg/dL"},
}


# =============================================================================
# 14. SEROTONERGIC DRUGS — for serotonin syndrome screening
#     Based on Hunter Serotonin Toxicity Criteria
# =============================================================================

SEROTONERGIC_DRUGS: dict[str, list[str]] = {
    "SSRI":    ["sertraline", "fluoxetine", "paroxetine", "citalopram", "escitalopram", "fluvoxamine"],
    "SNRI":    ["venlafaxine", "duloxetine", "desvenlafaxine", "milnacipran", "levomilnacipran"],
    "TCA":     ["amitriptyline", "imipramine", "clomipramine", "nortriptyline", "doxepin", "desipramine"],
    "MAOi":    ["phenelzine", "tranylcypromine", "selegiline", "rasagiline", "isocarboxazid", "linezolid"],
    "Opioid_serotonergic": ["tramadol", "meperidine", "fentanyl", "methadone", "tapentadol"],
    "Triptan": ["sumatriptan", "rizatriptan", "zolmitriptan", "eletriptan", "naratriptan", "almotriptan", "frovatriptan"],
    "Other":   ["lithium", "buspirone", "trazodone", "methylene blue", "dextromethorphan", "st john"],
}

# High-risk serotonergic combinations
SEROTONIN_CRITICAL_COMBOS: list[dict] = [
    {"cat_a": "MAOi",  "cat_b": "SSRI",  "severity": "CRITICAL", "note": "Contraindicated — 14-day washout required"},
    {"cat_a": "MAOi",  "cat_b": "SNRI",  "severity": "CRITICAL", "note": "Contraindicated — 14-day washout required"},
    {"cat_a": "MAOi",  "cat_b": "TCA",   "severity": "CRITICAL", "note": "Contraindicated"},
    {"cat_a": "MAOi",  "cat_b": "Opioid_serotonergic", "severity": "CRITICAL", "note": "Contraindicated — especially meperidine"},
    {"cat_a": "SSRI",  "cat_b": "Opioid_serotonergic", "severity": "HIGH",     "note": "Monitor for serotonin syndrome symptoms"},
    {"cat_a": "SNRI",  "cat_b": "Opioid_serotonergic", "severity": "HIGH",     "note": "Monitor for serotonin syndrome symptoms"},
    {"cat_a": "SSRI",  "cat_b": "Triptan", "severity": "HIGH",   "note": "FDA warning — monitor for serotonin syndrome"},
    {"cat_a": "SSRI",  "cat_b": "TCA",   "severity": "MODERATE", "note": "Cumulative serotonergic effect — use with caution"},
]


# =============================================================================
# 15. OPIOID + CNS DEPRESSANT COMBINATIONS — FDA REMS 2023
# =============================================================================

OPIOID_DRUGS: list[str] = [
    "oxycodone", "hydrocodone", "morphine", "fentanyl", "tramadol",
    "codeine", "hydromorphone", "oxymorphone", "buprenorphine", "methadone", "tapentadol",
]

CNS_DEPRESSANT_DRUGS: dict[str, list[str]] = {
    "Benzodiazepine": ["lorazepam", "diazepam", "alprazolam", "clonazepam", "temazepam",
                       "midazolam", "oxazepam", "chlordiazepoxide"],
    "Z-drug": ["zolpidem", "zaleplon", "eszopiclone"],
    "Gabapentinoid": ["gabapentin", "pregabalin"],
    "Muscle_relaxant": ["cyclobenzaprine", "carisoprodol", "methocarbamol", "baclofen", "tizanidine"],
    "Sedating_antihistamine": ["diphenhydramine", "hydroxyzine", "promethazine", "doxylamine"],
    "Sedating_antipsychotic": ["quetiapine", "olanzapine", "chlorpromazine"],
}