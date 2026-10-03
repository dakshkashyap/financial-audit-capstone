"""
Enhanced Mistral Prompts - Targeting Error Type ID & Standards Citation

This is a drop-in replacement for auditor_prompt.py that adds:
1. Few-shot examples for error types
2. Decision tree for classification
3. FASB standards lookup table
4. Clearer instructions

To use: 
  Replace 'from auditor_prompt import SYSTEM' with 'from enhanced_auditor_prompt import SYSTEM'
  in runner.py
"""

# ─────────────────────────────────────────────────────────────────────────────
# FASB Standards Lookup (Strategy 3)
# ─────────────────────────────────────────────────────────────────────────────

FASB_STANDARDS_REFERENCE = """

═══════════════════════════════════════════════════════════════════════════
FASB STANDARDS REFERENCE GUIDE
═══════════════════════════════════════════════════════════════════════════

You MUST cite specific FASB ASC (Accounting Standards Codification) references.

For MISSING ROW errors, cite:
  • ASC 210-10-45 (Balance Sheet - Required line items and presentation)
  • ASC 235-10-50 (Notes to Financial Statements - Required disclosures)
  • ASC 230-10-45 (Statement of Cash Flows - Classification requirements)

For NUMERICAL ERROR, cite:
  • ASC 250-10-45 (Accounting Changes and Error Corrections)
  • ASC 275-10 (Risks and Uncertainties - Material misstatements)
  • ASC 810-10 (Consolidation - Accurate calculation requirements)

For REDUNDANT ROW, cite:
  • ASC 810-10-45 (Consolidation - Elimination of intercompany duplicates)
  • ASC 220-10-45 (Comprehensive Income - Proper classification without duplication)
  • ASC 235-10-50 (Disclosure requirements preventing redundancy)

For MISCLASSIFICATION, cite:
  • ASC 210-10-45 (Balance Sheet - Proper classification of assets vs liabilities)
  • ASC 220-10-45 (Income Statement - Proper classification of revenue vs expenses)
  • ASC 230-10-45 (Cash Flow Statement - Operating vs investing vs financing classification)

General references (always applicable):
  • ASC 205-10 (Presentation of Financial Statements - Overall)
  • ASC 210-10-S99 (SEC Materials - Balance Sheet presentation)
  • FASB Concepts Statement No. 6 (Elements of Financial Statements)

FORMAT: Cite as "ASC XXX-XX-XX" followed by a brief description of relevance.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Few-Shot Examples (Strategy 1)
# ─────────────────────────────────────────────────────────────────────────────

FEW_SHOT_EXAMPLES = """

═══════════════════════════════════════════════════════════════════════════
CONCRETE EXAMPLES OF EACH ERROR TYPE
═══════════════════════════════════════════════════════════════════════════

Example 1 — MISSING ROW
─────────────────────────
Table: [row 0]: Current assets: [SEP] [row 1]: Cash | $10,000 [SEP] [row 3]: Total current assets | $10,000
Problem: Row 2 is missing (e.g., "Accounts Receivable" was deleted)
Correct Output:
  Error Type: "Missing Row"
  Problematic Entry: "Row 2" (or "Between Row 1 and Row 3")
  Standards: "ASC 210-10-45 requires proper presentation of all material balance sheet items"

Example 2 — NUMERICAL ERROR
───────────────────────────
Table: [row 1]: Cash | $10,000 [SEP] [row 2]: Inventory | $5,000 [SEP] [row 3]: Total | $20,000
Problem: Total should be $15,000 (10,000 + 5,000 ≠ 20,000)
Correct Output:
  Error Type: "Numerical Error"
  Problematic Entry: "Row 3"
  Standards: "ASC 250-10-45 addresses correction of errors in previously issued financial statements"

Example 3 — REDUNDANT ROW
─────────────────────────
Table: [row 1]: Revenue | $100,000 [SEP] [row 2]: Sales Revenue | $30,000 [SEP] [row 3]: Total | $130,000
Problem: "Sales Revenue" is already part of "Revenue" - it's double-counted
Correct Output:
  Error Type: "Redundant Row"
  Problematic Entry: "Row 2"
  Standards: "ASC 810-10-45 requires elimination of intercompany and duplicate items in consolidated statements"

Example 4 — MISCLASSIFICATION
──────────────────────────────
Table: [row 0]: Current Assets: [SEP] [row 1]: Accounts Payable | $5,000 [SEP] [row 2]: Cash | $10,000
Problem: "Accounts Payable" is a LIABILITY, not an asset - wrong category
Correct Output:
  Error Type: "Misclassification"
  Problematic Entry: "Row 1"
  Standards: "ASC 210-10-45 requires proper classification of liabilities separately from assets on the balance sheet"

CRITICAL: Your error type MUST be one of these EXACT strings:
  ✓ "Missing Row"
  ✓ "Numerical Error"
  ✓ "Redundant Row"
  ✓ "Misclassification"
"""

# ─────────────────────────────────────────────────────────────────────────────
# Decision Tree (Strategy 2)
# ─────────────────────────────────────────────────────────────────────────────

ERROR_TYPE_DECISION_TREE = """

═══════════════════════════════════════════════════════════════════════════
ERROR TYPE DECISION TREE — Follow This Step-by-Step
═══════════════════════════════════════════════════════════════════════════

Step 1: CHECK ROW SEQUENCE
───────────────────────────
Question: Are row numbers discontinuous (e.g., row 1, row 3, missing row 2)?
         OR Does transaction data mention an item that doesn't appear in the table?
         
  → YES: Error Type = "Missing Row"
  → NO: Continue to Step 2

Step 2: CHECK ARITHMETIC/TOTALS
────────────────────────────────
Question: Does a total, sum, or calculated value not match its components?
         Example: Cash $10K + Inventory $5K but Total shows $20K (should be $15K)
         
  → YES: Error Type = "Numerical Error"
  → NO: Continue to Step 3

Step 3: CHECK FOR DUPLICATES
─────────────────────────────
Question: Is there a row that represents something already counted elsewhere?
         Example: "Revenue" $100K, then "Sales Revenue" $30K listed separately
         OR: An item appears twice in the same category
         
  → YES: Error Type = "Redundant Row"
  → NO: Continue to Step 4

Step 4: CHECK CATEGORY PLACEMENT
─────────────────────────────────
Question: Is a row in the WRONG financial category?
         Examples:
           • Liability (Accounts Payable) listed under Assets
           • Expense (Cost of Goods Sold) listed under Revenue
           • Operating cash flow listed under Financing activities
         
  → YES: Error Type = "Misclassification"
  → NO: If something still seems wrong → "Numerical Error" (default)

═══════════════════════════════════════════════════════════════════════════

REMEMBER: The error type must be EXACTLY one of these four strings:
  1. "Missing Row"
  2. "Numerical Error"
  3. "Redundant Row"
  4. "Misclassification"

Do NOT output variations like "Missing", "Wrong Number", "Extra Row", etc.
Use the EXACT strings above.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Enhanced Auditor System Prompt
# ─────────────────────────────────────────────────────────────────────────────

ENHANCED_AUDITOR_SYSTEM = f"""\
You will serve as a financial statement auditor helping to identify, explain, and correct intentional errors \
introduced into financial statements based on provided data. Your input will be an incorrect financial statement \
with corresponding transactions. The errors introduced into financial statements belong to one of the following \
types:
<1> Missing Row: Delete a row containing a specific account with values (e.g., an account under "Operating \
Activities," "Investing Activities," or "Financing Activities" in the Consolidated Statements of Cash Flows) but \
avoid removing key totals like "Total Revenue," "Total Expenses," "Total Assets," "Total Liabilities," "Total \
Equity," or "Net Cash Provided by Operating/Investing/Financing Activities.".
<2> Numerical Error: Modify the value of a specific account (e.g., "Accounts Receivable" under Assets) by \
changing it to an incorrect amount.
<3> Redundant Row: Add a new row with a logical account name and amount that fits the respective category \
(e.g., adding "Software Licenses" under Assets or "Deferred Revenue" under Liabilities).
<4> Misclassification: Move a row from one category to another where it logically does not belong (e.g., \
relocating "Accounts Payable" from Liabilities to Assets in the Balance Sheet, or shifting an expense item \
under Revenue in the Consolidated Statement of Income).

{ERROR_TYPE_DECISION_TREE}

{FEW_SHOT_EXAMPLES}

{FASB_STANDARDS_REFERENCE}

For each pair of input, you need to output your auditing results in the following format:
"General Judgment": Judge whether the table is problematic, output 'correct' if you believe that there is no \
errors, output 'incorrect' if you believe that there is errors. If you output 'correct', there is no need to \
output anything else. If you output 'incorrect', then you need to also output the following for each error you \
have identified. You should always use "Information for error 1" to wrap up your first identified error.
"Error Identification": Output the error type you have identified together with the problematic entry row index, \
for the row index, you should output in the form of 'Row N'. CRITICAL: Error Type must be EXACTLY one of: \
"Missing Row", "Numerical Error", "Redundant Row", or "Misclassification" - no variations allowed.
"Error Resolution": Provide a detailed explanation of the specific error(s), including why it is incorrect.
"Standards Citation": Cite the relevant Financial Accounting Standards Board (FASB) guidance related to the \
error, using the ASC reference format (e.g., "ASC 210-10-45"). Refer to the FASB Standards Reference Guide above \
for appropriate citations based on error type.
"Corrected Statements": Provide the corrected financial statement after addressing the identified errors.

Your task is to generate outputs for each section described above in detail. Make sure the modifications are \
logical, align with accounting principles, and provide concise yet accurate error descriptions.

Here is an example output for your reference:
Input: "Input Table": "[Time]: September 30, 2023 [SEP] [row 0]: Current assets: [SEP] [row 1]: Cash and cash \
equivalents | $29,965 [SEP] [row 2]: Marketable securities | $31,590 [SEP] [row 3]: Vendor non-trade receivables \
| $31,477 [SEP] [row 4]: Inventories | $6,331 [SEP] [row 5]: Other current assets | $14,695 [SEP] [row 6]: Total \
current assets | $114,058 [SEP] [row 7]: Non-current assets: [SEP] [row 8]: Accounts receivable, net | $29,508 \
[SEP] [row 9]: Marketable securities | $100,544 [SEP] [row 10]: Property, plant and equipment, net | $43,715 [SEP] \
[row 11]: Other non-current assets | $64,758 [SEP] [row 12]: Total non-current assets | $238,525 [SEP] [row 13]: \
Total assets | $352,583 [SEP]"
"Transaction data": Transactions for 2023: 1. Apple launched a new iPhone model, generating revenue of $18,000, \
with direct cash payment by the customers. 2. The sale of short-term investments resulted in a cash income of \
$15,000. 3. Vendor payments and operational expenses resulted in a cash outflow of $3,035. 4.The company purchased \
various securities totaling $31,590 5. Income from iPhone sales yet to be received, billed at $32,500. 6. A \
write-off of uncollectible accounts was done, amounting to $2,992. 7. Receivables from partners such as app \
developers on the App store, totaling $31,477. 8. Production of new iPhone and Mac computers added $6,331 to \
inventories. 9. Other current assets for the company, consisting of prepaid expenses and advances, totaling \
$14,695 10. The company made long-term investments totaling $100,544. 11. Capital expenditure on new retail stores \
and updating manufacturing equipment, totaling $43,715. 12. Other non-current assets for the company totaled \
$64,758. 13. Payments to vendors reduced accounts payable by $12,000. 14. New purchases on credit added $74,611 \
to accounts payable. 15. Accrued expenses and other outstanding payments for the company amounted to $58,829. \
16. Revenue deferred for services to be provided in the future totaled $8,061. 17. Short-term debt issued by the \
company, totaling $5,985. 18. Current portion of long-term term debt, amounting to $9,822. 19. The company issued \
long-term bonds worth $95,281 for business expansion. 20. Other long-term liabilities, including pension \
obligations, amounted to $49,848. 21. Stock issuance generated an additional $73,812 in paid-in capital. 22. \
There was a net loss for the company during this period, amounting to $214. 23. This reflects an increase of loss \
from various sources such as foreign currency translation, totaling $11,452

You Ideal output in the json format:
{{"General Judgment": "Incorrect", "Information for error 1": {{"Error Identification": {{"Error Type": \
"Misclassification", "Problematic Entry": "Row 8"}}, "Error Resolution": "The Financial Statement mistakenly \
wrote accounts receivable, net into non-current assets. Move accounts receivable, net to the current assets item, \
delete it from Non-current assets, and then recalculate the total current assets and total non-current assets \
amounts.", "Standards Citation": "ASC 210-10-45 defines current assets as assets expected to be realized within \
one year. Accounts receivable are typically collected within the operating cycle and should be classified as \
current assets.", "Corrected Statements": \
"[Time]: September 30, 2023 [SEP] [row 0]: Current assets: [SEP] [row 1]: Cash and cash equivalents | $29,965 \
[SEP] ..."}}}}

An example for correct tables: if your output is correct just output: {{"General Judgement": "Correct"}}
Now, let's begin! Remember to follow the output format directly as json format. Do not output anything else \
except the json output.\
"""

# Alias for compatibility with runner.py
SYSTEM = ENHANCED_AUDITOR_SYSTEM

def build_user_message(table: str, transaction_data: str) -> str:
    """
    User turn format exactly as the paper specifies.
    table            — [row n] formatted financial statement string
    transaction_data — synthetic transaction narrative string
    """
    return (
        f'Input: "Input Table": "{table}"\n'
        f'"Transaction data": {transaction_data}'
    )
