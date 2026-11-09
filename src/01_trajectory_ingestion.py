"""Trajetória (INEP) -> pandas (MT + Graduação) -> CSVs P1 e P2 para o Power BI.

1. Lê as planilhas .xlsx (cabeçalho na linha 9), filtra em memória MT (CO_UF='51') + Graduação
   e mantém códigos como texto.
2. Calcula P1 e P2 com pandas (src/analytics.py) e grava outputs/p1_trajetoria_2015.csv e
   outputs/p2_dropout_ranking.csv (substituição atômica).

Uso:  python src/01_trajectory_ingestion.py [--raw data/raw/inep_trajetoria]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import openpyxl
import pandas as pd

from analytics import p1_trajectory, p2_dropout_ranking
from common import RAW_DIR, ROOT, write_csv_atomic

log = logging.getLogger("datahack.trajetoria")

HEADER_ROW = 9  # linhas 1-8 são metadados
UNDERGRAD_DEGREES = {"1", "2", "3"}  # bacharelado, licenciatura, tecnológico
UF_MT = "51"  # Mato Grosso
MIN_GROUP = 10  # regra do hackathon: build_groups menores são suprimidos

COLUMNS = [
    "CO_IES", "NO_IES", "TP_CATEGORIA_ADMINISTRATIVA", "TP_ORGANIZACAO_ACADEMICA", "CO_CURSO", "NO_CURSO",
    "CO_REGIAO", "CO_UF", "CO_MUNICIPIO", "TP_GRAU_ACADEMICO", "TP_MODALIDADE_ENSINO",
    "CO_CINE_ROTULO", "NO_CINE_ROTULO", "CO_CINE_AREA_GERAL", "NO_CINE_AREA_GERAL",
    "NU_ANO_INGRESSO", "NU_ANO_REFERENCIA", "NU_PRAZO_INTEGRALIZACAO", "NU_ANO_INTEGRALIZACAO",
    "NU_PRAZO_ACOMPANHAMENTO", "NU_ANO_MAXIMO_ACOMPANHAMENTO",
    "QT_INGRESSANTE", "QT_PERMANENCIA", "QT_CONCLUINTE", "QT_DESISTENCIA", "QT_FALECIDO",
    "TAP", "TCA", "TDA", "TCAN", "TADA",
]
COLS_INT = [c for c in COLUMNS if c.startswith(("NU_", "QT_"))]
COLS_DBL = ["TAP", "TCA", "TDA", "TCAN", "TADA"]
PAD = {"CO_UF": 2, "CO_CINE_AREA_GERAL": 2, "CO_CINE_ROTULO": 7}


# ----------------------------------------------------------------- Leitura + filtro
def _cod(v) -> str:
    """Normaliza código vindo da célula (1, 1.0, ' 1 ', '51') para texto sem sufixo decimal."""
    t = str(v).strip()
    return t[:-2] if t.endswith(".0") else t


def list_xlsx_files(root_dir: Path) -> list[Path]:
    return sorted(p for p in root_dir.rglob("*.xlsx") if not p.name.startswith("~$") and "trajetoria" in p.name.lower())


def read_xlsx_mt_undergrad(path: Path, uf: str) -> pd.DataFrame:
    """Streaming do xlsx (cabeçalho na linha 9); descarta na leitura tudo que não é UF/Graduação."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        linhas = wb.worksheets[0].iter_rows(min_row=HEADER_ROW, values_only=True)
        header = [str(h).strip() for h in next(linhas)]
        faltam = [c for c in COLUMNS if c not in header]
        if faltam:
            raise ValueError(f"{path.name}: cabeçalho da linha {HEADER_ROW} sem colunas {faltam}")
        i_uf, i_grau = header.index("CO_UF"), header.index("TP_GRAU_ACADEMICO")
        dados = [
            tuple(None if v is None else str(v).strip() for v in r)
            for r in linhas
            if r[i_uf] is not None and _cod(r[i_uf]).zfill(2) == uf and r[i_grau] is not None and _cod(r[i_grau]) in UNDERGRAD_DEGREES
        ]
    finally:
        wb.close()
    return pd.DataFrame(dados, columns=header, dtype="object")[COLUMNS]


def load_raw(raw: Path, uf: str) -> pd.DataFrame:
    arquivos = list_xlsx_files(raw)
    if not arquivos:
        raise SystemExit(f"Nenhum .xlsx de Trajetória em {raw}")
    if len(arquivos) != 6:
        log.warning("Esperados 6 arquivos (coortes 2015-2020); encontrados %d", len(arquivos))
    partes = []
    for p in arquivos:
        df = read_xlsx_mt_undergrad(p, uf)
        log.info("raw %s -> %s linhas (UF=%s, Graduação)", p.name, f"{len(df):,}", uf)
        partes.append(df)
    df = pd.concat(partes, ignore_index=True)
    for c, n in PAD.items():
        df[c] = df[c].str.zfill(n)
    for c in COLS_INT:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")  # suprimidos/inválidos -> NULL
    for c in COLS_DBL:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # Garantia: nada fora de MT/Graduação sobreviveu ao filtro de leitura.
    if set(df["CO_UF"]) != {uf} or not set(df["TP_GRAU_ACADEMICO"]) <= UNDERGRAD_DEGREES:
        raise ValueError(f"Filtro falhou: UFs={set(df['CO_UF'])}, graus={set(df['TP_GRAU_ACADEMICO'])}")
    key = ["CO_IES", "CO_CURSO", "NU_ANO_INGRESSO", "NU_ANO_REFERENCIA"]
    dup = int(df.duplicated(key).sum())
    if dup:  # EAD/multi-polo: seria preciso agregar por CO_CURSO antes de carregar
        raise ValueError(f"{dup} linhas duplicadas na chave {key}; agregar por CO_CURSO antes da carga")
    log.info("Em memória: %s linhas | ~%.1f MB | coortes %s", f"{len(df):,}",
             df.memory_usage(deep=True).sum() / 1e6, sorted(df["NU_ANO_INGRESSO"].dropna().unique().tolist()))
    return df


# ------------------------------------------------------------------------- Main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(RAW_DIR / "inep_trajetoria"))
    ap.add_argument("--out", default=str(ROOT / "outputs"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    log.info("[1/2] Leitura e filtro em memória")
    traj = load_raw(Path(a.raw), UF_MT).rename(columns=str.lower)
    log.info("[2/2] P1 e P2 em pandas")
    out = Path(a.out)

    p1 = p1_trajectory(traj)
    if p1.empty:
        log.error("P1 sem linhas — os dados estão vazios ou os filtros não casam.")
        return 1
    write_csv_atomic(p1, out / "p1_trajetoria_2015.csv")
    pior = p1[p1["maior_perda_anual"]].iloc[0]
    log.info("P1: maior perda anual no %dº ano do curso (ref. %d): %.2f%% dos ingressantes",
             pior.ano_do_curso, pior.ano_referencia, pior.tada_pct)

    p2 = p2_dropout_ranking(traj)
    write_csv_atomic(p2, out / "p2_ranking_desistencia.csv")
    for (nivel, coorte), g in p2.groupby(["nivel", "coorte"]):
        log.info("P2 %s %s: %d build_groups (>=%d alunos)", nivel, coorte, len(g), MIN_GROUP)
    return 0


if __name__ == "__main__":
    sys.exit(main())
