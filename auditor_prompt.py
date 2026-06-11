"""
AuditBench — All Prompts (arXiv:2506.17282v1)
 
Confirmed by author email (Rushi Wang, June 2026):
  - Temperature: 1.0  (paper used 1.0, NOT 0.0)
  - Models: gpt-3.5-turbo-0125 and gpt-4-0613
  - Standards Citation: LLM uses its own prior knowledge, no external DB.
    The model's generated citation is compared directly against the
    'Standards Citation' field already present in the JSON ground truth.
  - Sample seed: not saved — run on the FULL dataset.
 
All prompt text is reproduced VERBATIM from the paper Appendix pp.7-14.
Do not paraphrase — exact wording is part of the experiment.
"""
 
# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 1 — TABLE-TO-TEXT CONVERSION  (dataset creation only, not evaluation)
# Paper Appendix p.7
# Converts cropped financial statement images → structured [row n] text format.
# ─────────────────────────────────────────────────────────────────────────────
 
TABLE_TO_TEXT_PROMPT = """\
You are a helpful assistant who can help transform table inputs into formmated text. Input a image which shows a \
table, you need to transform it into text obeying the following rules: (1) Start the table with [Tab], together \
with the title of the table, you can also add subtitle if necessary, summarize the table if the name is not \
provided. It should be one of Balance Sheet, Income Statement, Cash Flow Statement or Statement of Changes in \
Equity of the company. (2) The table contains data from multiple years, translate the table year by year, \
seperate the information of each year with a token. This means you should first focus on all the rows for a \
certain year (the year is usually in column) before looking at and transforming the next year. Use a [Time] \
together with the real time shown on table to show the specific time of the data. (3) For each row without \
actual data, input a row with the title, for example: just put 'oprating activities' in a row and then [SEP] \
(4) For data of each year, start each row with [row n], where n is the index of the row of the table. Then \
you sequentially output the content of each line, you should seperate columns with a '|' and use a [SEP] \
token at the end of each line.
 
For example, your output can be something like:
[Tab] Consolidated Balance Sheets from Abbive Inc.
[Time]: September 30, 2023 [SEP] [row 0]: Net sales [SEP] [row 1]: Products | $298,085 [SEP] [row 2]: Services \
| $85,200 [SEP] [row 3]: Total net sales | $383,285 [SEP]
[Time]: September 30, 2024 [SEP] [row 0]: Net sales [SEP] [row 1]: Products | $236,085 [SEP] [row 2]: Services \
| $89,100 [SEP] [row 3]: Total net sales | $386,314 [SEP]
[Time]: September 30, 2025 [SEP] [row 0]: Net sales [SEP] [row 1]: Products | $238,085 [SEP] [row 2]: Services \
| $92,100 [SEP] [row 3]: Total net sales | $389,235 [SEP]
 
Now here is a table from the of the company , remember to directly generate your output. Now let's begin!\
"""
 
 
# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 2 — SYNTHETIC TRANSACTION GENERATION  (dataset creation only)
# Paper Appendix pp.8-9
# Given a financial table, generates realistic transactions summing to each row.
# ─────────────────────────────────────────────────────────────────────────────
 
TRANSACTION_GENERATION_SYSTEM = """\
You are a financial data expert and a helpful assistant in generating synthetic transaction data from consolidated \
financial statements. Based on the input data from the following types of financial statements—Consolidated Income \
Statement, Consolidated Balance Sheet, Consolidated Statement of Cash Flow, and Consolidated Statement of Equity, \
you need to Generate Realistic Transactions that lead to the numbers in the table. The transaction data that you \
generate should follow the following rules: (1) Align logically with the type of financial statement (e.g., revenue \
and expense transactions for income statements, asset and liability transactions for balance sheets, etc.) \
(2) Incorporate relatively plausible amounts and reflect realistic business activities for the specific company. \
(3) Generate event descriptions for each row of the financial statement, there should be several different events \
which contributes to the final number. (4) Generate transaction data row by row, and make sure that the sum of \
the generated scattered transactions is equal to the sum of each item on the financial statements.
 
You need to generate the output in the following format (note that you must repeat the original input as part of \
your output): Input: Here is a [specific financial statements] from the [specific company] [The input of original \
financial table]
 
Output: Transactions: [List of realistic transactions generated based on the input]
 
Now let's begin! Output your transactions which aligns with the table !
Input: { }\
"""
 
 
# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 3 — ERROR INJECTION  (dataset creation only)
# Paper Appendix pp.10-12
# Injects one deliberate error into a correct table and generates all five-stage
# ground truth labels simultaneously.
# ─────────────────────────────────────────────────────────────────────────────
 
ERROR_INJECTION_SYSTEM = """\
You will help generate modified financial statements with specific types of errors for financial auditing purposes. \
Based on the input data from the original financial statement, you need to create a version with deliberate errors, \
as well as identify and explain the errors and provide corrections. The error types are provided as below: \
<1> Missing Row: Delete a row containing a specific account with values (e.g., an account under "Operating \
Activities," "Investing Activities," or "Financing Activities" in the Consolidated Statements of Cash Flows) but \
avoid removing key totals like "Total Revenue," "Total Expenses," "Total Assets," "Total Liabilities," "Total \
Equity," or "Net Cash Provided by Operating/Investing/Financing Activities.". <2> Numerical Error: Modify the \
value of a specific account (e.g., "Accounts Receivable" under Assets) by changing it to an incorrect amount. \
<3> Redundant Row: Add a new row with a logical account name and amount that fits the respective category \
(e.g., adding "Software Licenses" under Assets or "Deferred Revenue" under Liabilities). <4> Misclassification: \
Move a row from one category to another where it logically does not belong (e.g., relocating "Accounts Payable" \
from Liabilities to Assets in the Balance Sheet, or shifting an expense item under Revenue in the Consolidated \
Statement of Income).
 
The outputs should consist of the following components:
"Modified Financial Statement with Errors": Introduce one of the following errors into the financial statement and \
output the changed statement as a table similar to input. You can use any of the type of errors introduced above by \
deleting rows, change a number, add an extra row, or move a row to a wrong place.
"General Judgment": Always output 'Incorrect' as you are introducing errors to the right table.
"Error Identification": Output the error type you have introduced together with the problematic entry row index. \
Generate your results with "Error type"
"Error Resolution": Provide a detailed explanation of the specific error(s), including why it is incorrect. \
For example: "The 'Inventory' item was wrong; it should be $2000, and the calculation should be..", "The 'Accounts \
Liabilities' item was erroneously classified under Assets.", "Receivables (with the amount) was omitted." Then \
explain the error and suggest specific corrections to resolve the error(s). For example: "Accounts Liabilities does \
not belong under Assets; it should be moved to Liabilities." "Add 'Receivables' (with the amount) under Current \
Assets."
"Standards Citation": Cite the relevant Financial Accounting Standards Board (FASB) guidance related to the error, \
including specific references to sections, if applicable.
 
Your task is to generate outputs for each section described above in detail. Make sure the modifications are \
logical, align with accounting principles, and provide concise yet accurate error descriptions.
 
Remember to follow the output format that is provided by the few-shot example. In this round, you need to generate \
the error of {Current error}
Input: "Input Table": {Current Table}
"Transaction data": {Current Transaction}\
"""
 
 
# ─────────────────────────────────────────────────────────────────────────────
# PROMPT 4 — LLM AUDITOR  ← THE MAIN EVALUATION PROMPT
# Paper Appendix pp.13-14
#
# This is the ONLY prompt sent to the model during evaluation.
# Confirmed settings (Rushi Wang email, June 2026):
#   model        : gpt-3.5-turbo-0125  OR  gpt-4-0613
#   temperature  : 1.0
#   Standards Citation: model draws from its own FASB knowledge,
#                       compared against GT 'Standards Citation' field in JSON
# ─────────────────────────────────────────────────────────────────────────────
 
AUDITOR_SYSTEM = """\
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
 
For each pair of input, you need to output your auditing results in the following format:
"General Judgment": Judge whether the table is problematic, output 'correct' if you believe that there is no \
errors, output 'incorrect' if you believe that there is errors. If you output 'correct', there is no need to \
output anything else. If you output 'incorrect', then you need to also output the following for each error you \
have identified. You should always use "Information for error 1" to wrap up your first identified error.
"Error Identification": Output the error type you have identified together with the problematic entry row index, \
for the row index, you should output in the form of 'Row N'.
"Error Resolution": Provide a detailed explanation of the specific error(s), including why it is incorrect.
"Standards Citation": Cite the relevant Financial Accounting Standards Board (FASB) guidance related to the \
error, including specific references to sections, if applicable.
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
{"General Judgment": "Incorrect", "Information for error 1": {"Error Identification": {"Error Type": \
"Misclassification", "Problematic Entry": "Row 8"}, "Error Resolution": "The Financial Statement mistakenly \
wrote accounts receivable, net into non-current assets. Move accounts receivable, net to the current assets item, \
delete it from Non-current assets, and then recalculate the total current assets and total non-current assets \
amounts.", "Standards Citation": "Current assets generally include: Receivables from officers, employees, \
affiliates, and others, if collectible in the ordinary course of business within a year.", "Corrected Statements": \
"[Time]: September 30, 2023 [SEP] [row 0]: Current assets: [SEP] [row 1]: Cash and cash equivalents | $29,965 \
[SEP] ..."}}
 
An example for correct tables: if your output is correct just output: {"General Judgement": "Correct"}
Now, let's begin! Remember to follow the output format directly as json format. Do not output anything else \
except the json output.\
"""
 
# Alias — runner.py imports this name
SYSTEM = AUDITOR_SYSTEM
 
 
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