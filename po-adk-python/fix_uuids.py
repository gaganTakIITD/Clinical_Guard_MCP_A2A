import json

data = json.load(open(r'd:\Ai hackathon devpost\po-adk-python\demo_patient_bundle.json', encoding='utf-8'))

# Find patient's fullUrl
patient_full_url = None
for entry in data['entry']:
    if entry['resource']['resourceType'] == 'Patient':
        patient_full_url = entry['fullUrl']
        break

print(f'Patient fullUrl: {patient_full_url}')

# Fix all subject/patient references to use urn:uuid: format
fixed = 0
for entry in data['entry']:
    res = entry['resource']
    for key in ['subject', 'patient']:
        if key in res and 'reference' in res[key]:
            if res[key]['reference'].startswith('Patient/'):
                res[key]['reference'] = patient_full_url
                fixed += 1

json.dump(data, open(r'd:\Ai hackathon devpost\po-adk-python\demo_patient_bundle.json', 'w', encoding='utf-8'), indent=2)
print(f'Fixed {fixed} references to use urn:uuid format.')
