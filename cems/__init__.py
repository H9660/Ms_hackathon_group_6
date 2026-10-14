"""Campus Event Management System (CEMS) core package.

Layering (each layer may only import from the layers below it):

    ui/*            Streamlit pages                       (Steps 4-7)
    services.py     workflow / state transitions          (Step 3)
    rules.py        business validations                  (Step 2)
    repository.py   data access, dataclass <-> row        (Step 1)
    db.py           SQLite connection, schema, transactions (Step 1)
    models.py       domain types, no dependencies         (Step 1)
"""
