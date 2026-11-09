"""Indicadores P1 a P5, B1 e B2 em pandas, a partir dos DataFrames filtrados de Mato Grosso.

Regras comuns: taxas ponderadas por qt_ingressante; build_groups com menos de 10 alunos são suprimidos;
os resultados descrevem associação estatística, sem alegação de causalidade.
Colunas em minúsculas (ex.: co_curso, qt_ingressante).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_GROUP = 10
UNDERGRAD_DEGREES = ["1", "2", "3"]


def _safe_sum(s: pd.Series):
    return s.sum(min_count=1)  # tudo nulo -> nulo


def _weighted(df: pd.DataFrame, cols: list[str], peso: str, keys: list[str]) -> pd.DataFrame:
    """Média ponderada por `peso` de cada coluna em `cols`, por grupo."""
    w = df[peso].astype("float64")
    aux = df[keys].copy()
    aux["_w"] = w
    for c in cols:
        aux[c] = df[c].astype("float64") * w
    g = aux.groupby(keys, dropna=False, sort=False)
    soma = g[["_w", *cols]].sum()
    return soma[cols].div(soma["_w"], axis=0)


def _course_year(df: pd.DataFrame) -> pd.Series:
    return (df["nu_ano_referencia"] - df["nu_ano_ingresso"] + 1).astype("int64")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").astype("float64")


# ------------------------------------------------------------------ Trajetória
def p1_trajectory(traj: pd.DataFrame) -> pd.DataFrame:
    """Coorte 2015, Presencial, MT, Graduação, 2015-2024: TDA/TCA/TAP/TADA ponderadas por ano."""
    t = traj[
        (traj["co_uf"] == "51") & traj["tp_grau_academico"].isin(UNDERGRAD_DEGREES)
        & (traj["tp_modalidade_ensino"] == "1") & (traj["nu_ano_ingresso"] == 2015)
        & (traj["qt_ingressante"] > 0)
        & traj[["tda", "tca", "tap", "tada"]].notna().all(axis=1)
    ].copy()
    t["ano_do_curso"] = _course_year(t)
    keys = ["nu_ano_ingresso", "nu_ano_referencia", "ano_do_curso"]
    pond = _weighted(t, ["tda", "tca", "tap", "tada"], "qt_ingressante", keys)
    g = t.groupby(keys, sort=False)
    ano = pd.DataFrame({
        "n_cursos": g["co_curso"].nunique(),
        "qt_ingressantes": g["qt_ingressante"].sum(),
        "qt_desistencia_ano": g["qt_desistencia"].apply(_safe_sum),
        "qt_conclusao_ano": g["qt_concluinte"].apply(_safe_sum),
    }).join(pond.add_suffix("_pct")).reset_index()
    ano = ano[ano["qt_ingressantes"] >= MIN_GROUP].sort_values("nu_ano_referencia").reset_index(drop=True)
    return pd.DataFrame({
        "coorte": ano["nu_ano_ingresso"], "ano_referencia": ano["nu_ano_referencia"],
        "ano_do_curso": ano["ano_do_curso"], "n_cursos": ano["n_cursos"],
        "qt_ingressantes": ano["qt_ingressantes"],
        "tda_pct": ano["tda_pct"].round(4), "tca_pct": ano["tca_pct"].round(4), "tap_pct": ano["tap_pct"].round(4),
        "soma_tda_tca_tap_pct": (ano["tda_pct"] + ano["tca_pct"] + ano["tap_pct"]).round(4),
        "qt_desistencia_ano": ano["qt_desistencia_ano"], "qt_conclusao_ano": ano["qt_conclusao_ano"],
        "tada_pct": ano["tada_pct"].round(4),
        "maior_perda_anual": ano["tada_pct"] == ano["tada_pct"].max(),
    })


def p2_dropout_ranking(traj: pd.DataFrame) -> pd.DataFrame:
    """Ranking de TDA por CINE rótulo e área geral: coortes 2015 e 2020 no 5º ano, Presencial."""
    t = traj[
        (traj["co_uf"] == "51") & traj["tp_grau_academico"].isin(UNDERGRAD_DEGREES)
        & (traj["tp_modalidade_ensino"] == "1") & traj["nu_ano_ingresso"].isin([2015, 2020])
        & (traj["qt_ingressante"] > 0) & traj[["tda", "tca", "tap"]].notna().all(axis=1)
    ].copy()
    t = t[_course_year(t) == 5]

    def group_by_level(nivel: str, keys: list[str]) -> pd.DataFrame:
        k = ["nu_ano_ingresso", *keys]
        pond = _weighted(t, ["tda", "tca", "tap"], "qt_ingressante", k)
        g = t.groupby(k, dropna=False, sort=False)
        r = pd.DataFrame({"n_cursos": g["co_curso"].nunique(), "qt_ingressantes": g["qt_ingressante"].sum()})
        r = r.join(pond.add_suffix("_pct")).reset_index()
        r = r[r["qt_ingressantes"] >= MIN_GROUP].copy()
        r.insert(0, "nivel", nivel)
        return r

    rot = ["co_cine_rotulo", "no_cine_rotulo", "co_cine_area_geral", "no_cine_area_geral"]
    u = pd.concat([group_by_level("CINE_ROTULO", rot), group_by_level("CINE_AREA_GERAL", ["co_cine_area_geral", "no_cine_area_geral"])],
                  ignore_index=True).rename(columns={"nu_ano_ingresso": "coorte"})
    u["chave"] = u["co_cine_rotulo"].fillna(u["co_cine_area_geral"])
    part = u.groupby(["nivel", "coorte"])
    u["ranking_desistencia"] = part["tda_pct"].rank(method="min", ascending=False).astype("int64")
    u["n_grupos_ranqueados"] = part["tda_pct"].transform("size").astype("int64")
    u = u.sort_values(["nivel", "chave", "coorte"], kind="stable")
    u["delta"] = (u["tda_pct"] - u.groupby(["nivel", "chave"])["tda_pct"].shift(1)).round(4)
    u = u.sort_values(["nivel", "coorte", "ranking_desistencia", "chave"], kind="stable").reset_index(drop=True)
    u["ano_do_curso"] = 5
    for c in ("tda_pct", "tca_pct", "tap_pct"):
        u[c] = u[c].round(4)
    return u[["nivel", "coorte", "ano_do_curso", *rot, "n_cursos", "qt_ingressantes", "tda_pct", "tca_pct", "tap_pct",
              "ranking_desistencia", "n_grupos_ranqueados"]].assign(delta_tda_pp_vs_coorte_anterior=u["delta"])


# ----------------------------------------------------------------------- Censo
def _network_group(c: pd.DataFrame) -> pd.Series:
    return np.select(
        [c["tp_rede"] == "1", c["tp_categoria_administrativa"] == "4", c["tp_categoria_administrativa"] == "5"],
        ["Pública", "Privada com fins lucrativos", "Privada sem fins lucrativos"],
        default="Privada (outra categoria)",
    )


def _modality(s: pd.Series) -> pd.Series:
    return s.map({"1": "Presencial", "2": "EAD"})


def _pct(num: pd.Series, den: pd.Series, casas: int) -> pd.Series:
    den = den.astype("float64").where(den != 0)
    return (100.0 * num.astype("float64") / den).round(casas)


def p3_census_dropout(censo: pd.DataFrame) -> pd.DataFrame:
    """Evasão anual 2021-2024 = desvinculados / (matriculados + desvinculados + transferidos)."""
    c = censo[(censo["co_uf"] == "51") & (censo["tp_nivel_academico"] == "1") & censo["nu_ano_censo"].between(2021, 2024)]
    k = ["nu_ano_censo", "co_curso", "tp_rede", "tp_categoria_administrativa", "tp_modalidade_ensino"]
    cursos = c.groupby(k, dropna=False).agg(
        qt_mat=("qt_mat", _safe_sum), qt_desvinculado=("qt_sit_desvinculado", _safe_sum),
        qt_transferido=("qt_sit_transferido", _safe_sum)).reset_index()  # EAD: soma os polos de MT por curso
    cursos["grupo_rede"] = _network_group(cursos)
    cursos["modalidade"] = _modality(cursos["tp_modalidade_ensino"])
    cursos["base"] = cursos["qt_mat"] + cursos["qt_desvinculado"] + cursos["qt_transferido"]
    kg = ["nu_ano_censo", "tp_rede", "grupo_rede", "tp_modalidade_ensino", "modalidade"]
    g = cursos.groupby(kg, dropna=False)
    r = g.agg(n_cursos=("co_curso", "nunique"), qt_mat=("qt_mat", _safe_sum), qt_desvinculado=("qt_desvinculado", _safe_sum),
              qt_transferido=("qt_transferido", _safe_sum), base_alunos=("base", _safe_sum)).reset_index()
    r = r[r["base_alunos"] >= MIN_GROUP].copy()
    r["evasao_anual_pct"] = _pct(r["qt_desvinculado"], r["base_alunos"], 4)
    return r.sort_values(["nu_ano_censo", "tp_rede", "grupo_rede", "tp_modalidade_ensino"]).reset_index(drop=True)


def b1_deserts(censo: pd.DataFrame, ibge: pd.DataFrame) -> pd.DataFrame:
    """Vagas presenciais 2024 por 100 jovens de 18-24 anos; municípios sem oferta = deserto."""
    c = censo[(censo["co_uf"] == "51") & (censo["tp_nivel_academico"] == "1")
              & (censo["tp_modalidade_ensino"] == "1") & (censo["nu_ano_censo"] == 2024)]
    v = c.groupby("co_municipio").agg(
        vagas_presenciais_2024=("qt_vg_total", _safe_sum), n_cursos_presenciais=("co_curso", "nunique"),
        n_ies=("co_ies", "nunique")).reset_index()
    r = ibge[["co_municipio", "no_municipio", "pop_18_24"]].merge(v, on="co_municipio", how="left")
    for col in ("vagas_presenciais_2024", "n_cursos_presenciais", "n_ies"):
        r[col] = r[col].fillna(0).astype("int64")
    r["vagas_por_100_jovens"] = _pct(r["vagas_presenciais_2024"], r["pop_18_24"], 2)
    r["deserto"] = r["vagas_presenciais_2024"] == 0
    r = r.sort_values(["deserto", "vagas_por_100_jovens", "co_municipio"], ascending=[False, True, True],
                      na_position="first", kind="stable").reset_index(drop=True)
    return r[["co_municipio", "no_municipio", "pop_18_24", "vagas_presenciais_2024", "n_cursos_presenciais", "n_ies",
              "vagas_por_100_jovens", "deserto"]]


def b2_financing(censo: pd.DataFrame) -> pd.DataFrame:
    """Rede privada, 2021-2024: evasão anual em cursos de alta (>=10%) vs baixa adesão a FIES/ProUni."""
    c = censo[(censo["co_uf"] == "51") & (censo["tp_nivel_academico"] == "1") & (censo["tp_rede"] == "2")
              & censo["nu_ano_censo"].between(2021, 2024)].copy()
    c["qt_ing_financ"] = c["qt_ing_fies"] + c["qt_ing_prounii"] + c["qt_ing_prounip"]
    k = ["nu_ano_censo", "co_curso", "tp_modalidade_ensino"]
    cur = c.groupby(k, dropna=False).agg(
        qt_ing=("qt_ing", _safe_sum), qt_ing_financ=("qt_ing_financ", _safe_sum), qt_mat=("qt_mat", _safe_sum),
        qt_desvinculado=("qt_sit_desvinculado", _safe_sum), qt_transferido=("qt_sit_transferido", _safe_sum)).reset_index()
    cur["prop"] = cur["qt_ing_financ"].astype("float64") / cur["qt_ing"].astype("float64").where(cur["qt_ing"] != 0)
    cur["grupo_adesao"] = np.where(cur["prop"] >= 0.10, "Alta adesão (>=10%)", "Baixa adesão (<10%)")
    cur = cur[cur["prop"].notna() & (cur["prop"] <= 1)].copy()  # sem ingressantes ou >100%: fora
    cur["base"] = cur["qt_mat"] + cur["qt_desvinculado"] + cur["qt_transferido"]
    kg = ["nu_ano_censo", "tp_modalidade_ensino", "grupo_adesao"]
    r = cur.groupby(kg, dropna=False).agg(
        n_cursos=("co_curso", "nunique"), qt_ing=("qt_ing", _safe_sum), qt_ing_financ=("qt_ing_financ", _safe_sum),
        qt_mat=("qt_mat", _safe_sum), qt_desvinculado=("qt_desvinculado", _safe_sum),
        qt_transferido=("qt_transferido", _safe_sum), base_alunos=("base", _safe_sum)).reset_index()
    r = r[r["base_alunos"] >= MIN_GROUP].copy()
    r["modalidade"] = _modality(r["tp_modalidade_ensino"])
    r["prop_financiados_pct"] = _pct(r["qt_ing_financ"], r["qt_ing"], 2)
    bruto = 100.0 * r["qt_desvinculado"].astype("float64") / r["base_alunos"].astype("float64").where(r["base_alunos"] != 0)
    baixa = bruto.where(r["grupo_adesao"] == "Baixa adesão (<10%)")
    ref = baixa.groupby([r["nu_ano_censo"], r["tp_modalidade_ensino"]]).transform("max")
    r["evasao_anual_pct"] = bruto.round(4)
    r["dif_evasao_pp_vs_baixa_adesao"] = (bruto - ref).round(4)
    r = r.sort_values(["nu_ano_censo", "tp_modalidade_ensino", "grupo_adesao"]).reset_index(drop=True)
    return r[["nu_ano_censo", "tp_modalidade_ensino", "modalidade", "grupo_adesao", "n_cursos", "qt_ing", "qt_ing_financ",
              "prop_financiados_pct", "qt_mat", "qt_desvinculado", "qt_transferido", "base_alunos",
              "evasao_anual_pct", "dif_evasao_pp_vs_baixa_adesao"]]


# -------------------------------------------------------------------- Qualidade
def _tda_by_course(traj: pd.DataFrame, graus: list[str], com_coortes: bool) -> pd.DataFrame:
    """TDA no 5º ano de acompanhamento, coortes agrupadas, ponderada por qt_ingressante; >= 10 ingressantes."""
    t = traj[(traj["co_uf"] == "51") & traj["tp_grau_academico"].isin(graus)
             & (traj["qt_ingressante"] > 0) & traj["tda"].notna()]
    t = t[_course_year(t) == 5]
    pond = _weighted(t, ["tda"], "qt_ingressante", ["co_curso"])
    g = t.groupby("co_curso", sort=False)
    r = pd.DataFrame({"qt_ingressantes": g["qt_ingressante"].sum()}).join(pond.rename(columns={"tda": "tda_pct"}))
    if com_coortes:
        r["n_coortes"] = g["nu_ano_ingresso"].nunique()
    return r[r["qt_ingressantes"] >= MIN_GROUP].reset_index()


def _distinct_by_course(df: pd.DataFrame, ordem: list[str], asc: list[bool]) -> pd.DataFrame:
    return df.sort_values(ordem, ascending=asc, na_position="last", kind="stable").drop_duplicates("co_curso")


def _ntile(n: int, k: int) -> np.ndarray:
    base, resto = divmod(n, k)
    tamanhos = [base + 1] * resto + [base] * (k - resto)
    return np.repeat(np.arange(1, k + 1), tamanhos)


def p4_cpc_vs_dropout(traj: pd.DataFrame, cpc: pd.DataFrame) -> pd.DataFrame:
    """CPC (Faixa e Contínuo) x TDA no 5º ano, com correlações de Pearson e Spearman."""
    t = _tda_by_course(traj, UNDERGRAD_DEGREES, com_coortes=True)
    c = cpc[cpc["sg_uf"] == "MT"].copy()
    c["cpc_continuo"] = _num(c["cpc_continuo"])
    c["cpc_faixa"] = _num(c["cpc_faixa"])
    c = c[c["cpc_faixa"].notna() & c["cpc_continuo"].notna()]
    c["qt_concluintes_participantes"] = _num(c["qt_concluintes_participantes"])
    c = _distinct_by_course(c, ["co_curso", "nu_ano_cpc", "qt_concluintes_participantes", "co_municipio"],
                            [True, False, False, True])
    b = c[["co_curso", "cpc_faixa", "cpc_continuo"]].merge(t[["co_curso", "qt_ingressantes", "tda_pct"]], on="co_curso")
    b = b.sort_values("cpc_continuo", kind="stable").reset_index(drop=True)
    b["quartil_cpc"] = _ntile(len(b), 4)
    k = {
        "n_cursos_correlacao": len(b),
        "corr_pearson_cpc_tda": round(float(b["cpc_continuo"].corr(b["tda_pct"])), 4),
        "corr_spearman_cpc_tda": round(float(b["cpc_continuo"].rank().corr(b["tda_pct"].rank())), 4),
    }
    b["_w"] = b["tda_pct"] * b["qt_ingressantes"]

    def build_groups(agrup: str, col: str, rotulo) -> pd.DataFrame:
        g = b.groupby(col)
        r = pd.DataFrame({"n_cursos": g.size(), "qt_ingressantes": g["qt_ingressantes"].sum(),
                          "cpc_continuo_medio": g["cpc_continuo"].mean(), "_w": g["_w"].sum()}).reset_index()
        r["tda_pct"] = r["_w"] / r["qt_ingressantes"]
        r = r[r["qt_ingressantes"] >= MIN_GROUP]
        return pd.DataFrame({"agrupamento": agrup, "grupo": r[col].map(rotulo), "ordem": r[col],
                             "n_cursos": r["n_cursos"], "qt_ingressantes": r["qt_ingressantes"],
                             "cpc_continuo_medio": r["cpc_continuo_medio"].round(4), "tda_pct": r["tda_pct"].round(4)})

    u = pd.concat([build_groups("CPC_FAIXA", "cpc_faixa", lambda v: str(int(v))),
                   build_groups("CPC_CONTINUO_QUARTIL", "quartil_cpc", lambda v: f"Q{int(v)}")], ignore_index=True)
    u = u.sort_values(["agrupamento", "ordem"], ascending=[False, True], kind="stable").drop(columns="ordem")
    for nome, v in k.items():
        u[nome] = v
    return u.reset_index(drop=True)


def p5_teaching_degree_funnel(traj: pd.DataFrame, enade: pd.DataFrame) -> pd.DataFrame:
    """Licenciaturas: TDA x proficiência no Enade 2025 e funil crítico (TDA >= mediana e proficiência < mediana)."""
    t = _tda_by_course(traj, ["2"], com_coortes=False)
    e = enade[enade["sg_uf"] == "MT"].copy()
    e["prop_proficiente_padrao1"] = _num(e["prop_proficiente_padrao1"])
    e["qt_concluintes_participantes"] = _num(e["qt_concluintes_participantes"])
    e = e[e["prop_proficiente_padrao1"].notna() & (e["qt_concluintes_participantes"] >= MIN_GROUP)]
    e = _distinct_by_course(e, ["co_curso", "qt_concluintes_participantes", "co_municipio"], [True, False, True])
    j = e.merge(t, on="co_curso")
    j["prop_proficiente_pct"] = 100.0 * j["prop_proficiente_padrao1"]
    med_tda, med_prof = j["tda_pct"].median(), j["prop_proficiente_pct"].median()
    j["funil_critico"] = (j["tda_pct"] >= med_tda) & (j["prop_proficiente_pct"] < med_prof)
    j["n_cursos_area"] = j.groupby("co_area")["co_curso"].transform("size")
    j["n_cursos_criticos_area"] = j.groupby("co_area")["funil_critico"].transform("sum")
    j = j.sort_values(["n_cursos_criticos_area", "no_area_avaliacao", "funil_critico", "tda_pct", "co_curso"],
                      ascending=[False, True, False, False, True], kind="stable").reset_index(drop=True)
    return pd.DataFrame({
        "co_area": j["co_area"], "no_area_avaliacao": j["no_area_avaliacao"], "co_curso": j["co_curso"],
        "co_ies": j["co_ies"], "sg_ies": j["sg_ies"], "no_modalidade_ensino": j["no_modalidade_ensino"],
        "co_municipio": j["co_municipio"], "no_municipio": j["no_municipio"],
        "qt_ingressantes": j["qt_ingressantes"], "tda_pct": j["tda_pct"].round(4),
        "qt_concluintes_participantes": j["qt_concluintes_participantes"].astype("int64"),
        "qt_proficiente_padrao1": j["qt_proficiente_padrao1"],
        "prop_proficiente_pct": j["prop_proficiente_pct"].round(2), "enade_faixa": j["enade_faixa"],
        "estimativa_proficientes_por_100_ingressantes": ((100 - j["tda_pct"]) * j["prop_proficiente_pct"] / 100.0).round(2),
        "mediana_tda_pct": round(med_tda, 4), "mediana_prop_proficiente_pct": round(med_prof, 2),
        "funil_critico": j["funil_critico"], "n_cursos_area": j["n_cursos_area"].astype("int64"),
        "n_cursos_criticos_area": j["n_cursos_criticos_area"].astype("int64"),
    })
