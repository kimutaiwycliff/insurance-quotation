# imports

Bring an agent's existing book (clients and policies) in from a spreadsheet: **Excel (.xlsx, first sheet)**
or **CSV** (Plan A1.1 R1.5).
- Excel cells become the text an agent would have typed: dates as ISO, whole numbers without ".0", booleans
  as yes/no.
- Formulas are read as their last saved values.
- `openpyxl` runs with `defusedxml`; old `.xls` files are refused with a hint to save as `.xlsx`.

- `POST /imports/policies/preview` reads the file and saves nothing:
  - detects the columns from common headings ("Insured", "Reg No", "Inception Date", "Expiry", "Comm %"...);
  - checks every row: Kenyan dates such as 31/12/2026, amounts such as "KES 38,500", class names matched to
    the jurisdiction pack;
  - matches clients on phone, email, KRA PIN or ID within the file and against the book;
  - skips policies whose insurer and number are already in the book.
- `POST /imports/policies` imports in **one transaction**. If rows have errors, it refuses unless
  `skip_errors` is set. It accepts up to 1,000 rows and 2 MB.
- **Imported policies are existing cover:**
  - activation basis `imported`, linked to the `book_imports` log row (ADR-0019);
  - with `assume_paid` (the default) and no "paid" column, the premium is recorded as paid to the insurer on
    the start date ("Opening balance (import)");
  - commission is set when the file has a rate and a "premium before levies" column.
- `parse.py` holds pure helpers with unit tests (`tests/unit/test_imports_parse.py`).
- Needs `client:write`, plus `premium:write` when payments are recorded.
