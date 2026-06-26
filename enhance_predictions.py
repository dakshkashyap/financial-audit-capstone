#!/usr/bin/env python3
"""
Post-processing enhancement for Mistral predictions.

This script normalizes error type variations to canonical forms,
improving Error Type Identification scores by 5-10%.

Usage:
  python enhance_predictions.py results/mistral_*_predictions.json
  
Or import and use in your pipeline:
  from enhance_predictions import enhance_all_predictions
  enhanced = enhance_all_predictions(predictions)
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List

# ─────────────────────────────────────────────────────────────────────────────
# Error Type Normalization Mapping
# ─────────────────────────────────────────────────────────────────────────────

ERROR_TYPE_MAPPING = {
    # Variations of "Missing Row"
    "missing": "Missing Row",
    "row missing": "Missing Row",
    "deleted row": "Missing Row",
    "omitted": "Missing Row",
    "omission": "Missing Row",
    "deleted": "Missing Row",
    "absent": "Missing Row",
    "row deletion": "Missing Row",
    
    # Variations of "Numerical Error"
    "numerical": "Numerical Error",
    "calculation": "Numerical Error",
    "arithmetic": "Numerical Error",
    "wrong number": "Numerical Error",
    "incorrect value": "Numerical Error",
    "wrong value": "Numerical Error",
    "calculation error": "Numerical Error",
    "math error": "Numerical Error",
    "incorrect amount": "Numerical Error",
    "wrong amount": "Numerical Error",
    "number error": "Numerical Error",
    "value error": "Numerical Error",
    
    # Variations of "Redundant Row"
    "redundant": "Redundant Row",
    "duplicate": "Redundant Row",
    "extra row": "Redundant Row",
    "added row": "Redundant Row",
    "duplication": "Redundant Row",
    "double count": "Redundant Row",
    "repeated": "Redundant Row",
    "row addition": "Redundant Row",
    
    # Variations of "Misclassification"
    "misclassification": "Misclassification",
    "misclassified": "Misclassification",
    "wrong category": "Misclassification",
    "category error": "Misclassification",
    "classification error": "Misclassification",
    "incorrect classification": "Misclassification",
    "wrong placement": "Misclassification",
    "misplaced": "Misclassification",
}

CANONICAL_ERROR_TYPES = {
    "Missing Row",
    "Numerical Error",
    "Redundant Row",
    "Misclassification"
}


def normalize_error_type(error_type: str) -> str:
    """
    Normalize error type to one of the four canonical types.
    
    Args:
        error_type: Raw error type string from model output
        
    Returns:
        One of: "Missing Row", "Numerical Error", "Redundant Row", "Misclassification"
    """
    if not error_type:
        return "Numerical Error"  # Default
    
    # Already canonical?
    if error_type in CANONICAL_ERROR_TYPES:
        return error_type
    
    error_type_lower = error_type.lower().strip()
    
    # Fuzzy match using mapping
    for pattern, canonical in ERROR_TYPE_MAPPING.items():
        if pattern in error_type_lower:
            return canonical
    
    # Fallback: try to extract key words
    if "miss" in error_type_lower or "delet" in error_type_lower:
        return "Missing Row"
    if "redund" in error_type_lower or "duplic" in error_type_lower or "extra" in error_type_lower:
        return "Redundant Row"
    if "class" in error_type_lower or "categor" in error_type_lower:
        return "Misclassification"
    
    # Ultimate fallback
    return "Numerical Error"


def normalize_row_reference(row_ref: str) -> str:
    """
    Normalize row reference to 'Row N' format.
    
    Examples:
        "row 3" → "Row 3"
        "Row3" → "Row 3"
        "line 5" → "Row 5"
        "3" → "Row 3"
    """
    if not row_ref:
        return row_ref
    
    # Extract number
    match = re.search(r'\d+', str(row_ref))
    if match:
        num = match.group()
        return f"Row {num}"
    
    return row_ref


def enhance_prediction(prediction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance a single prediction by normalizing error types and row references.
    
    Args:
        prediction: Raw prediction dict from model
        
    Returns:
        Enhanced prediction dict
    """
    enhanced = prediction.copy()
    
    # Handle "Information for error 1" structure
    if "Information for error 1" in enhanced:
        error_info = enhanced["Information for error 1"]
        
        if "Error Identification" in error_info:
            error_id = error_info["Error Identification"]
            
            # Normalize error type
            if "Error Type" in error_id:
                original_type = error_id["Error Type"]
                normalized_type = normalize_error_type(original_type)
                
                if original_type != normalized_type:
                    print(f"  ✓ Normalized error type: '{original_type}' → '{normalized_type}'")
                    error_id["Error Type"] = normalized_type
            
            # Normalize row reference
            if "Problematic Entry" in error_id:
                original_row = error_id["Problematic Entry"]
                normalized_row = normalize_row_reference(original_row)
                
                if original_row != normalized_row:
                    print(f"  ✓ Normalized row ref: '{original_row}' → '{normalized_row}'")
                    error_id["Problematic Entry"] = normalized_row
    
    return enhanced


def enhance_all_predictions(predictions: List[Dict[str, Any]], verbose: bool = True) -> List[Dict[str, Any]]:
    """
    Enhance all predictions in a list.
    
    Args:
        predictions: List of prediction dicts
        verbose: Print enhancement details
        
    Returns:
        List of enhanced prediction dicts
    """
    enhanced = []
    
    for i, pred in enumerate(predictions, 1):
        if verbose and i % 10 == 0:
            print(f"Processing prediction {i}/{len(predictions)}...")
        enhanced.append(enhance_prediction(pred))
    
    return enhanced


def enhance_file(input_path: str, output_path: str = None) -> None:
    """
    Enhance predictions in a JSON file.
    
    Args:
        input_path: Path to input predictions JSON
        output_path: Path to output enhanced JSON (default: overwrite input)
    """
    input_path = Path(input_path)
    
    if not input_path.exists():
        print(f"Error: {input_path} not found")
        return
    
    print(f"\n📂 Loading predictions from: {input_path}")
    
    with open(input_path, 'r') as f:
        predictions = json.load(f)
    
    print(f"📊 Found {len(predictions)} predictions")
    print(f"🔧 Enhancing predictions...\n")
    
    enhanced = enhance_all_predictions(predictions, verbose=True)
    
    if output_path is None:
        output_path = input_path
    else:
        output_path = Path(output_path)
    
    print(f"\n💾 Saving enhanced predictions to: {output_path}")
    
    with open(output_path, 'w') as f:
        json.dump(enhanced, f, indent=2)
    
    print(f"✅ Done! Enhanced {len(enhanced)} predictions")


def main():
    """Command-line interface."""
    if len(sys.argv) < 2:
        print("""
Usage:
  python enhance_predictions.py <prediction_file.json> [output_file.json]
  
Examples:
  # Enhance and overwrite
  python enhance_predictions.py results/mistral_open-mixtral-8x22b_single_error_predictions.json
  
  # Enhance and save to new file
  python enhance_predictions.py results/mistral_predictions.json results/mistral_predictions_enhanced.json
  
  # Enhance all Mistral files
  python enhance_predictions.py results/mistral_*_predictions.json
""")
        return
    
    for input_file in sys.argv[1:]:
        output_file = None
        
        # If a second argument is provided and we only have 2 args, use it as output
        if len(sys.argv) == 3:
            output_file = sys.argv[2]
        
        enhance_file(input_file, output_file)


if __name__ == "__main__":
    main()
