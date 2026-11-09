# Arquitetura

Pipeline em Python + pandas: roda inteiro na máquina local, sem banco, serviço em nuvem ou credencial.

```
data/raw/inep_*/            (Raw, local, fora do Git)
        │  openpyxl / pandas (streaming; filtro MT + Graduação / UF = MT)
        ▼
src/01_trajectory_ingestion.py · 02_census_processing.py · 03_education_quality.py
        │  src/analytics.py (pandas)
        ▼
outputs/*.csv               (versionado)
        ▼
dashboard/                  (Power BI lê os CSVs)
```

## Módulos

| Arquivo | Responsabilidade |
|---|---|
| `src/common.py` | Raiz do projeto, `RAW_DIR` (`data/raw/`) e gravação atômica de CSV (`write_csv_atomic`) |
| `src/analytics.py` | Indicadores P1 a P5, B1 e B2 em pandas, a partir dos DataFrames filtrados |
| `src/01_trajectory_ingestion.py` | Trajetória (INEP): leitura + filtro, P1 e P2 |
| `src/02_census_processing.py` | Censo 2021-2024 em chunks (MT + Graduação) + população 18-24 do SIDRA 9514 (cache em `data/raw/ibge/`): P3, B1 e B2 |
| `src/03_education_quality.py` | CPC 2021-2023 e Enade Licenciaturas 2025 (`Sigla da UF = MT`) cruzados com a Trajetória (lida de novo a partir de `data/raw/inep_trajetoria`): taxa de match, P4 e P5 |

## Indicadores (`src/analytics.py`)

Os filtros (CO_UF='51', Presencial, coortes, 5º ano, grupos >= 10) são literais no código.

| Função | Saída |
|---|---|
| `p1_trajectory` | `p1_trajetoria_2015.csv`: coorte 2015 presencial, TDA/TCA/TAP ponderadas e ano de maior perda |
| `p2_dropout_ranking` | `p2_ranking_desistencia.csv`: ranking por CINE, coortes 2015 vs 2020 no 5º ano, grupos < 10 omitidos |
| `p3_census_dropout` | `p3_evasao_censo.csv`: evasão anual por ano × rede × modalidade |
| `b1_deserts` | `b1_desertos_ensino_superior.csv`: vagas presenciais 2024 por 100 jovens de 18-24 e municípios sem oferta |
| `b2_financing` | `b2_financiamento_permanencia.csv`: evasão na rede privada, alta vs baixa adesão a FIES/ProUni |
| `p4_cpc_vs_dropout` | `p4_cpc_vs_desistencia.csv`: CPC (Faixa e Contínuo) x TDA no 5º ano, com correlações |
| `p5_teaching_degree_funnel` | `p5_funil_licenciaturas.csv`: TDA x proficiência no Enade 2025 e funil crítico por área |

## Execução

```bash
pip install -r requirements.txt
python src/01_trajectory_ingestion.py
python src/02_census_processing.py
python src/03_education_quality.py
```

Opções: `--raw` (pasta dos dados brutos) e `--out` (pasta dos CSVs). O `02_census_processing.py` aceita ainda `--refresh-ibge`; o `03_education_quality.py`, `--traj`.

Decisões e justificativas em `docs/strategy.md`.
