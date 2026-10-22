"""Best-effort parsing of Indian bank / UPI debit and credit alerts. Returns None when unsure,
so a misparse can never silently move money numbers."""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_AMT = r"(?:rs\.?|inr|₹)\s*([\d,]+(?:\.\d{1,2})?)"
_DEBIT = re.compile(r"\b(debited|spent|paid|sent|withdrawn|purchase|payment of)\b", re.I)
_CREDIT = re.compile(r"\b(credited|received|deposited|refund(?:ed)?)\b", re.I)
_BAL = re.compile(r"(?:avl\.?|available|total)?\s*bal(?:ance)?\.?\s*(?:is|:|-)?\s*" + _AMT, re.I)
_VENDOR = re.compile(r"\b(?:to|at|towards|vpa|info:?)\s+([A-Za-z0-9@._&' -]{2,32}?)(?=\s+(?:on|ref|upi|avl|bal|via|from|a/c)\b|[.,;]|$)",
                     re.I)


def _num(s: str) -> float:
    return float(s.replace(",", ""))


def parse_alert(text: str) -> Optional[Dict[str, Any]]:
    t = " ".join(text.split())
    bal_m = _BAL.search(t)
    t_wo_bal = t[:bal_m.start()] + t[bal_m.end():] if bal_m else t
    amt = re.search(_AMT, t_wo_bal, re.I)
    d, c = _DEBIT.search(t_wo_bal), _CREDIT.search(t_wo_bal)
    if not amt or bool(d) == bool(c):
        return None
    v = _VENDOR.search(t_wo_bal)
    return {"direction": "debit" if d else "credit", "amount": _num(amt.group(1)),
            "balance": _num(bal_m.group(1)) if bal_m else None,
            "vendor": (v.group(1).strip().lower() if v else ""),
            "channel": "upi" if re.search(r"\bupi\b", t, re.I) else "bank"}
