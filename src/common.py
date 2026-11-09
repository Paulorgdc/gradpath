"""Utilidades comuns: root_dir do projeto, pasta de dados brutos e gravação atômica de CSV."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"  # microdados e censos brutos (não versionados)
log = logging.getLogger("datahack.common")


def write_csv_atomic(df: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    try:
        df.to_csv(tmp, index=False, encoding="utf-8", lineterminator="\n")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    log.info("Gravado %s (%d linhas)", dest.relative_to(ROOT), len(df))
