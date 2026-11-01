DEPARTMENT_ALIASES = {
    "COM": "CS",
    "SWE": "SE",
    "IFT": "IT",
    "CBS": "CY",
    "CS": "COM",
    "SE": "SWE",
    "IT": "IFT",
    "CY": "CBS",
}


def department_codes(value):
    code = (value or "").strip().upper()
    if not code:
        return []
    alias = DEPARTMENT_ALIASES.get(code)
    return [code, alias] if alias else [code]
