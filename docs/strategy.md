# Estratégia

## 1. Stack

**Python + pandas, 100% local.** pandas + openpyxl leem e pré-filtram as planilhas; os indicadores são calculados em `src/analytics.py` e gravados em `outputs/*.csv`, consumidos pelo dashboard.

- sem banco, credencial ou rede (exceto o download opcional do SIDRA 9514, com cache local);
- uma função por pergunta analítica, com filtros literais e auditáveis;
- reexecução reprodutível: mesmo dado bruto, mesmos CSVs.

### Pré-filtro em memória

O Censo e a Trajetória brutos somam centenas de MB. O pipeline reduz já na leitura:

1. leitura em streaming das planilhas (`openpyxl` read-only) e em chunks dos CSVs;
2. descarte imediato de tudo que não é **Mato Grosso (`CO_UF = '51'`)** e **Graduação** (`TP_GRAU_ACADEMICO` em 1, 2, 3);
3. cálculo dos indicadores sobre o que sobra.

Os dados brutos nunca vão ao Git.

## 2. Camadas de dados

| Camada | Onde | Conteúdo / regras |
|---|---|---|
| **Raw** | `data/raw/inep_*/` (local, fora do Git) | Planilhas oficiais, somente leitura |
| **Filtrada** | DataFrames em memória | MT + Graduação; códigos (`co_*`, CINE, `tp_*`) como texto; suprimidos/inválidos viram nulo |
| **Saída** | `outputs/*.csv` | P1 a P5, B1 e B2, ponderados por `qt_ingressante` quando aplicável |

## 3. Idempotência

- Cada execução relê o bruto e sobrescreve os CSVs: reexecuções nunca duplicam linhas.
- Chaves duplicadas (EAD/multi-polo) abortam a leitura antes do cálculo.
- CSVs de saída são gravados em arquivo temporário e promovidos por `os.replace` (substituição atômica).

## 4. Armadilhas metodológicas e mitigação

| Armadilha | Mitigação |
|---|---|
| Cursos EAD aparecem em múltiplos polos/locais | Agregação obrigatória por `CO_CURSO`; a ingestão aborta se houver chave duplicada |
| Planilha de Trajetória com cabeçalho deslocado | Cabeçalhos na **linha 9**; o script valida as colunas esperadas |
| Perda de zeros à esquerda em códigos | Tudo lido como texto; `zfill` em UF e CINE |
| Censo em formato legado | Encoding **latin-1** e delimitador **`;`** |
| Risco de reidentificação | **Supressão de grupos com < 10 alunos** (soma de `qt_ingressante` >= 10) |
| Taxas instáveis em grupos pequenos | Exibir `qt_ingressantes` e `n_cursos` junto de cada taxa |
| Interpretação indevida dos resultados | **Associação estatística**, sem alegação de causalidade |
