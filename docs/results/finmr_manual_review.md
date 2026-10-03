# FinMR manual review sheet

Use this to spot-check GT labels and failure patterns before/after an LLM run.

## id=3 · DQC_US_0015
- GT extracted: `-157,000,000`
- GT calculated: `157,000,000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 112,835 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=13 · DQC_US_0015
- GT extracted: `-17,777`
- GT calculated: `17,777`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 80,823 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=14 · DQC_US_0015
- GT extracted: `-182000`
- GT calculated: `182000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 58,597 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=17 · DQC_US_0015
- GT extracted: `-46600000`
- GT calculated: `46600000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 71,534 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=28 · DQC_US_0015
- GT extracted: `-4,200,000`
- GT calculated: `4,200,000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 99,382 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=31 · DQC_US_0015
- GT extracted: `-58,000`
- GT calculated: `58,000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 115,264 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=35 · DQC_US_0015
- GT extracted: `-226,000`
- GT calculated: `226,000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 114,651 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=81 · DQC_US_0015
- GT extracted: `-451,000`
- GT calculated: `451,000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 127,087 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=86 · DQC_US_0015
- GT extracted: `-149,000`
- GT calculated: `149,000`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 119,302 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```

## id=94 · DQC_US_0015
- GT extracted: `-189,767`
- GT calculated: `189,767`
- Pattern hint: **sign_flip (extracted ≈ −calculated)**
- Query length: 121,687 chars
- Query head:
```
"You are an auditor for XBRL filings. \nGiven the question and the provided filing \n(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \nidentify the reported value of a financial element and calculate the actual value that should be reported based on calculation relationships.\n\nAnswer strictly in the following JSON format:\n{\n  \"extracted_value\": \"<numeric value reported in the instance document, or 0 if not found, keep the same format as in the XBRL 
```
