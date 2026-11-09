"""Utilidades comuns: raiz do projeto, pasta de dados brutos e gravação atômica de CSV."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"  # microdados e censos brutos (não versionados)
log = logging.getLogger("datahack.common")


def gravar_csv(df: pd.DataFrame, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    try:
        df.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\n")
        os.replace(tmp, destino)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("Gravado %s (%d linhas)", destino.relative_to(ROOT), len(df))
