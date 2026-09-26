"""DHIS2 export: the monthly facility report as a DHIS2 `dataValueSets` payload.

India's HMIS (and the national health information systems of 80+ countries, including several
BRICS members) run on DHIS2, so this is the integration path that needs no custom connector:
POST the payload to <dhis2>/api/dataValueSets?dataElementIdScheme=CODE&orgUnitIdScheme=CODE
after importing the data elements from `metadata()` once. Org units are identified by the
facility's HMIS NIN; periods use DHIS2's monthly format (YYYYMM).
"""
from . import auth, service
from .reference import DRUGS

FOOTFALL = [("PHCP_OPD_TOTAL", "OPD attendance (total)", "opd"),
            ("PHCP_FEVER_CASES", "Fever cases", "fever"),
            ("PHCP_DIARRHOEA_CASES", "Diarrhoea cases", "diarrhoea"),
            ("PHCP_ARI_CASES", "Acute respiratory infection cases", "respiratory"),
            ("PHCP_DAYS_REPORTED", "Days with a daily report", "days_reported")]
STOCK = [("RECEIVED", "received", "received"), ("CONSUMED", "consumed", "dispensed"),
         ("CLOSING", "closing balance", "closing"), ("STOCKOUT_DAYS", "stock-out days", "stockout_days")]


def metadata() -> dict:
    """Data elements to create in DHIS2 once (importable via /api/metadata)."""
    des = [{"code": c, "name": f"PHC Pulse - {n}", "shortName": n[:50], "valueType": "INTEGER_ZERO_OR_POSITIVE",
            "aggregationType": "SUM", "domainType": "AGGREGATE"} for c, n, _ in FOOTFALL]
    for d in DRUGS:
        for suffix, label, _ in STOCK:
            des.append({"code": f"PHCP_{d['code']}_{suffix}", "name": f"PHC Pulse - {d['name']} {label}",
                        "shortName": f"{d['code']} {label}"[:50], "valueType": "INTEGER_ZERO_OR_POSITIVE",
                        "aggregationType": "LAST" if suffix == "CLOSING" else "SUM", "domainType": "AGGREGATE"})
    return {"dataElements": des,
            "dataSets": [{"code": "PHCP_MONTHLY", "name": "PHC Pulse monthly facility report",
                          "periodType": "Monthly", "dataSetElements": [{"dataElement": {"code": e["code"]}} for e in des]}]}


def data_value_set(month: str, scope: dict) -> dict:
    stock, foot = service.monthly_hmis(month)
    period = month.replace("-", "")
    values, seen = [], set()
    for s in stock:
        if not auth.in_scope(scope, s):
            continue
        if s["code"] not in seen:          # footfall once per facility
            seen.add(s["code"])
            f = foot.get(s["code"], {})
            for code, _, key in FOOTFALL:
                if f.get(key) is not None:
                    values.append({"dataElement": code, "period": period, "orgUnit": s["nin"],
                                   "value": str(round(f[key]))})
        for suffix, _, key in STOCK:
            v = s[key] if s[key] is not None else 0
            values.append({"dataElement": f"PHCP_{s['drug_code']}_{suffix}", "period": period,
                           "orgUnit": s["nin"], "value": str(max(0, round(v)))})
    return {"dataSet": "PHCP_MONTHLY", "period": period, "dataValues": values,
            "_import": "POST to /api/dataValueSets?dataElementIdScheme=CODE&orgUnitIdScheme=CODE"
                       "&dataSetIdScheme=CODE"}
