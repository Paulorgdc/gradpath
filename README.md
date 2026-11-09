# 🎓 DATAHACK: Mato Grosso Higher Education Trajectory & Dropout Analytics

A Python/Pandas pipeline that turns raw Inep/MEC microdata into dropout and retention indicators for higher education in Mato Grosso, ready for Power BI.

[![Category](https://img.shields.io/badge/CATEGORY-ACADEMIC%20PROJECT-e0004d?style=for-the-badge)](#)[![UNIVAG](https://img.shields.io/badge/UNIVAG-DATAHACK%202026-00c8ff?style=for-the-badge)](#)[![License](https://img.shields.io/badge/LICENSE-MIT-76b900?style=for-the-badge)](#)

---

## 📌 Project Overview

DATAHACK was built for the UNIVAG DataHack 2026 challenge *Rota do Diploma*. It analyzes the trajectory of undergraduate students in Mato Grosso (`CO_UF = 51`) using official Inep/MEC data: the Higher Education Census, the Student Trajectory indicators, and the CPC/Enade quality indicators, complemented by IBGE population data.

The pipeline filters the raw files in memory, computes the indicators with Pandas, and writes deterministic CSVs to `outputs/` for the Power BI dashboard. Results describe statistical association, not causality, and groups with fewer than 10 students are suppressed.

---

## ⚡ Tech Stack

- **Language:** Python 3
- **Data processing:** Pandas, OpenPyXL, Requests
- **Visualization:** Power BI (`dashboard/Rota_do_Diploma.pbix`)
- **Data sources:** Inep (Census, Trajectory, CPC, Enade), IBGE SIDRA table 9514

---

## 🔍 Key Analytical Findings

| ID | Question | Output |
|---|---|---|
| **P1** | At which year of the course do students drop out the most (2015 cohort)? | `p1_trajetoria_2015.csv` |
| **P2** | Which fields of study (CINE) rank highest in dropout in the 5th year, 2015 vs 2020 cohorts? | `p2_ranking_desistencia.csv` |
| **P3** | How does annual dropout vary across the 2021-2024 Census, by year, network and modality? | `p3_evasao_censo.csv` |
| **P4** | Is a better CPC score associated with lower dropout? (Pearson and Spearman) | `p4_cpc_vs_desistencia.csv` |
| **P5** | Where does the teaching-degree (licenciatura) funnel break: high dropout combined with low Enade proficiency? | `p5_funil_licenciaturas.csv` |
| **B1** | Which municipalities are higher-education deserts (seats per 100 young people aged 18-24)? | `b1_desertos_ensino_superior.csv` |
| **B2** | Does financing (FIES/ProUni) relate to retention in private institutions? | `b2_financiamento_permanencia.csv` |

---

## 🏗️ Data Pipeline Architecture

```
data/raw/  (Inep spreadsheets and CSVs, not versioned)
   │  01_trajectory_ingestion.py · 02_census_processing.py · 03_education_quality.py
   │  read + filter MT / undergraduate in memory
   ▼
src/analytics.py  (Pandas indicators)
   ▼
outputs/*.csv  (atomic writes)  ──►  dashboard/Rota_do_Diploma.pbix
```

| Path | Role |
|---|---|
| `src/common.py` | Project paths (`RAW_DIR = data/raw/`) and atomic CSV writing |
| `src/analytics.py` | Indicators P1 to P5, B1 and B2 |
| `docs/architecture.md`, `docs/strategy.md` | Architecture and analytical decisions |

---

## 🛠️ Installation & Execution

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Paulorgdc/datahack-grupo6.git
   cd datahack-grupo6
   ```
2. **Create the environment and install dependencies:**
   ```bash
   python -m venv .venv
   .venv\Scripts\activate      # Windows
   pip install -r requirements.txt
   ```
3. **Place the raw Inep files under `data/raw/`** (`inep_trajetoria/`, `inep_censo_microdados/`, `inep_indicadores_qualidade/`).
4. **Run the pipeline:**
   ```bash
   python src/01_trajectory_ingestion.py
   python src/02_census_processing.py
   python src/03_education_quality.py
   ```
5. **Open `dashboard/Rota_do_Diploma.pbix`** in Power BI and refresh from `outputs/`.
