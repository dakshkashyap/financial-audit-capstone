import json
import os
import re
from collections import Counter

from core.parser import DATA as _PARSER_DATA

FILE_PATH = os.environ.get(
    "AUDITBENCH_SINGLE_ERROR_PATH", _PARSER_DATA["single_error"])

def extract_fasb_id(citation_text):
    # Extracts FASB ASC xxx-xx-xx from the text
    match = re.search(r'FASB ASC (\d+-\d+-\d+(-\d+)?)', citation_text)
    if match:
        return match.group(1)
    
    match_fallback = re.search(r'ASC (\d+-\d+-\d+(-\d+)?)', citation_text)
    if match_fallback:
        return match_fallback.group(1)
    return "UNKNOWN"

def build_registry():
    print(f"Loading data from {FILE_PATH}...")
    try:
        with open(FILE_PATH, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading JSON: {e}")
        return

    registry = {}
    citation_counter = Counter()

    for item in data:
        error_id_info = item.get("Error Identification", {})
        error_type = error_id_info.get("Error Type", "Unknown")
        
        # In reality, statement type, row, etc. can be parsed from the table, but we use error_type and the rule here.
        citation_text = item.get("Standards Citation", "")
        fasb_id = extract_fasb_id(citation_text)
        
        citation_counter[fasb_id] += 1
        
        # Group by error type for simplicity in the initial registry
        if error_type not in registry:
            registry[error_type] = {}
        
        # We can further subdivide by statement type or problematic entry, but for now we aggregate
        # the citations used per error type.
        if fasb_id not in registry[error_type]:
            registry[error_type][fasb_id] = 0
        registry[error_type][fasb_id] += 1

    print("\n--- FASB IDs Found ---")
    for fasb_id, count in citation_counter.most_common(20):
        print(f"{fasb_id}: {count} occurrences")

    print("\n--- Constraint Registry by Error Type ---")
    for err_type, fasb_counts in registry.items():
        print(f"\n{err_type}:")
        for fid, count in sorted(fasb_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {fid}: {count} occurrences")

    # Save to file
    out_file = os.path.join(os.path.dirname(__file__), "constraint_registry.json")
    with open(out_file, 'w') as f:
        json.dump(registry, f, indent=2)
    print(f"\nSaved registry to {out_file}")

if __name__ == "__main__":
    build_registry()
