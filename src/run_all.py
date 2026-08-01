"""Single entry point for this submission (EduMiners).

Running `python src/run_all.py` from the repo root rebuilds every file listed
under `outputs:` in manifest.yml from the raw data, using only:

  - the GP Maths Contest primary data in  ACSEL/Akshara_Data_For Datathon/
  - the district crosswalk           in  ACSEL/district_crosswalk.xlsx
  - NFHS-5 context                    in  data/nfhs/
  - SSLC 2025 Class-10 maths context  in  data/sslc/

Design rules this file follows:
  - Read data with paths relative to the repo root (no absolute machine paths).
  - Fix a random seed for anything that uses randomness, so metrics reproduce.
  - Do not download data or models while running; the judging run is offline
    (the dashboard inlines plotly.js instead of pulling it from a CDN).
  - Finish quickly: the analysis is a handful of pandas group-bys + one OLS.

Outputs written under outputs/:
  tables/district_accuracy.csv          per-district student-weighted accuracy
  tables/score_trend_by_grade_year.csv  mean accuracy by grade x year
  tables/gender_gap.csv                 mean accuracy by grade x year x gender
  tables/competency_accuracy.csv        overall accuracy per competency
  tables/nfhs_correlations.csv          NFHS-5 indicator x grade Spearman r
  tables/sslc_correlations.csv          contest vs SSLC maths pass% Spearman r
  tables/model_metrics.csv              development-index OLS R^2 and coefficient
  tables/district_gap.csv               observed - expected accuracy + segment
  predictions/predictions.csv           per-district observed/expected/gap
  figures/dashboard.html                combined interactive Plotly dashboard
"""

from __future__ import annotations

import glob
import os
import random
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from sklearn.linear_model import LinearRegression

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
ACSEL_DIR = REPO_ROOT / "ACSEL" / "Akshara_Data_For Datathon"
OUTPUTS = REPO_ROOT / "outputs"
TABLES = OUTPUTS / "tables"
FIGURES = OUTPUTS / "figures"
PREDICTIONS = OUTPUTS / "predictions"

# Make `import src.*` work no matter where the entry point is launched from.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.nfhs_district import build_contest_district_nfhs  # noqa: E402
from src.sslc_district import build_contest_district_sslc_maths  # noqa: E402

QUESTION_COLS = [f"Q{i}" for i in range(1, 21)]
GRADE_COLORS = {4: "#636EFA", 5: "#EF553B", 6: "#00CC96"}
# Development index = these three collinear NFHS-5 development indicators.
DEV_FEATURES = [
    "female_ever_school_n5",
    "improved_sanitation_n5",
    "women_10yr_schooling_n5",
]
# NFHS-5 indicators most plausibly linked to early numeracy, for the corr table.
NFHS_FOCUS = [
    "women_10yr_schooling_n5",
    "female_ever_school_n5",
    "child_stunted_n5",
    "child_underweight_n5",
    "child_adequate_diet_n5",
    "improved_sanitation_n5",
    "clean_cooking_fuel_n5",
    "electricity_n5",
    "child_marriage_n5",
    "teen_motherhood_n5",
    "health_insurance_n5",
]


# --------------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------------- #
def _contest_files() -> list[str]:
    return sorted(
        f
        for f in glob.glob(str(ACSEL_DIR / "**" / "*.xlsx"), recursive=True)
        if not os.path.basename(f).startswith("~$")
    )


def load_assessment() -> pd.DataFrame:
    """Combine the 9 contest files (3 grades x 3 years) into one student table."""
    xlsx_files = _contest_files()
    if not xlsx_files:
        raise FileNotFoundError(f"No contest .xlsx files found under {ACSEL_DIR}")

    frames = []
    for f in xlsx_files:
        match = re.search(r"Grade_(\d+)_(\d{4}-\d{2})", f)
        grade, year = int(match.group(1)), match.group(2)
        df = pd.ExcelFile(f).parse("Assessment Data")
        df["grade"] = grade
        df["year"] = year
        frames.append(df)

    assessment = pd.concat(frames, ignore_index=True)
    assessment["score"] = assessment[QUESTION_COLS].sum(axis=1)
    assessment["pct_correct"] = assessment["score"] / len(QUESTION_COLS)
    return assessment


def parse_competency_mapping(xls: pd.ExcelFile) -> pd.DataFrame:
    """Read the (grade/year-specific) Question -> Competency map from one file.

    The header row is detected dynamically because its position differs across
    files (the row containing the literal cell "Questions").
    """
    raw = xls.parse("Competency Mapping", header=None)
    header_mask = raw.apply(
        lambda row: row.astype(str).str.strip().eq("Questions").any(), axis=1
    )
    header_row_idx = header_mask.idxmax()
    header_row = raw.iloc[header_row_idx]
    col_idx = {str(v).strip(): c for c, v in header_row.items() if pd.notna(v)}
    comp = raw.iloc[header_row_idx + 1 :][
        [col_idx["Questions"], col_idx["Question Name"], col_idx["Competency"]]
    ]
    comp.columns = ["Question", "Question Name", "Competency"]
    return comp.dropna(subset=["Question"])


def load_competency() -> pd.DataFrame:
    """Combine every file's Question -> Competency map, tagged by grade/year."""
    frames = []
    for f in _contest_files():
        match = re.search(r"Grade_(\d+)_(\d{4}-\d{2})", f)
        grade, year = int(match.group(1)), match.group(2)
        comp = parse_competency_mapping(pd.ExcelFile(f))
        comp["grade"] = grade
        comp["year"] = year
        frames.append(comp)
    return pd.concat(frames, ignore_index=True)


# --------------------------------------------------------------------------- #
# Analysis (mirrors notebooks/eda.ipynb, nfhs_analysis.ipynb, sslc_analysis.ipynb)
# --------------------------------------------------------------------------- #
def district_accuracy(assessment: pd.DataFrame) -> pd.DataFrame:
    """Student-weighted contest maths accuracy per district (key = contest name)."""
    return (
        assessment.groupby("District")
        .agg(accuracy=("pct_correct", "mean"), n_students=("pct_correct", "size"))
        .reset_index()
        .rename(columns={"District": "contest_district_value"})
    )


def score_trend(assessment: pd.DataFrame) -> pd.DataFrame:
    """Mean accuracy (with quartiles) by grade x year."""
    return (
        assessment.groupby(["grade", "year"])["pct_correct"]
        .describe(percentiles=[0.25, 0.5, 0.75])
        .reset_index()
        .sort_values(["grade", "year"])
    )


def gender_gap(assessment: pd.DataFrame) -> pd.DataFrame:
    """Mean accuracy by grade x year x gender, plus the girls-minus-boys gap."""
    stats = (
        assessment.groupby(["grade", "year", "Gender"])["pct_correct"]
        .mean()
        .reset_index()
    )
    wide = stats.pivot_table(
        index=["grade", "year"], columns="Gender", values="pct_correct"
    ).reset_index()
    if {"female", "male"}.issubset(wide.columns):
        wide["gap_female_minus_male_pp"] = (wide["female"] - wide["male"]) * 100
    return wide


def competency_accuracy(
    assessment: pd.DataFrame, competency: pd.DataFrame
) -> pd.DataFrame:
    """Overall accuracy per competency (all grades/years combined)."""
    long_df = assessment.melt(
        id_vars=["grade", "year"],
        value_vars=QUESTION_COLS,
        var_name="Question",
        value_name="correct",
    )
    merged = long_df.merge(competency, on=["Question", "grade", "year"], how="left")
    out = (
        merged.groupby("Competency")["correct"]
        .agg(accuracy="mean", n_responses="count")
        .reset_index()
        .sort_values("accuracy", ascending=False)
    )
    return out


def nfhs_correlations(assessment: pd.DataFrame, nfhs_ctx: pd.DataFrame) -> pd.DataFrame:
    """Per-grade Spearman r of district accuracy vs NFHS-5 indicators.

    Accuracy is aggregated to the NFHS district grain first, so split contest
    districts sharing one NFHS parent do not pseudo-replicate.
    """
    amap = assessment.merge(
        nfhs_ctx[["contest_district_value", "nfhs_name"]],
        left_on="District",
        right_on="contest_district_value",
        how="left",
    )
    grade_acc = (
        amap.groupby(["nfhs_name", "grade"])
        .agg(accuracy=("pct_correct", "mean"))
        .reset_index()
    )
    nfhs_ind = nfhs_ctx.drop_duplicates("nfhs_name").set_index("nfhs_name")

    rows = []
    for g in sorted(grade_acc["grade"].unique()):
        sub = grade_acc[grade_acc["grade"] == g].merge(
            nfhs_ind[NFHS_FOCUS], left_on="nfhs_name", right_index=True
        )
        for col in NFHS_FOCUS:
            rows.append(
                {
                    "indicator": col.replace("_n5", ""),
                    "grade": int(g),
                    "spearman_r": round(
                        sub["accuracy"].corr(sub[col], method="spearman"), 3
                    ),
                    "n_districts": int(sub[col].notna().sum()),
                }
            )
    return (
        pd.DataFrame(rows)
        .pivot(index="indicator", columns="grade", values="spearman_r")
        .sort_values(by=4, key=lambda s: s.abs(), ascending=False)
        .reset_index()
    )


def development_index_model(
    district_acc: pd.DataFrame, nfhs_ctx: pd.DataFrame
) -> tuple[pd.DataFrame, dict]:
    """Fit accuracy ~ standardized development index; return per-district gaps.

    Returns (district_gap, metrics) where metrics has r2, coef, n_districts.
    """
    enriched = district_acc.merge(nfhs_ctx, on="contest_district_value", how="left")
    dd = enriched.dropna(subset=DEV_FEATURES + ["accuracy"]).copy()

    dev_z = (dd[DEV_FEATURES] - dd[DEV_FEATURES].mean()) / dd[DEV_FEATURES].std()
    dd["dev_index"] = dev_z.mean(axis=1)
    dd["dev_index_z"] = (dd["dev_index"] - dd["dev_index"].mean()) / dd[
        "dev_index"
    ].std()

    X = dd[["dev_index_z"]].to_numpy()
    y = dd["accuracy"].to_numpy()
    model = LinearRegression().fit(X, y)
    dd["expected_accuracy"] = model.predict(X)
    dd["gap"] = dd["accuracy"] - dd["expected_accuracy"]
    r2 = float(model.score(X, y))

    ctx_med = dd["expected_accuracy"].median()
    acc_med = dd["accuracy"].median()

    def _segment(r):
        ctx = "favourable" if r["expected_accuracy"] >= ctx_med else "weak"
        acc = "high" if r["accuracy"] >= acc_med else "low"
        return f"{ctx} context / {acc} accuracy"

    dd["segment"] = dd.apply(_segment, axis=1)

    district_gap = (
        dd[
            [
                "contest_district_value",
                "accuracy",
                "expected_accuracy",
                "gap",
                "dev_index_z",
                *DEV_FEATURES,
                "segment",
                "is_proxy",
            ]
        ]
        .sort_values("gap")
        .reset_index(drop=True)
    )
    metrics = {
        "model": "OLS accuracy ~ standardized development index",
        "n_districts": int(len(dd)),
        "r2": round(r2, 4),
        "std_coef_per_sd": round(float(model.coef_[0]), 4),
        "random_seed": SEED,
    }
    return district_gap, metrics


def sslc_correlations(
    assessment: pd.DataFrame, sslc_maths: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Spearman r of contest maths accuracy vs SSLC 2025 Class-10 maths pass%.

    Returns (corr_table, sslc_join) where corr_table has overall/boys/girls and
    per-grade rho, and sslc_join is the merged district table for plotting.
    """
    acc = district_accuracy(assessment)
    sslc_join = acc.merge(sslc_maths, on="contest_district_value", how="inner")

    rho_overall = sslc_join["accuracy"].corr(
        sslc_join["maths_pass_pct"], method="spearman"
    )
    rho_boys = sslc_join["accuracy"].corr(
        sslc_join["maths_pass_pct_boys"], method="spearman"
    )
    rho_girls = sslc_join["accuracy"].corr(
        sslc_join["maths_pass_pct_girls"], method="spearman"
    )

    rows = [
        {
            "comparison": "overall_pass_pct",
            "grade": "all",
            "spearman_r": round(float(rho_overall), 3),
            "n_districts": len(sslc_join),
        },
        {
            "comparison": "boys_pass_pct",
            "grade": "all",
            "spearman_r": round(float(rho_boys), 3),
            "n_districts": len(sslc_join),
        },
        {
            "comparison": "girls_pass_pct",
            "grade": "all",
            "spearman_r": round(float(rho_girls), 3),
            "n_districts": len(sslc_join),
        },
    ]

    grade_acc = (
        assessment.groupby(["District", "grade"])["pct_correct"]
        .mean()
        .reset_index()
        .rename(
            columns={"District": "contest_district_value", "pct_correct": "accuracy"}
        )
        .merge(
            sslc_maths[["contest_district_value", "maths_pass_pct"]],
            on="contest_district_value",
            how="inner",
        )
    )
    for g in sorted(grade_acc["grade"].unique()):
        sub = grade_acc[grade_acc["grade"] == g]
        rows.append(
            {
                "comparison": "overall_pass_pct",
                "grade": int(g),
                "spearman_r": round(
                    float(
                        sub["accuracy"].corr(sub["maths_pass_pct"], method="spearman")
                    ),
                    3,
                ),
                "n_districts": len(sub),
            }
        )
    return pd.DataFrame(rows), sslc_join


# --------------------------------------------------------------------------- #
# Figures + dashboard
# --------------------------------------------------------------------------- #
def fig_score_trend(trend: pd.DataFrame) -> go.Figure:
    grades = sorted(trend["grade"].unique())
    fig = make_subplots(
        rows=1,
        cols=len(grades),
        subplot_titles=[f"Grade {g}" for g in grades],
        shared_yaxes=True,
        horizontal_spacing=0.06,
    )
    for i, g in enumerate(grades, start=1):
        sub = trend[trend["grade"] == g]
        color = GRADE_COLORS.get(g, "#AB63FA")
        fig.add_trace(
            go.Scatter(
                x=sub["year"],
                y=sub["mean"],
                mode="lines+markers+text",
                line=dict(color=color, width=3),
                marker=dict(size=10),
                text=[f"{v:.1%}" for v in sub["mean"]],
                textposition="top center",
                showlegend=False,
                hovertemplate="Year %{x}<br>Mean %{y:.1%}<extra></extra>",
            ),
            row=1,
            col=i,
        )
    fig.update_yaxes(tickformat=".0%", title_text="Percent correct", row=1, col=1)
    fig.update_layout(
        template="plotly_white",
        title="Contest accuracy trend by grade across school years",
        width=1050,
        height=420,
        margin=dict(t=80),
    )
    return fig


def fig_gender_gap(gap: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if {"female", "male"}.issubset(gap.columns):
        for gender, color in (("male", "#636EFA"), ("female", "#EF553B")):
            gg = gap.groupby("year")[gender].mean().reset_index()
            fig.add_trace(
                go.Scatter(
                    x=gg["year"],
                    y=gg[gender],
                    mode="lines+markers",
                    name=gender,
                    line=dict(color=color, width=3),
                    marker=dict(size=10),
                )
            )
    fig.update_yaxes(tickformat=".0%", title_text="Percent correct")
    fig.update_layout(
        template="plotly_white",
        title="Mean accuracy by gender across school years",
        width=800,
        height=420,
        margin=dict(t=80),
        legend_title="Gender",
    )
    return fig


def fig_nfhs_corr(corr: pd.DataFrame) -> go.Figure:
    grades = [c for c in corr.columns if isinstance(c, (int, np.integer))]
    long_df = corr.melt(
        id_vars="indicator",
        value_vars=grades,
        var_name="grade",
        value_name="spearman_r",
    )
    order = corr["indicator"].tolist()[::-1]
    fig = go.Figure()
    for g in grades:
        d = long_df[long_df["grade"] == g]
        fig.add_trace(
            go.Bar(
                y=d["indicator"],
                x=d["spearman_r"],
                orientation="h",
                name=f"Grade {g}",
                marker_color=GRADE_COLORS.get(int(g), "#AB63FA"),
                hovertemplate=f"Grade {g}<br>%{{y}}<br>r = %{{x:.2f}}<extra></extra>",
            )
        )
    fig.add_vline(x=0, line_width=1.5, line_color="black")
    fig.update_yaxes(categoryorder="array", categoryarray=order)
    fig.update_xaxes(title_text="Spearman r with district accuracy", range=[-0.7, 0.7])
    fig.update_layout(
        template="plotly_white",
        barmode="group",
        title="District accuracy vs NFHS-5 context, by grade",
        width=950,
        height=620,
        margin=dict(t=80, l=180),
        legend_title="Grade",
    )
    return fig


def fig_district_gap(district_gap: pd.DataFrame) -> go.Figure:
    gs = district_gap.sort_values("gap")
    colors = ["#2ca02c" if v >= 0 else "#d62728" for v in gs["gap"]]
    labels = [
        d + (" *" if p else "")
        for d, p in zip(gs["contest_district_value"], gs["is_proxy"])
    ]
    fig = go.Figure(
        go.Bar(
            y=labels,
            x=gs["gap"],
            orientation="h",
            marker_color=colors,
            customdata=gs[["accuracy", "expected_accuracy"]].values,
            hovertemplate=(
                "%{y}<br>Gap %{x:+.1%}<br>Accuracy %{customdata[0]:.1%}"
                "<br>Expected %{customdata[1]:.1%}<extra></extra>"
            ),
        )
    )
    fig.add_vline(x=0, line_width=1.5, line_color="black")
    fig.update_xaxes(
        title_text="Accuracy gap vs development-index benchmark", tickformat="+.0%"
    )
    fig.update_layout(
        template="plotly_white",
        title="Which districts beat or miss their development benchmark?"
        " (* = NFHS proxy)",
        width=950,
        height=760,
        margin=dict(t=80, l=170),
    )
    return fig


def fig_sslc_scatter(sslc_join: pd.DataFrame, rho_overall: float) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=sslc_join["maths_pass_pct"],
            y=sslc_join["accuracy"],
            mode="markers+text",
            text=sslc_join["contest_district_value"],
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(
                size=12,
                color=sslc_join["maths_gender_gap_pp"],
                colorscale="Tealrose",
                cmid=10,
                colorbar=dict(title="SSLC gap<br>(G-B, pp)"),
            ),
            hovertemplate=(
                "%{text}<br>Contest %{y:.1%}<br>SSLC pass %{x:.1%}<extra></extra>"
            ),
        )
    )
    b, a = np.polyfit(sslc_join["maths_pass_pct"], sslc_join["accuracy"], 1)
    xs = np.array(
        [sslc_join["maths_pass_pct"].min(), sslc_join["maths_pass_pct"].max()]
    )
    fig.add_trace(
        go.Scatter(
            x=xs,
            y=a + b * xs,
            mode="lines",
            line=dict(color="black", dash="dash", width=1.5),
            name="OLS fit",
            hoverinfo="skip",
        )
    )
    fig.update_xaxes(title_text="SSLC 2025 Class-10 maths pass%", tickformat=".0%")
    fig.update_yaxes(title_text="Contest maths accuracy (grades 4-6)", tickformat=".0%")
    fig.update_layout(
        template="plotly_white",
        showlegend=False,
        title=f"Contest accuracy vs SSLC maths pass% (Spearman rho = {rho_overall:+.2f})",
        width=880,
        height=640,
        margin=dict(t=80),
    )
    return fig


def write_dashboard(figs: list[go.Figure], path: Path) -> None:
    """Write one self-contained, offline HTML holding every figure.

    plotly.js is inlined into the first figure (include_plotlyjs=True) so the
    file works with no internet access during judging; later figures reuse it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    parts = [
        "<html><head><meta charset='utf-8'>",
        "<title>EduMiners - Karnataka GP Maths Contest dashboard</title>",
        "</head><body>",
        "<h1 style='font-family:sans-serif'>EduMiners &mdash; Karnataka "
        "rural maths learning dashboard</h1>",
    ]
    for i, fig in enumerate(figs):
        parts.append(
            fig.to_html(full_html=False, include_plotlyjs=(True if i == 0 else False))
        )
    parts.append("</body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> None:
    for d in (TABLES, FIGURES, PREDICTIONS):
        d.mkdir(parents=True, exist_ok=True)

    print("Loading contest primary data ...")
    assessment = load_assessment()
    competency = load_competency()
    print(
        f"  assessment rows: {len(assessment):,} | "
        f"districts: {assessment['District'].nunique()}"
    )

    print("Loading NFHS-5 and SSLC context ...")
    nfhs_ctx = build_contest_district_nfhs()
    sslc_maths = build_contest_district_sslc_maths()

    # --- Descriptive tables -------------------------------------------------
    acc = district_accuracy(assessment)
    trend = score_trend(assessment)
    gap = gender_gap(assessment)
    comp_acc = competency_accuracy(assessment, competency)
    nfhs_corr = nfhs_correlations(assessment, nfhs_ctx)

    acc.to_csv(TABLES / "district_accuracy.csv", index=False)
    trend.to_csv(TABLES / "score_trend_by_grade_year.csv", index=False)
    gap.to_csv(TABLES / "gender_gap.csv", index=False)
    comp_acc.to_csv(TABLES / "competency_accuracy.csv", index=False)
    nfhs_corr.to_csv(TABLES / "nfhs_correlations.csv", index=False)

    # --- Development-index diagnostic model ---------------------------------
    district_gap, metrics = development_index_model(acc, nfhs_ctx)
    district_gap.to_csv(TABLES / "district_gap.csv", index=False)
    pd.DataFrame([metrics]).to_csv(TABLES / "model_metrics.csv", index=False)
    district_gap[
        ["contest_district_value", "accuracy", "expected_accuracy", "gap", "segment"]
    ].to_csv(PREDICTIONS / "predictions.csv", index=False)

    # --- SSLC cross-board correlation ---------------------------------------
    sslc_corr, sslc_join = sslc_correlations(assessment, sslc_maths)
    sslc_corr.to_csv(TABLES / "sslc_correlations.csv", index=False)
    rho_overall = float(
        sslc_corr.loc[
            sslc_corr["comparison"].eq("overall_pass_pct")
            & sslc_corr["grade"].eq("all"),
            "spearman_r",
        ].iloc[0]
    )

    overall_acc = float(np.average(acc["accuracy"], weights=acc["n_students"]))
    print(f"  overall student-weighted accuracy: {overall_acc:.1%}")
    print(f"  development-index OLS R^2: {metrics['r2']} (n={metrics['n_districts']})")
    print(f"  SSLC Spearman (overall): {rho_overall:+.3f} (n={len(sslc_join)})")

    # --- Dashboard ----------------------------------------------------------
    print("Building dashboard ...")
    figs = [
        fig_score_trend(trend),
        fig_gender_gap(gap),
        fig_nfhs_corr(nfhs_corr),
        fig_sslc_scatter(sslc_join, rho_overall),
        fig_district_gap(district_gap),
    ]
    write_dashboard(figs, FIGURES / "dashboard.html")

    print("Done. Outputs written under outputs/.")


if __name__ == "__main__":
    main()
