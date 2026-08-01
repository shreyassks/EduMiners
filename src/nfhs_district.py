from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
NFHS_CSV = REPO_ROOT / "data" / "nfhs" / "NFHS-5-KA-Karnataka.csv"
CROSSWALK_XLSX = REPO_ROOT / "ACSEL" / "district_crosswalk.xlsx"

ENRICHMENT_INDICATORS: dict[int, str] = {
    1: "female_ever_school",
    15: "women_10yr_schooling",
    73: "child_stunted",
    74: "child_wasted",
    76: "child_underweight",
    72: "child_adequate_diet",
    78: "women_low_bmi",
    9: "improved_sanitation",
    10: "clean_cooking_fuel",
    7: "electricity",
    8: "improved_water",
    12: "health_insurance",
    16: "child_marriage",
    18: "teen_motherhood",
    19: "menstrual_hygiene",
    4: "sex_ratio_at_birth",
    3: "sex_ratio_total",
    2: "population_under_15",
}


def load_crosswalk_mapping() -> pd.DataFrame:
    """Return the contest-district -> NFHS-district mapping from the crosswalk.

    Columns: contest_district_value, standard_district, nfhs_name (the base NFHS
    district name to join on), is_proxy (True when a proxy district is used).
    Rows with "(no contest row)" placeholders (Bengaluru Urban, Shivamogga) are
    dropped because the contest has no data for them.
    """
    cw = pd.read_excel(CROSSWALK_XLSX, sheet_name="District Crosswalk")
    cw = cw[["contest_district_value", "standard_district", "nfhs_join_name"]].copy()
    cw = cw[~cw["contest_district_value"].str.contains(r"\(no contest row\)", na=False)]

    nfhs_districts = set(pd.read_csv(NFHS_CSV)["District"].unique())

    def base_name(text: str) -> str:
        # Strip trailing parentheticals like " (sum with '...')" or " (partial only)".
        return re.sub(r"\s*\(.*\)\s*$", "", str(text)).strip()

    # First pass: names that already match an NFHS district.
    cw["nfhs_name"] = cw["nfhs_join_name"].map(base_name)
    cw["is_proxy"] = False

    resolved = dict(
        zip(
            cw.loc[
                cw["nfhs_name"].isin(nfhs_districts), "standard_district"
            ].str.lower(),
            cw.loc[cw["nfhs_name"].isin(nfhs_districts), "nfhs_name"],
        )
    )
    for idx, row in cw.iterrows():
        if row["nfhs_name"] in nfhs_districts:
            continue
        text = str(row["nfhs_join_name"]).lower()
        for std_lower, nfhs_name in resolved.items():
            token = std_lower.split()[0]  # e.g. "ballari"
            if token and token in text:
                cw.at[idx, "nfhs_name"] = nfhs_name
                cw.at[idx, "is_proxy"] = True
                break

    unresolved = cw.loc[
        ~cw["nfhs_name"].isin(nfhs_districts), "contest_district_value"
    ].tolist()
    if unresolved:
        raise ValueError(f"Could not map these contest districts to NFHS: {unresolved}")

    return cw[["contest_district_value", "standard_district", "nfhs_name", "is_proxy"]]


def load_nfhs_indicators() -> pd.DataFrame:
    """Return the 18 enrichment indicators per NFHS district (old names).

    One row per NFHS district; for each indicator two columns:
    "<name>_n5" (NFHS-5 level) and "<name>_delta" (NFHS-5 minus NFHS-4).
    """
    ka = pd.read_csv(NFHS_CSV)
    ka["ind_num"] = ka["Indicator"].str.split(".").str[0].astype(int)
    ka = ka[ka["ind_num"].isin(ENRICHMENT_INDICATORS)].copy()
    ka["name"] = ka["ind_num"].map(ENRICHMENT_INDICATORS)
    ka["delta"] = ka["NFHS-5"] - ka["NFHS-4"]

    level = ka.pivot(index="District", columns="name", values="NFHS-5")
    level.columns = [f"{c}_n5" for c in level.columns]
    delta = ka.pivot(index="District", columns="name", values="delta")
    delta.columns = [f"{c}_delta" for c in delta.columns]
    return level.join(delta).reset_index().rename(columns={"District": "nfhs_name"})


def build_contest_district_nfhs() -> pd.DataFrame:
    """Return NFHS enrichment indicators keyed by the contest district value.

    Ready to join to district-aggregated contest accuracy on
    `contest_district_value`.
    """
    mapping = load_crosswalk_mapping()
    nfhs = load_nfhs_indicators()
    out = mapping.merge(nfhs, on="nfhs_name", how="left")
    return out


if __name__ == "__main__":
    table = build_contest_district_nfhs()
    pd.set_option("display.width", 200)
    print(f"Contest districts mapped: {len(table)}")
    print(
        f"Proxy districts: {table.loc[table['is_proxy'], 'contest_district_value'].tolist()}"
    )
    print(
        table[
            [
                "contest_district_value",
                "nfhs_name",
                "is_proxy",
                "women_10yr_schooling_n5",
                "child_stunted_n5",
                "clean_cooking_fuel_delta",
            ]
        ].to_string(index=False)
    )
