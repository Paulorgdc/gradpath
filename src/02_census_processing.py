"""Censo da Educação Superior (Cursos 2021-2024) + IBGE (SIDRA 9514) -> pandas -> CSVs P3, B1 e B2.

1. Lê cada CSV do Censo em chunks (';', latin-1) e descarta NA LEITURA tudo que não é
   CO_UF='51' (MT) e TP_NIVEL_ACADEMICO='1' (Graduação).
2. Obtém a população de 18-24 anos dos municípios de MT (Censo 2022, SIDRA tabela 9514) e guarda o
   JSON bruto em data/raw/ibge/ (cache).
3. Calcula P3, B1 e B2 com pandas (src/analytics.py) e grava outputs/p3_*.csv, b1_*.csv e b2_*.csv.

Uso:  python src/02_census_processing.py [--raw data/raw/inep_censo_microdados] [--refresh-ibge]
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path

import pandas as pd
import requests

from analytics import b1_deserts, b2_financing, p3_census_dropout
from common import RAW_DIR, ROOT, write_csv_atomic

log = logging.getLogger("datahack.censo")

UF_MT = "51"
UNDERGRAD_LEVEL = "1"
ANOS = (2021, 2022, 2023, 2024)
CHUNK = 100_000

COLS_STR = [  # códigos e rótulos: sempre texto
    "CO_UF", "CO_MUNICIPIO", "NO_MUNICIPIO", "TP_ORGANIZACAO_ACADEMICA", "TP_CATEGORIA_ADMINISTRATIVA",
    "TP_REDE", "CO_IES", "CO_CURSO", "NO_CURSO", "CO_CINE_ROTULO", "NO_CINE_ROTULO",
    "CO_CINE_AREA_GERAL", "NO_CINE_AREA_GERAL", "TP_GRAU_ACADEMICO", "TP_MODALIDADE_ENSINO", "TP_NIVEL_ACADEMICO",
]
COLS_INT = [
    "NU_ANO_CENSO", "QT_VG_TOTAL", "QT_ING", "QT_ING_FIES", "QT_ING_PROUNII", "QT_ING_PROUNIP",
    "QT_MAT", "QT_CONC", "QT_SIT_TRANCADA", "QT_SIT_DESVINCULADO", "QT_SIT_TRANSFERIDO", "QT_SIT_FALECIDO",
]
# Colunas mantidas em memória
COLUMN_ORDER = [
    "NU_ANO_CENSO", "CO_UF", "CO_MUNICIPIO", "NO_MUNICIPIO", "TP_ORGANIZACAO_ACADEMICA",
    "TP_CATEGORIA_ADMINISTRATIVA", "TP_REDE", "CO_IES", "CO_CURSO", "NO_CURSO",
    "CO_CINE_ROTULO", "NO_CINE_ROTULO", "CO_CINE_AREA_GERAL", "NO_CINE_AREA_GERAL",
    "TP_GRAU_ACADEMICO", "TP_MODALIDADE_ENSINO", "TP_NIVEL_ACADEMICO",
    "QT_VG_TOTAL", "QT_ING", "QT_ING_FIES", "QT_ING_PROUNII", "QT_ING_PROUNIP",
    "QT_MAT", "QT_CONC", "QT_SIT_TRANCADA", "QT_SIT_DESVINCULADO", "QT_SIT_TRANSFERIDO", "QT_SIT_FALECIDO",
]

# SIDRA 9514: população residente (v93), Censo 2022; idades 18 anos, 19 anos e 20 a 24 anos.
SIDRA_URL = (
    "https://apisidra.ibge.gov.br/values/t/9514/n6/in%20n3%2051/v/93/p/2022"
    "/c2/6794/c286/113635/c287/6575,6576,93087"
)
IBGE_CACHE = RAW_DIR / "ibge" / "ibge_9514_mt_18_24_2022.json"


# ----------------------------------------------------------------------- Censo
def list_course_csvs(root_dir: Path, anos: tuple[int, ...]) -> dict[int, Path]:
    achados: dict[int, Path] = {}
    for p in root_dir.rglob("*.CSV"):
        m = re.fullmatch(r"MICRODADOS_.*CURSOS_(\d{4})\.CSV", p.name, flags=re.I)
        if m and int(m.group(1)) in anos:
            achados[int(m.group(1))] = p
    faltam = sorted(set(anos) - set(achados))
    if faltam:
        raise SystemExit(f"CSV de Cursos ausente para {faltam} em {root_dir}")
    return dict(sorted(achados.items()))


def read_csv_mt(path: Path) -> pd.DataFrame:
    """Lê em chunks e filtra MT + Graduação por chunk; só o filtrado é acumulado."""
    usar = lambda c: c in COLUMN_ORDER
    partes, lidas = [], 0
    for ch in pd.read_csv(path, sep=";", encoding="latin-1", dtype=str, usecols=usar, chunksize=CHUNK, low_memory=False):
        lidas += len(ch)
        partes.append(ch[(ch["CO_UF"].str.strip() == UF_MT) & (ch["TP_NIVEL_ACADEMICO"].str.strip() == UNDERGRAD_LEVEL)])
    df = pd.concat(partes, ignore_index=True)
    faltam = [c for c in COLUMN_ORDER if c not in df.columns]
    if faltam:
        raise ValueError(f"{path.name}: colunas ausentes {faltam}")
    log.info("censo %s: %s linhas lidas -> %s (MT, Graduação)", path.name, f"{lidas:,}", f"{len(df):,}")
    return df[COLUMN_ORDER]


def load_census(root_dir: Path, anos: tuple[int, ...]) -> pd.DataFrame:
    df = pd.concat([read_csv_mt(p) for p in list_course_csvs(root_dir, anos).values()], ignore_index=True)
    for c in COLS_STR:
        df[c] = df[c].str.strip()
    for c in COLS_INT:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    if set(df["CO_UF"]) != {UF_MT} or set(df["TP_NIVEL_ACADEMICO"]) != {UNDERGRAD_LEVEL}:
        raise ValueError("Filtro falhou: restaram linhas fora de MT/Graduação")
    dup = int(df.duplicated(["NU_ANO_CENSO", "CO_CURSO", "CO_MUNICIPIO"]).sum())
    if dup:
        raise ValueError(f"{dup} linhas duplicadas em (ano, curso, município)")
    log.info("Censo em memória: %s linhas | ~%.1f MB | anos %s", f"{len(df):,}",
             df.memory_usage(deep=True).sum() / 1e6, sorted(df["NU_ANO_CENSO"].unique().tolist()))
    return df


# ------------------------------------------------------------------------ IBGE
def get_population(refresh: bool) -> pd.DataFrame:
    if IBGE_CACHE.exists() and not refresh:
        linhas = json.loads(IBGE_CACHE.read_text(encoding="utf-8"))
        log.info("IBGE: cache %s", IBGE_CACHE.relative_to(ROOT))
    else:
        log.info("IBGE: baixando SIDRA 9514 (MT, 18-24 anos, Censo 2022)")
        r = requests.get(SIDRA_URL, timeout=60)
        r.raise_for_status()
        linhas = r.json()
        IBGE_CACHE.parent.mkdir(parents=True, exist_ok=True)
        IBGE_CACHE.write_text(json.dumps(linhas, ensure_ascii=False), encoding="utf-8")
    campos, dados = linhas[0], linhas[1:]  # a linha 0 é o dicionário de campos
    k_idade = next(k for k, v in campos.items() if v.startswith("Idade (C"))  # posição varia com a URL
    df = pd.DataFrame(
        {"co_municipio": [d["D1C"] for d in dados],
         "no_municipio": [re.sub(r" - MT$", "", d["D1N"]) for d in dados],
         "idade": [d[k_idade] for d in dados], "v": [d["V"] for d in dados]}
    )
    df["v"] = pd.to_numeric(df["v"], errors="coerce")  # '-', 'X', '...' -> NULL
    larga = df.pivot(index=["co_municipio", "no_municipio"], columns="idade", values="v")  # falha se houver duplicata
    larga.columns.name = None
    larga = larga.rename(columns={"6575": "p18", "6576": "p19", "93087": "pop_20_24"}).reset_index()
    larga["pop_18_19"] = larga["p18"] + larga["p19"]
    larga["pop_18_24"] = larga["pop_18_19"] + larga["pop_20_24"]
    larga["nu_ano_censo"] = 2022
    larga["co_municipio"] = larga["co_municipio"].astype(str)
    out = larga[["co_municipio", "no_municipio", "nu_ano_censo", "pop_18_19", "pop_20_24", "pop_18_24"]].copy()
    for c in ["nu_ano_censo", "pop_18_19", "pop_20_24", "pop_18_24"]:
        out[c] = out[c].astype("Int64")
    if not out["co_municipio"].str.startswith(UF_MT).all():
        raise ValueError("IBGE: município fora de MT")
    log.info("IBGE: %d municípios | jovens 18-24 em MT: %s", len(out), f"{int(out['pop_18_24'].sum()):,}")
    return out.sort_values("co_municipio").reset_index(drop=True)


# ---------------------------------------------------------------------- Saídas
def extract(censo: pd.DataFrame, ibge: pd.DataFrame, out: Path) -> None:
    p3 = p3_census_dropout(censo)
    write_csv_atomic(p3, out / "p3_evasao_censo.csv")
    b1 = b1_deserts(censo, ibge)
    write_csv_atomic(b1, out / "b1_desertos_ensino_superior.csv")
    b2 = b2_financing(censo)
    write_csv_atomic(b2, out / "b2_financiamento_permanencia.csv")
    if p3.empty or b1.empty or b2.empty:
        raise RuntimeError("Alguma consulta retornou vazio — verifique a carga.")
    log.info("P3: %d células | B1: %d municípios, %d desertos | B2: %d células",
             len(p3), len(b1), int(b1["deserto"].sum()), len(b2))


# ------------------------------------------------------------------------- Main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(RAW_DIR / "inep_censo_microdados"))
    ap.add_argument("--out", default=str(ROOT / "outputs"))
    ap.add_argument("--anos", type=int, nargs="+", default=list(ANOS))
    ap.add_argument("--refresh-ibge", action="store_true", help="ignora o cache e baixa o SIDRA de novo")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    log.info("[1/3] Leitura e filtro em memória (Censo)")
    censo = load_census(Path(a.raw), tuple(a.anos)).rename(columns=str.lower)
    log.info("[2/3] População IBGE")
    ibge = get_population(a.refresh_ibge)
    log.info("Linhas do Censo sem município no IBGE: %d", int((~censo["co_municipio"].isin(ibge["co_municipio"])).sum()))
    log.info("[3/3] P3, B1 e B2 em pandas")
    extract(censo, ibge, Path(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
