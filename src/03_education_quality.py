"""Indicadores de Qualidade do INEP (CPC 2021-2023, Enade Licenciaturas 2025) -> pandas -> CSVs P4 e P5.

1. Lê as planilhas .xlsx em streaming (cabeçalho na linha 1) e descarta na leitura tudo que não é
   'Sigla da UF' = 'MT'. Códigos (curso, IES, município) são texto; '--', 'SC' (Sem Conceito) e
   vazios viram NULL, nunca zero.
2. Lê a Trajetória (mesma leitura de src/01_trajectory_ingestion.py), registra a taxa de match por
   co_curso e calcula P4 e P5 com pandas (src/analytics.py), gravando outputs/p4_cpc_vs_desistencia.csv
   e outputs/p5_funil_licenciaturas.csv.

Uso:  python src/03_education_quality.py [--raw data/raw/inep_indicadores_qualidade] [--traj data/raw/inep_trajetoria]
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import re
import sys
import unicodedata
from pathlib import Path

import openpyxl
import pandas as pd

from analytics import p4_cpc_vs_desistencia, p5_funil_licenciaturas
from common import RAW_DIR, ROOT, gravar_csv

log = logging.getLogger("datahack.qualidade")

UF = "MT"
NULOS = {"", "--", "-", "SC", "S/C", "NA", "N/A", "ND", "*", "NAN", "NONE"}  # Sem Conceito / sem dado

# Cabeçalho normalizado (sem acento, minúsculo, sem pontuação) -> coluna do DataFrame.
COMUNS = [
    (r"^ano$", "nu_ano"), (r"^codigo da area$", "co_area"), (r"^area de avaliacao$", "no_area_avaliacao"),
    (r"^grau academico$", "no_grau_academico"), (r"^codigo da ies$", "co_ies"), (r"^nome da ies$", "no_ies"),
    (r"^sigla da ies$", "sg_ies"), (r"^organizacao academica$", "no_organizacao_academica"),
    (r"^categoria administrativa$", "no_categoria_administrativa"), (r"^codigo do curso$", "co_curso"),
    (r"^modalidade de ensino$", "no_modalidade_ensino"), (r"^codigo do municipio$", "co_municipio"),
    (r"^municipio do curso$", "no_municipio"), (r"^sigla da uf$", "sg_uf"),
    (r"^no de concluintes inscritos$", "qt_concluintes_inscritos"),
    (r"^no de concluintes participantes$", "qt_concluintes_participantes"),
]
MAP_CPC = COMUNS + [
    (r"^nota padronizada fg$", "nota_padronizada_fg"), (r"^nota padronizada ce$", "nota_padronizada_ce"),
    (r"^conceito enade continuo$", "conceito_enade_continuo"), (r"^nota padronizada idd$", "nota_padronizada_idd"),
    (r"^nota padronizada organizacao", "nota_padronizada_org_didatico"),
    (r"^nota padronizada infraestrutura", "nota_padronizada_infraestrutura"),
    (r"^nota padronizada oportunidade", "nota_padronizada_oportunidade"),
    (r"^nota padronizada mestres$", "nota_padronizada_mestres"),
    (r"^nota padronizada doutores$", "nota_padronizada_doutores"),
    (r"^nota padronizada regime", "nota_padronizada_regime"),
    (r"^cpc continuo$", "cpc_continuo"), (r"^cpc faixa$", "cpc_faixa"),
]
MAP_ENADE = COMUNS + [
    (r"^total de concluinte igual", "qt_proficiente_padrao1"),
    (r"^percentual de concluintes igual", "prop_proficiente_padrao1"),
    (r"^conceito enade faixa$", "enade_faixa"), (r"^cebas$", "in_cebas"),
]

# Ordem das colunas
ORD_CPC = [
    "nu_ano_cpc", "co_area", "no_area_avaliacao", "no_grau_academico", "co_ies", "no_ies", "sg_ies",
    "no_organizacao_academica", "no_categoria_administrativa", "co_curso", "no_modalidade_ensino", "co_municipio",
    "no_municipio", "sg_uf", "qt_concluintes_inscritos", "qt_concluintes_participantes", "nota_padronizada_fg",
    "nota_padronizada_ce", "conceito_enade_continuo", "nota_padronizada_idd", "nota_padronizada_org_didatico",
    "nota_padronizada_infraestrutura", "nota_padronizada_oportunidade", "nota_padronizada_mestres",
    "nota_padronizada_doutores", "nota_padronizada_regime", "cpc_continuo", "cpc_faixa", "in_sem_conceito",
]
ORD_ENADE = [
    "nu_ano_enade", "co_area", "no_area_avaliacao", "no_grau_academico", "co_ies", "no_ies", "sg_ies",
    "no_organizacao_academica", "no_categoria_administrativa", "co_curso", "no_modalidade_ensino", "co_municipio",
    "no_municipio", "sg_uf", "qt_concluintes_inscritos", "qt_concluintes_participantes", "qt_proficiente_padrao1",
    "prop_proficiente_padrao1", "enade_faixa", "in_sem_conceito", "in_cebas",
]
TXT = ["co_area", "no_area_avaliacao", "no_grau_academico", "co_ies", "no_ies", "sg_ies", "no_organizacao_academica",
       "no_categoria_administrativa", "co_curso", "no_modalidade_ensino", "co_municipio", "no_municipio", "sg_uf", "in_cebas"]
INTS = ["nu_ano_cpc", "nu_ano_enade", "qt_concluintes_inscritos", "qt_concluintes_participantes", "qt_proficiente_padrao1",
        "cpc_faixa", "enade_faixa"]


# ---------------------------------------------------------------------- Leitura
def _norm(h: object) -> str:
    t = unicodedata.normalize("NFKD", str(h)).encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)  # tira asteriscos, notas de rodapé e pontuação
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r" \d$", "", t)  # nota de rodapé no fim ('Sigla da IES ¹' -> 'sigla da ies 1')


def _limpa(v: object) -> str | None:
    """Célula -> texto; marcadores de sem conceito/sem dado -> None."""
    if v is None:
        return None
    t = str(v).strip()
    if t.endswith(".0") and t[:-2].lstrip("-").isdigit():
        t = t[:-2]
    return None if t.upper() in NULOS else t


def ler_xlsx_mt(path: Path, mapa: list[tuple[str, str]]) -> pd.DataFrame:
    """Streaming do xlsx (cabeçalho na linha 1); só linhas com Sigla da UF = MT entram na memória."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        linhas = wb.worksheets[0].iter_rows(values_only=True)
        header = [_norm(h) for h in next(linhas)]
        idx: dict[str, int] = {}
        for rx, col in mapa:
            achado = [i for i, h in enumerate(header) if re.search(rx, h)]
            if achado:
                idx[col] = achado[0]
        for obrig in ("nu_ano", "co_curso", "co_ies", "co_municipio", "sg_uf"):
            if obrig not in idx:
                raise ValueError(f"{path.name}: coluna '{obrig}' não encontrada em {header[:15]}")
        i_uf = idx["sg_uf"]
        dados = [
            {c: _limpa(r[i]) for c, i in idx.items()}
            for r in linhas
            if r[i_uf] is not None and str(r[i_uf]).strip().upper() == UF
        ]
    finally:
        wb.close()
    return pd.DataFrame(dados, dtype="object")


def _numeros(df: pd.DataFrame, cols: list[str]) -> None:
    for c in cols:
        if c in df:  # decimal com vírgula (CPC 2022) e valores textuais viram número ou NULL
            df[c] = pd.to_numeric(df[c].astype("string").str.replace(",", ".", regex=False), errors="coerce")


def _finalizar(df: pd.DataFrame, ordem: list[str], faixa: str, continuos: list[str]) -> pd.DataFrame:
    df["co_municipio"] = df["co_municipio"].str.zfill(7)
    # in_sem_conceito: faixa sem número (SC/--). Valores contínuos desses cursos são NULL, não zero
    # (alguns arquivos gravam 0 no lugar do conceito).
    df["in_sem_conceito"] = df[faixa].isna() | (pd.to_numeric(df[faixa], errors="coerce").isna())
    _numeros(df, [c for c in df.columns if c.startswith(("nota_", "conceito_", "cpc_c", "prop_"))])
    sem = df["in_sem_conceito"]
    for c in continuos:
        if c in df:
            df.loc[sem, c] = pd.NA
    _numeros(df, INTS)
    for c in INTS:
        if c in df:
            df[c] = df[c].round().astype("Int64")
    for c in ordem:
        if c not in df:
            df[c] = pd.NA
    return df[ordem]


def carregar_cpc(raiz: Path) -> pd.DataFrame:
    partes = []
    for p in sorted(raiz.glob("*.xlsx")):
        m = re.fullmatch(r"cpc_(2021|2022|2023)\.xlsx", p.name, flags=re.I)
        if not m:
            continue
        df = ler_xlsx_mt(p, MAP_CPC)
        log.info("cpc %s: %d cursos de MT", p.name, len(df))
        partes.append(df)
    if len(partes) != 3:
        raise SystemExit(f"Esperados CPC_2021, cpc_2022 e CPC_2023 em {raiz}; achados {len(partes)}")
    df = pd.concat(partes, ignore_index=True).rename(columns={"nu_ano": "nu_ano_cpc"})
    df = _finalizar(df, ORD_CPC, "cpc_faixa", ["cpc_continuo", "conceito_enade_continuo"])
    _validar(df, ["nu_ano_cpc", "co_curso", "co_municipio"], "CPC")
    log.info("CPC: %d linhas MT | sem conceito: %d | anos %s", len(df), int(df["in_sem_conceito"].sum()),
             sorted(df["nu_ano_cpc"].dropna().unique().tolist()))
    return df


def carregar_enade(raiz: Path) -> pd.DataFrame:
    p = raiz / "conceito_enade_licenciaturas.xlsx"
    if not p.exists():
        raise SystemExit(f"{p} não encontrado")
    df = ler_xlsx_mt(p, MAP_ENADE).rename(columns={"nu_ano": "nu_ano_enade"})
    df = _finalizar(df, ORD_ENADE, "enade_faixa", ["prop_proficiente_padrao1"])
    # Edição especial 2025: o 'Percentual' é proporção (0 a 1); se vier em % (>1), converte.
    if (df["prop_proficiente_padrao1"].dropna() > 1).any():
        df["prop_proficiente_padrao1"] = df["prop_proficiente_padrao1"] / 100
    _validar(df, ["nu_ano_enade", "co_curso", "co_municipio"], "Enade")
    log.info("Enade licenciaturas: %d linhas MT | sem conceito: %d | anos %s", len(df),
             int(df["in_sem_conceito"].sum()), sorted(df["nu_ano_enade"].dropna().unique().tolist()))
    return df


def _validar(df: pd.DataFrame, chave: list[str], nome: str) -> None:
    if set(df["sg_uf"]) != {UF}:
        raise ValueError(f"{nome}: restaram UFs fora de MT: {set(df['sg_uf'])}")
    dup = int(df.duplicated(chave).sum())
    if dup:
        raise ValueError(f"{nome}: {dup} linhas duplicadas em {chave}")


# ------------------------------------------------------------------- Match / saída
def carregar_trajetoria(raw: Path) -> pd.DataFrame:
    """Reaproveita a leitura de src/01_trajectory_ingestion.py (MT + Graduação)."""
    spec = importlib.util.spec_from_file_location("trajectory_ingestion", Path(__file__).with_name("01_trajectory_ingestion.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.carregar_raw(raw, mod.UF_MT).rename(columns=str.lower)


def logar_match(traj: pd.DataFrame, cpc: pd.DataFrame, enade: pd.DataFrame) -> None:
    cursos_traj = set(traj["co_curso"])
    cursos_lic = set(traj.loc[traj["tp_grau_academico"] == "2", "co_curso"])
    cpc_cursos = set(cpc["co_curso"])
    cpc_c = set(cpc.loc[cpc["cpc_faixa"].notna(), "co_curso"])
    en = set(enade["co_curso"])
    pct = lambda a, b: f"{100 * a / b:.1f}%" if b else "n/a"
    n1, n2, n3 = len(cpc_cursos & cursos_traj), len(cpc_c & cursos_traj), len(en & cursos_lic)
    log.info("MATCH P4 (CPC x Trajetória, via co_curso): %d/%d cursos casaram (%s); %d ficaram de fora",
             n1, len(cpc_cursos), pct(n1, len(cpc_cursos)), len(cpc_cursos) - n1)
    log.info("MATCH P4 (só cursos com conceito CPC): %d/%d casaram (%s); %d de fora",
             n2, len(cpc_c), pct(n2, len(cpc_c)), len(cpc_c) - n2)
    log.info("MATCH P5 (Enade Licenciaturas x Trajetória grau 2): %d/%d cursos casaram (%s); %d de fora",
             n3, len(en), pct(n3, len(en)), len(en) - n3)


def extrair(traj: pd.DataFrame, cpc: pd.DataFrame, enade: pd.DataFrame, out: Path) -> None:
    p4 = p4_cpc_vs_desistencia(traj, cpc)
    p5 = p5_funil_licenciaturas(traj, enade)
    gravar_csv(p4, out / "p4_cpc_vs_desistencia.csv")
    gravar_csv(p5, out / "p5_funil_licenciaturas.csv")
    if p4.empty or p5.empty:
        raise RuntimeError("P4 ou P5 sem linhas — verifique a carga e o match com a Trajetória.")
    k = p4.iloc[0]
    log.info("P4: %d cursos na correlação | Pearson=%s | Spearman=%s", k.n_cursos_correlacao,
             k.corr_pearson_cpc_tda, k.corr_spearman_cpc_tda)
    log.info("P5: %d licenciaturas analisadas | %d em funil crítico", len(p5), int(p5["funil_critico"].sum()))


# ------------------------------------------------------------------------- Main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", default=str(RAW_DIR / "inep_indicadores_qualidade"))
    ap.add_argument("--traj", default=str(RAW_DIR / "inep_trajetoria"))
    ap.add_argument("--out", default=str(ROOT / "outputs"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    log.info("[1/3] Leitura e filtro em memória (UF = MT)")
    cpc, enade = carregar_cpc(Path(a.raw)), carregar_enade(Path(a.raw))
    traj = carregar_trajetoria(Path(a.traj))
    log.info("[2/3] Taxa de match com a Trajetória")
    logar_match(traj, cpc, enade)
    log.info("[3/3] P4 e P5 em pandas")
    extrair(traj, cpc, enade, Path(a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
