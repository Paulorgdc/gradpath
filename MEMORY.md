# MEMORY — DataHack
Scripts Python com pandas que filtram os microdados educacionais de Mato Grosso (CO_UF = 51) e geram os CSVs de saída para o Power BI. Sem banco de dados.

## Stack
- Python · pandas, openpyxl, requests

## Comandos
- `python -m venv .venv` · `.venv\Scripts\activate` · `pip install -r requirements.txt`
- `python src/01_trajectory_ingestion.py` → `02_census_processing.py` → `03_education_quality.py` (gravam `outputs/*.csv`)

## Estrutura
- `src/common.py` (`RAW_DIR = data/raw/`, gravação atômica de CSV) · `src/analytics.py` (indicadores P1 a P5, B1, B2)
- `data/raw/` (microdados e censos brutos, fora do Git) · `outputs/` (CSVs em português lidos pelo Power BI) · `dashboard/Rota_do_Diploma.pbix`
- `docs/architecture.md` · `docs/strategy.md`

## Regras de ouro
1. Pré-filtro em memória (MT + Graduação) na leitura dos brutos; nada é gravado além dos CSVs.
2. Sem variáveis de ambiente: os caminhos são constantes apontando para `data/raw/`.
3. Taxas ponderadas por `qt_ingressante`; grupos com menos de 10 alunos são suprimidos.
