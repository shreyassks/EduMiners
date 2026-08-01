# data/ folder: put the organizer dataset here (never commit it)

This folder is where your code reads the datathon dataset from.

Everything in this folder is git-ignored on purpose. The repository is public,
and the dataset contains individual student assessment records. Committing it
(or any file made from it that still holds individual rows) would publicly
expose real children's data, and it disqualifies your submission.

## How to use it

1. Download the dataset from the NAS server/
2. Put the files in this `data/` folder on your own machine.
3. Have your `src/run_all.py` (or `src/run_all.R`) read from `./data/` using
   relative paths, not absolute paths like `C:\Users\...` or `/home/...`.

When judges run your code, they will put the same dataset into this folder
before running your entry point, so relative paths to `./data/` will work.

## Folder layout

Supplementary/context data is organised by category:

- `data/nfhs/` — NFHS-5 health & social context
  - `NFHS-5-KA-Karnataka.csv` (long format, KA districts; used by `src/nfhs_district.py`)
  - `NFHS-Health-Data.csv` (compact KA health table; not wired into code)
  - `datafile.csv` (wide, all-India NFHS district table; not wired into code)
- `data/sslc/` — SSLC (Class-10 board) 2025 results
  - `SSLCEXAM-1PROFORMAAPRIL2025.xlsx` (KSEAB proforma; used by `src/sslc_district.py`)
  - `2025_SSLC_Exam_1_100_percent_Secured_Schools_List.pdf`
  - `2025_SSLC_Exam_1_Zero_Percent_Secured_Schools_List.pdf`
- `data/udise/` — UDISE+ school supply-side indicators (KA, education districts),
  one file per dataset × academic year (2019-20, 2020-21, 2021-22); used by
  `src/udise_district.py`
  - `ptr_{year}.xlsx` — Pupil-Teacher Ratio by level
  - `dropout_{year}.xlsx` — Dropout Rate by gender, level & social category
  - `infrastructure_{year}.xlsx` — Number of Schools by availability of
    infrastructure & facilities
