# Team Name: EduMiners

EduMiners diagnoses foundational rural-mathematics gaps across Karnataka's 31
districts by triangulating the Akshara GP Maths Contest with district development
(NFHS-5) and Class-10 board (SSLC 2025) outcomes, then benchmarks each district
against its development context to flag where school-side action has the most
headroom.

## Team

- Team name: EduMiners
- Members: <add member names>
- Track(s) addressed: Data Insights & Visualization / Predictive Analytics
- Contact email: <add contact email>
- Language used: Python

## AI and LLM use is restricted

AI or LLM tools (ChatGPT, Claude, Copilot, Gemini, and so on) must not be used
to generate your analysis, findings, report, slides, or policy recommendations.
The analytical and written work must be your team's own.

The only tolerated use is basic coding assistance, such as editor autocomplete
or looking up syntax and error messages. It must not extend to producing the
analysis or the written deliverables.

Reports and notes are checked for signs of AI generation, and all numbers are
independently fact-checked. Submissions that appear substantially AI-generated
may be disqualified.

## What's in this repo

| File / folder | Purpose |
|---|---|
| `report.pdf` | Main findings report (replace the placeholder) |
| `slides.pptx` | Your filled-in 12-slide solution deck |
| `docs/policy_note.pdf` | Recommendations note |
| `src/run_all.py` | Single entry point. Running this reproduces everything in `outputs/` |
| `src/nfhs_district.py`, `src/sslc_district.py` | Build district-level NFHS-5 and SSLC context tables used by the pipeline |
| `requirements.txt` | Packages needed to run the entry point |
| `manifest.yml` | Lists every file your submission produces |
| `claims.json` | Every factual or numeric claim in your report, with how it can be checked |
| `outputs/` | Generated tables, figures, dashboard, and predictions |
| `Dockerfile` | Optional. Containerizes your entry point for a reproducibility bonus |

## How to run this

```bash
pip install -r requirements.txt
python src/run_all.py
```

This rebuilds everything under `outputs/` from scratch, reading the dataset from `./data/`.

## Rules (please read)

- **Language:** Python or R. Provide exactly one entry point (`src/run_all.py` or `src/run_all.R`) with packages pinned.
- **Data:** use only the dataset the organizers give you, plus any external data you list in `manifest.yml`. External data must be public and must not contain personal records. Read the data from `./data/`. Never commit the dataset, because the repo is public.
- **Reproducibility:** use relative paths, not absolute machine paths. Fix a random seed for any model that uses randomness. Do not download data or models while your code runs, because the judging run is offline.
- **Runtime:** your entry point should finish in about 3 minutes. If you train a heavy model, save the result and commit it instead of training again during the run.

## Dashboard rules (read before you build)

- **Code-based dashboards only.** Build with Plotly/Dash, Streamlit, Bokeh, Altair/Vega, Observable, or plain HTML/JS, so `src/run_all.py` rebuilds it and it exports to `outputs/figures/dashboard.html`.
- **Tableau and Power BI are not accepted** for the dashboard. The pipeline cannot run or check `.twbx`/`.pbix` files, so they will not count toward the Visualisation and presentation score.
- **Never upload the dataset to any public service** (Tableau Public, Power BI "publish to web", public Google Sheets, and so on). The data contains student assessment records, and publishing it risks re-identifying real children. Doing so disqualifies that data product.

## Notes for reviewers

- **Primary data:** Akshara GP Maths Contest — ~1.38M student sittings, grades 4–6, 2022–23 to 2024–25, across 31 districts. Q1–Q20 (0/1) are scored into `pct_correct`.
- **External data (listed in `manifest.yml`):** NFHS-5 district health/development indicators and SSLC 2025 Class-10 maths pass rates, bridged to contest districts via a district crosswalk.
- **Reproducibility:** `python src/run_all.py` rebuilds every table, figure, prediction, and the offline dashboard under `outputs/` from `./data/`. Random seed is fixed at 42.
- **Headline numbers:** overall student-weighted accuracy 53.1%; development-index OLS R² = 0.43 (n = 31); SSLC maths Spearman ρ = +0.57. The residual gap flags under-performing districts (e.g. chitradurga −12.8 pp).
- **Key caveats:** NFHS/SSLC links are ecological (district-level, not student-level); the SSLC cohort differs from the contest cohort by roughly 4–6 years; some coastal districts have small sample sizes.
