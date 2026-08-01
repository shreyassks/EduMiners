from __future__ import annotations

from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
SSLC_XLSX = REPO_ROOT / "data" / "sslc" / "SSLCEXAM-1PROFORMAAPRIL2025.xlsx"
CROSSWALK_XLSX = REPO_ROOT / "ACSEL" / "district_crosswalk.xlsx"

# Sheet + fixed column layout of the MATHS block in the KSEAB proforma.
MATHS_SHEET = "PRO-2A(2)"
DATA_START_ROW = 7  # rows 0-6 are titles + the multi-row header
COL_CODE = 1
COL_NAME = 2
# (appeared, passed) column indices for boys and girls within the MATHS block.
COL_BOYS_APPRD, COL_BOYS_PASS = 9, 10
COL_GIRLS_APPRD, COL_GIRLS_PASS = 12, 13

# The only crosswalk gap: the source sheet leaves CHIKKODI's code cell blank, so
# `belagavi chikkodi` has no `sslc_dist_code(s)`. Resolve it by SSLC name.
CONTEST_TO_SSLC_NAME_FALLBACK: dict[str, str] = {
    "belagavi chikkodi": "CHIKKODI",
}


def load_sslc_maths() -> pd.DataFrame:
    """Return SSLC 2025 district-level mathematics results, one row per SSLC
    education district.

    Columns: sslc_dist_code, sslc_district_name, maths_appeared, maths_passed,
    maths_pass_pct (overall), maths_pass_pct_boys, maths_pass_pct_girls,
    maths_gender_gap_pp (girls - boys, percentage points).
    """
    raw = pd.read_excel(SSLC_XLSX, sheet_name=MATHS_SHEET, header=None)
    body = raw.iloc[DATA_START_ROW:].copy()

    name = body[COL_NAME].astype("string").str.strip()
    # Keep real district rows: a district name present and not the TOTAL row.
    keep = name.notna() & ~name.str.upper().eq("TOTAL")
    body = body[keep]

    num = lambda col: pd.to_numeric(body[col], errors="coerce")
    out = pd.DataFrame(
        {
            "sslc_dist_code": body[COL_CODE].astype("string").str.strip(),
            "sslc_district_name": body[COL_NAME].astype("string").str.strip(),
            "boys_appeared": num(COL_BOYS_APPRD),
            "boys_passed": num(COL_BOYS_PASS),
            "girls_appeared": num(COL_GIRLS_APPRD),
            "girls_passed": num(COL_GIRLS_PASS),
        }
    ).reset_index(drop=True)

    out["maths_appeared"] = out["boys_appeared"] + out["girls_appeared"]
    out["maths_passed"] = out["boys_passed"] + out["girls_passed"]
    out["maths_pass_pct"] = out["maths_passed"] / out["maths_appeared"]
    out["maths_pass_pct_boys"] = out["boys_passed"] / out["boys_appeared"]
    out["maths_pass_pct_girls"] = out["girls_passed"] / out["girls_appeared"]
    out["maths_gender_gap_pp"] = (
        out["maths_pass_pct_girls"] - out["maths_pass_pct_boys"]
    ) * 100

    return out


def load_crosswalk_sslc_mapping() -> pd.DataFrame:
    """Return the contest-district -> SSLC-district bridge from the crosswalk.

    Columns: contest_district_value, standard_district, sslc_dist_code.
    "(no contest row)" placeholders and multi-code sum rows (Bengaluru Urban =
    "AS + AN") are dropped. `belagavi chikkodi` (blank code in the source) is
    resolved by name later in build_contest_district_sslc_maths().
    """
    cw = pd.read_excel(CROSSWALK_XLSX, sheet_name="District Crosswalk")
    cw = cw[["contest_district_value", "standard_district", "sslc_dist_code(s)"]].copy()
    cw = cw[~cw["contest_district_value"].str.contains(r"\(no contest row\)", na=False)]

    code = cw["sslc_dist_code(s)"].astype("string").str.strip()
    # Drop composite "AS + AN (sum)"-style entries (they belong to no-contest rows).
    code = code.where(~code.str.contains(r"\+", na=False))
    cw["sslc_dist_code"] = code
    return cw[["contest_district_value", "standard_district", "sslc_dist_code"]]


def build_contest_district_sslc_maths() -> pd.DataFrame:
    """Return SSLC 2025 mathematics results keyed by the contest district value.

    Ready to join to district-aggregated contest maths accuracy on
    `contest_district_value`. Each contest district maps 1:1 to a distinct SSLC
    education district. Contest districts with no matching SSLC row are EXCLUDED.
    """
    maths = load_sslc_maths()
    mapping = load_crosswalk_sslc_mapping()

    by_code = maths.dropna(subset=["sslc_dist_code"]).set_index("sslc_dist_code")
    by_name = maths.set_index(maths["sslc_district_name"].str.upper())

    records = []
    for _, row in mapping.iterrows():
        contest = row["contest_district_value"]
        code = row["sslc_dist_code"]
        match = None
        if pd.notna(code) and code in by_code.index:
            match = by_code.loc[code]
        elif contest in CONTEST_TO_SSLC_NAME_FALLBACK:
            sslc_name = CONTEST_TO_SSLC_NAME_FALLBACK[contest].upper()
            if sslc_name in by_name.index:
                match = by_name.loc[sslc_name]
        if match is None:
            continue  # no SSLC data for this district -> exclude it
        records.append(
            {
                "contest_district_value": contest,
                "standard_district": row["standard_district"],
                **match.drop(labels=[]).to_dict(),
            }
        )

    out = pd.DataFrame.from_records(records)
    return out


if __name__ == "__main__":
    table = build_contest_district_sslc_maths()
    pd.set_option("display.width", 200)
    print(f"Contest districts with SSLC maths data: {len(table)}")
    print(
        table[
            [
                "contest_district_value",
                "sslc_district_name",
                "maths_appeared",
                "maths_pass_pct",
                "maths_gender_gap_pp",
            ]
        ]
        .sort_values("maths_pass_pct")
        .to_string(index=False)
    )
