# -*- coding: utf-8 -*-
"""Lógica de carga, limpieza y anonimización de resultados Saber Pro.

Separado de app.py para poder probarse sin depender del runtime de
Streamlit.
"""

import io
import re

import numpy as np
import pandas as pd
from scipy import stats

# ---------------------------------------------------------------------------
# Columnas que identifican personas — se eliminan siempre, sin excepción
# ---------------------------------------------------------------------------
SENSITIVE_PATTERNS = [
    r"nombre", r"apellido", r"identificaci", r"documento", r"c[eé]dula",
    r"\bcc\b", r"correo", r"e-?mail", r"tel[eé]fono", r"celular",
    r"direcci[oó]n", r"usuario", r"login",
]
SENSITIVE_RE = re.compile("|".join(SENSITIVE_PATTERNS), flags=re.IGNORECASE)


def is_sensitive_column(col_name: str) -> bool:
    return bool(SENSITIVE_RE.search(str(col_name)))


def _clean_cell(v):
    if pd.isna(v):
        return None
    return str(v).strip()


def load_saberpro_sheet(raw: pd.DataFrame):
    """Reconoce el formato típico de listado Saber Pro: una fila con
    categorías (N°, Identificación, Nombre, Apellido, Puntaje Total,
    <competencia 1>, <competencia 2>, ...) seguida de una fila con
    subcategorías (Puntaje / NBC / Nacional) para cada competencia.

    Retorna (df_estudiantes, df_resumen_institucional, encabezado_detectado).
    """
    header_row_idx = None
    for i in range(min(20, len(raw))):
        row_vals = [_clean_cell(v) for v in raw.iloc[i].tolist()]
        for v in row_vals:
            if v and v.lower() in ("identificación", "identificacion"):
                header_row_idx = i
                break
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        return None, None, False  # No se detectó el formato especial

    top = [_clean_cell(v) for v in raw.iloc[header_row_idx].tolist()]
    sub_row_idx = header_row_idx + 1
    sub = [_clean_cell(v) for v in raw.iloc[sub_row_idx].tolist()] if sub_row_idx < len(raw) else [None] * len(top)

    # forward-fill de las categorías superiores (celdas combinadas -> NaN)
    filled_top = []
    last = None
    for v in top:
        if v is not None:
            last = v
        filled_top.append(last)

    columns = []
    for t, s in zip(filled_top, sub):
        if s is None or s == "":
            columns.append(t if t else "col")
        else:
            columns.append(f"{t} - {s}")

    data_start = sub_row_idx + 1
    data = raw.iloc[data_start:].copy()
    data.columns = columns

    # localizar la columna "N°" (primera) para separar filas de resumen
    first_col = columns[0]

    def is_row_number(v):
        try:
            float(v)
            return True
        except (TypeError, ValueError):
            return False

    is_student_row = data[first_col].apply(is_row_number)
    df_students = data[is_student_row].reset_index(drop=True)
    df_summary = data[~is_student_row].reset_index(drop=True)

    # eliminar columnas totalmente vacías
    df_students = df_students.dropna(axis=1, how="all")
    df_summary = df_summary.reindex(columns=df_students.columns)

    # convertir a numérico lo que se pueda (todo excepto columnas identificatorias/texto)
    for c in df_students.columns:
        if is_sensitive_column(c) or c == first_col:
            continue
        df_students[c] = pd.to_numeric(df_students[c], errors="coerce")
        df_summary[c] = pd.to_numeric(df_summary[c], errors="coerce")

    return df_students, df_summary, True


def anonymize(df: pd.DataFrame) -> pd.DataFrame:
    """Elimina cualquier columna identificatoria y asigna un rótulo anónimo."""
    keep_cols = [c for c in df.columns if not is_sensitive_column(c)]
    clean = df[keep_cols].copy()
    clean.insert(0, "Estudiante", [f"Estudiante {i + 1}" for i in range(len(clean))])
    return clean


def process_uploaded_file(file_bytes: bytes, filename: str, sheet_name):
    if filename.lower().endswith(".csv"):
        raw = pd.read_csv(io.BytesIO(file_bytes), header=None)
    else:
        raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, header=None, engine="openpyxl")

    df_students, df_summary, detected = load_saberpro_sheet(raw)

    if not detected:
        # Formato genérico: primera fila como encabezado
        if filename.lower().endswith(".csv"):
            generic = pd.read_csv(io.BytesIO(file_bytes))
        else:
            generic = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name, engine="openpyxl")
        df_students = generic
        df_summary = pd.DataFrame(columns=generic.columns)
        for c in df_students.columns:
            if not is_sensitive_column(c):
                df_students[c] = pd.to_numeric(df_students[c], errors="ignore")

    anon = anonymize(df_students)
    return anon, df_summary, detected


def get_sheet_names(file_bytes: bytes, filename: str):
    if filename.lower().endswith(".csv"):
        return None
    xl = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
    return xl.sheet_names


def find_competencies(columns):
    """Detecta grupos de competencias con sub-columna 'Puntaje'."""
    comps = []
    for c in columns:
        if isinstance(c, str) and c.endswith(" - Puntaje"):
            comps.append(c[: -len(" - Puntaje")])
    return comps


# ---------------------------------------------------------------------------
# Análisis estadístico
# ---------------------------------------------------------------------------
def descriptive_stats_table(df: pd.DataFrame, score_cols: list, labels: list = None) -> pd.DataFrame:
    """Tabla de estadística descriptiva transpuesta: una fila por estadístico,
    una columna por variable (competencia). Incluye rango y coeficiente de
    variación además de las medidas usuales. No incluye 'n' (no aporta aquí,
    ya que todas las variables comparten el mismo número de estudiantes).
    """
    if labels is None:
        labels = score_cols
    out = {}
    for col, label in zip(score_cols, labels):
        s = df[col].dropna()
        mean = s.mean()
        std = s.std()
        out[label] = {
            "mínimo": s.min(),
            "Q1": s.quantile(0.25),
            "mediana": s.median(),
            "media": mean,
            "Q3": s.quantile(0.75),
            "máximo": s.max(),
            "rango": s.max() - s.min(),
            "desv. estándar": std,
            "coef. de variación (%)": (std / mean * 100) if mean else float("nan"),
        }
    order = ["mínimo", "Q1", "mediana", "media", "Q3", "máximo", "rango",
             "desv. estándar", "coef. de variación (%)"]
    table = pd.DataFrame(out).reindex(order)
    return table


def box_stats(df: pd.DataFrame, value_col: str, label_col: str = "Estudiante"):
    """Estadísticas de caja y bigotes por la regla de Tukey (1.5 x IQR),
    recalculando los bigotes como el dato válido más extremo dentro de las
    cercas (no la cerca teórica), de forma que los outliers queden SIEMPRE
    graficados por fuera de los bigotes.

    Retorna un dict con: q1, median, q3, whisker_low, whisker_high,
    outliers (DataFrame con [label_col, value_col]).
    """
    s = df[[label_col, value_col]].dropna()
    vals = s[value_col]
    q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
    iqr = q3 - q1
    lower_fence, upper_fence = q1 - 1.5 * iqr, q3 + 1.5 * iqr

    inside = vals[(vals >= lower_fence) & (vals <= upper_fence)]
    whisker_low = inside.min() if not inside.empty else q1
    whisker_high = inside.max() if not inside.empty else q3

    outlier_mask = (vals < lower_fence) | (vals > upper_fence)
    outliers = s.loc[outlier_mask]

    return dict(
        q1=q1, median=vals.median(), q3=q3,
        whisker_low=whisker_low, whisker_high=whisker_high,
        outliers=outliers,
    )


def kde_estimate(data, num=200, pad_frac=0.15):
    """Estimación de densidad no paramétrica (KDE, kernel gaussiano, regla de
    Scott para el ancho de banda). Es la alternativa recomendada frente a
    forzar el ajuste a una familia paramétrica (normal, t, etc.) cuando la
    muestra es pequeña: no asume una forma concreta y no exige pruebas de
    bondad de ajuste (como Kolmogórov-Smirnov) que pierden validez cuando los
    parámetros de la distribución candidata se estiman con la misma muestra.

    Retorna (x_grid, densidad) o (None, None) si no hay suficientes datos.
    """
    arr = np.asarray(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3 or np.allclose(arr, arr[0]):
        return None, None
    kde = stats.gaussian_kde(arr, bw_method="scott")
    pad = (arr.max() - arr.min()) * pad_frac or 1.0
    x_grid = np.linspace(arr.min() - pad, arr.max() + pad, num)
    return x_grid, kde(x_grid)


def shape_stats(data):
    """Asimetría y curtosis (exceso) de la muestra, para describir la forma
    de la distribución sin necesidad de un ajuste paramétrico formal."""
    arr = np.asarray(data, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 3:
        return None
    return dict(
        skewness=stats.skew(arr, bias=False),
        kurtosis=stats.kurtosis(arr, bias=False),
    )


def diverging_from_baseline(df: pd.DataFrame, value_col: str, baseline: float, label_col: str = "Estudiante"):
    """Prepara los datos para un diagrama de barras divergente ('delta
    respecto a una línea base'): la forma recomendada para comparar
    magnitudes individuales contra una referencia, en vez de un ranking
    simple o un Pareto (pensado para concentración de causas, no para
    valores individuales).

    Retorna (df_ordenado_con_delta) con columnas [label_col, value_col, "delta"].
    """
    d = df[[label_col, value_col]].dropna().copy()
    d["delta"] = d[value_col] - baseline
    d = d.sort_values(value_col, ascending=False).reset_index(drop=True)
    return d


def diverging_ranking(df: pd.DataFrame, value_col: str, label_col: str = "Estudiante"):
    """Igual que `diverging_from_baseline`, usando el promedio del grupo como
    línea base. Retorna (df_ordenado_con_delta, media_grupo).
    """
    mean_val = df[value_col].dropna().mean()
    d = diverging_from_baseline(df, value_col, mean_val, label_col)
    return d, mean_val
