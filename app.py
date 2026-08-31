# -*- coding: utf-8 -*-
"""
Análisis Estadístico de Resultados Saber Pro
=============================================
Aplicación Streamlit para cargar el listado de resultados del examen
Saber Pro (formato ICFES/institucional) y explorar sus principales
estadísticas y gráficos.

IMPORTANTE - PRIVACIDAD:
Esta app elimina automáticamente cualquier columna que identifique a las
personas (nombres, apellidos, número de identificación/documento, correo,
teléfono, etc.) antes de mostrar, graficar o permitir la descarga de los
datos. Los estudiantes se referencian únicamente por un rótulo anónimo
("Estudiante N") basado en su posición en el listado.

NOTA SOBRE LAS VARIABLES:
- "Puntaje" es el resultado absoluto de la prueba, sobre 300.
- "NBC" es el percentil del estudiante frente a los Núcleos Básicos de
  Conocimiento afines (p. ej., Ingeniería de Sistemas y afines a nivel
  nacional).
- "Nacional" es el percentil del estudiante frente a todos los evaluados
  a nivel nacional.
Por tratarse de percentiles, NBC y Nacional no se incluyen en las
estadísticas descriptivas de los puntajes absolutos.
"""

import base64
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

from core import (
    process_uploaded_file,
    get_sheet_names,
    find_competencies,
    descriptive_stats_table,
    box_stats,
    kde_estimate,
    shape_stats,
    diverging_ranking,
    diverging_from_baseline,
)

# ---------------------------------------------------------------------------
# Identidad institucional UCO (Manual de identidad 2024)
# ---------------------------------------------------------------------------
UCO_GREEN = "#008b50"
UCO_GOLD = "#ffca00"
UCO_GREEN_DARK = "#024426"
UCO_CREAM = "#f9ead4"
UCO_NAVY = "#1d3475"       # complementario: azul marino
UCO_ORANGE = "#e28210"     # complementario: naranja
UCO_TEAL = "#04b5ac"       # complementario: turquesa
UCO_OLIVE = "#c1c12f"      # complementario: verde oliva

# ---------------------------------------------------------------------------
# Paleta de las gráficas: colores institucionales UCO, tomados de la guía de
# color del manual de identidad (paleta principal + complementarios). Orden
# elegido para mantener buena separación perceptual entre colores adyacentes;
# como algunos tonos institucionales (dorado, naranja, turquesa, oliva) tienen
# bajo contraste sobre fondo claro, siempre se acompañan de etiquetas de datos
# visibles o de una tabla con los valores exactos.
CATEGORICAL = [
    UCO_GREEN,   # 1 verde institucional
    UCO_GOLD,    # 2 dorado institucional
    UCO_NAVY,    # 3 azul marino
    UCO_ORANGE,  # 4 naranja
    UCO_TEAL,    # 5 turquesa
    UCO_OLIVE,   # 6 verde oliva
]
# Par divergente (correlación, delta vs. promedio/mediana): verde institucional
# (positivo/por encima) <-> azul marino (negativo/por debajo), con el crema
# institucional como punto neutro.
DIVERGING_LOW = UCO_NAVY    # por debajo del promedio / correlación negativa
DIVERGING_MID = UCO_CREAM   # neutro (0)
DIVERGING_HIGH = UCO_GREEN  # por encima del promedio / correlación positiva
DIVERGING_SCALE = [[0.0, DIVERGING_LOW], [0.5, DIVERGING_MID], [1.0, DIVERGING_HIGH]]

# Color fijo para marcar outliers y líneas de referencia, independiente de la
# paleta categórica de arriba (así nunca se confunde con una competencia).
OUTLIER_COLOR = "#1a1a1a"

TEXT_PRIMARY = "#0b0b0b"
SURFACE = "#fcfcfb"
GRID = "#e3e2dc"

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
FAVICON_PATH = ASSETS_DIR / "E&B.png"
LOGO_PATH = ASSETS_DIR / "UCO.png"


def _load_favicon():
    try:
        return Image.open(FAVICON_PATH)
    except Exception:
        return None


def _b64(path: Path):
    try:
        return base64.b64encode(path.read_bytes()).decode("utf-8")
    except Exception:
        return None

PLOTLY_LAYOUT = dict(
    template="plotly_white",
    font=dict(color=TEXT_PRIMARY, size=13),
    paper_bgcolor=SURFACE,
    plot_bgcolor=SURFACE,
    margin=dict(l=40, r=20, t=50, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
)

cached_process = st.cache_data(show_spinner=False)(process_uploaded_file)


def add_box_with_outliers(fig, df, value_col, label, x_pos, color, label_col="Estudiante"):
    """Dibuja una caja y bigotes con estadísticos precalculados (para que el
    bigote coincida exactamente con la regla de Tukey usada para detectar
    outliers) y agrega los outliers como puntos por fuera del bigote, con el
    rótulo anónimo del estudiante."""
    stats_ = box_stats(df, value_col, label_col)
    fig.add_trace(go.Box(
        q1=[stats_["q1"]], median=[stats_["median"]], q3=[stats_["q3"]],
        lowerfence=[stats_["whisker_low"]], upperfence=[stats_["whisker_high"]],
        x=[label], name=label,
        marker_color=color, fillcolor=color,
        line=dict(color=OUTLIER_COLOR, width=1.5),
        showlegend=False,
    ))
    outliers = stats_["outliers"]
    if not outliers.empty:
        fig.add_trace(go.Scatter(
            x=[x_pos] * len(outliers),
            y=outliers[value_col],
            mode="markers+text",
            text=outliers[label_col],
            textposition="middle right",
            marker=dict(color=OUTLIER_COLOR, size=8, symbol="diamond"),
            textfont=dict(size=11, color=OUTLIER_COLOR),
            name="Outlier",
            showlegend=False,
            hovertemplate="%{text}: %{y}<extra></extra>",
        ))
    return stats_


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
_page_config_kwargs = dict(page_title="Análisis Saber Pro — UCO", layout="wide")
_favicon = _load_favicon()
if _favicon is not None:
    _page_config_kwargs["page_icon"] = _favicon
st.set_page_config(**_page_config_kwargs)

# --- Estilo institucional (Manual de identidad UCO 2024) -------------------
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@600;700;800&family=Roboto:wght@400;500&display=swap');

    html, body, [class^="css"], [class*=" css"] {{
        font-family: 'Roboto', 'Nimbus Sans', 'Helvetica Neue', Arial, sans-serif;
    }}
    h1, h2, h3, h4, .uco-header-title {{
        font-family: 'Montserrat', 'Helvetica Neue', Arial, sans-serif !important;
        font-weight: 700 !important;
    }}
    h2, h3 {{ color: {UCO_GREEN_DARK} !important; }}

    .uco-header {{
        display: flex;
        align-items: center;
        gap: 1.1rem;
        background: #ffffff;
        border-radius: 16px;
        padding: 0.85rem 1.4rem;
        box-shadow: 0 2px 14px rgba(0, 0, 0, 0.10);
        margin-bottom: 0.6rem;
    }}
    .uco-header img {{ height: 54px; width: auto; }}
    .uco-header-title {{
        font-size: 1.35rem;
        color: {UCO_GREEN};
        line-height: 1.2;
        margin: 0;
    }}
    .uco-header-sub {{
        font-size: 0.85rem;
        color: #5b5b5b;
        margin-top: 0.15rem;
    }}
    .uco-accent-bar {{
        height: 6px;
        border-radius: 4px;
        margin: 0.2rem 0 1.1rem 0;
        background: linear-gradient(90deg, {UCO_GREEN} 0%, {UCO_GREEN} 82%, {UCO_GOLD} 82%, {UCO_GOLD} 100%);
    }}

    section[data-testid="stSidebar"] {{
        background-color: {UCO_CREAM}55;
        border-right: 1px solid #e8e2d0;
    }}
    section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3 {{ color: {UCO_GREEN_DARK} !important; }}

    div[data-testid="stMetricValue"] {{ color: {UCO_GREEN}; }}
    div[data-testid="stMetricLabel"] {{ color: #5b5b5b; }}

    button[kind="primary"], .stDownloadButton button {{
        background-color: {UCO_GREEN} !important;
        border-color: {UCO_GREEN} !important;
    }}

    .stTabs [aria-selected="true"] {{
        color: {UCO_GREEN} !important;
        border-bottom-color: {UCO_GOLD} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

_logo_b64 = _b64(LOGO_PATH)
_logo_html = f'<img src="data:image/png;base64,{_logo_b64}" alt="Universidad Católica de Oriente" />' if _logo_b64 else ""
st.markdown(
    f"""
    <div class="uco-header">
        {_logo_html}
        <div>
            <p class="uco-header-title">Análisis Estadístico — Resultados Saber Pro</p>
            <p class="uco-header-sub">Universidad Católica de Oriente</p>
        </div>
    </div>
    <div class="uco-accent-bar"></div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Carga el listado de resultados y explora las principales estadísticas y "
    "gráficos. Los nombres y números de identificación de los estudiantes "
    "nunca se muestran, grafican ni exportan."
)

def _select_only_sheet(chosen_sheet, all_sheets):
    """Callback: fuerza selección única — marca la hoja elegida y desmarca
    el resto, emulando un grupo de radio-buttons con checkboxes."""
    for s in all_sheets:
        st.session_state[f"sheet_cb_{s}"] = (s == chosen_sheet)
    st.session_state["_active_sheet"] = chosen_sheet


with st.sidebar:
    st.header("1. Cargar archivo")
    uploaded = st.file_uploader("Archivo de resultados (.xlsx)", type=["xlsx"])
    sheet_choice = None
    if uploaded is not None:
        try:
            sheets = get_sheet_names(uploaded.getvalue(), uploaded.name)
        except Exception as e:
            sheets = None
            st.error(f"No se pudo leer el libro de Excel: {e}")

        if sheets:
            # Si es un archivo nuevo (hojas distintas a las de la selección
            # activa), se selecciona automáticamente la primera hoja.
            if st.session_state.get("_active_sheet") not in sheets:
                for s in sheets:
                    st.session_state[f"sheet_cb_{s}"] = (s == sheets[0])
                st.session_state["_active_sheet"] = sheets[0]

            if len(sheets) > 1:
                st.markdown("**Hoja**")
                for s in sheets:
                    st.checkbox(
                        s, key=f"sheet_cb_{s}",
                        on_change=_select_only_sheet, args=(s, sheets),
                    )

            sheet_choice = st.session_state["_active_sheet"]

if uploaded is None:
    st.info("Carga un archivo desde la barra lateral para comenzar.")
    st.stop()

try:
    df, df_summary, detected = cached_process(uploaded.getvalue(), uploaded.name, sheet_choice)
except Exception as e:
    st.error(f"Ocurrió un error al procesar el archivo: {e}")
    st.stop()

if df.empty:
    st.warning("No se encontraron filas de datos de estudiantes en el archivo.")
    st.stop()

if detected:
    st.success(
        f"Formato de listado Saber Pro detectado — {len(df)} estudiantes encontrados. "
        "Se removieron automáticamente las columnas de nombre, apellido e identificación."
    )
else:
    st.warning(
        "No se reconoció el formato estándar de dos filas de encabezado; se usó la "
        "primera fila como encabezado. Se removieron columnas que parecen contener "
        "datos personales, según el nombre de columna."
    )

competencies = find_competencies(df.columns)
score_cols = [f"{c} - Puntaje" for c in competencies if f"{c} - Puntaje" in df.columns]
nbc_cols = [f"{c} - NBC" for c in competencies if f"{c} - NBC" in df.columns]
nacional_cols = [f"{c} - Nacional" for c in competencies if f"{c} - Nacional" in df.columns]

if not score_cols:
    # Formato genérico: no se detectaron columnas "- Puntaje"; se usan todas
    # las columnas numéricas como puntajes.
    score_cols = [c for c in df.columns if c != "Estudiante" and pd.api.types.is_numeric_dtype(df[c])]

score_labels = [c.replace(" - Puntaje", "") for c in score_cols]

total_col = next((c for c in df.columns if "Puntaje Total - Puntaje" in str(c)), None)
if total_col is None:
    total_col = next((c for c in score_cols if "total" in str(c).lower()), None)

tabs = st.tabs([
    "Resumen",
    "Estadísticas descriptivas",
    "Distribuciones",
    "Percentiles nacionales",
    "Correlaciones",
    "Ranking",
])

# --- Resumen -----------------------------------------------------------
with tabs[0]:
    col1, col2, col3 = st.columns(3)
    col1.metric("Estudiantes", len(df))
    col2.metric("Competencias detectadas", len(competencies) if competencies else "—")
    if total_col:
        col3.metric("Puntaje total promedio (sobre 300)", f"{df[total_col].mean():.1f}")

    if competencies and score_cols:
        st.subheader("Puntaje promedio por competencia (sobre 300)")
        means = [df[c].mean() for c in score_cols]
        fig = go.Figure(
            go.Bar(
                x=score_labels, y=means,
                marker_color=CATEGORICAL[0],
                text=[f"{m:.0f}" for m in means],
                textposition="outside",
            )
        )
        fig.update_layout(**PLOTLY_LAYOUT, yaxis_title="Puntaje promedio", showlegend=False)
        fig.update_yaxes(gridcolor=GRID)
        st.plotly_chart(fig, width="stretch")

    st.subheader("Descargar datos anonimizados")
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Descargar CSV (sin nombres ni documentos)",
        data=csv_bytes,
        file_name="resultados_anonimizados.csv",
        mime="text/csv",
    )

# --- Estadísticas descriptivas -----------------------------------------
with tabs[1]:
    st.subheader("Estadísticas descriptivas — puntajes absolutos (sobre 300)")
    st.caption(
        "Tabla transpuesta: una fila por estadístico y una columna por competencia. "
        "Solo se incluyen los puntajes absolutos; NBC y Nacional son percentiles y "
        "se analizan en la pestaña 'Percentiles'."
    )
    if score_cols:
        desc = descriptive_stats_table(df, score_cols, score_labels)
        st.dataframe(desc.style.format("{:.1f}"), width="stretch")
    else:
        st.warning("No se detectaron columnas de puntaje para analizar.")

# --- Distribuciones ------------------------------------------------------
with tabs[2]:
    st.subheader("Distribución de puntajes")
    if score_cols:
        choice = st.selectbox(
            "Selecciona una competencia",
            score_cols,
            format_func=lambda c: c.replace(" - Puntaje", ""),
        )
        choice_label = choice.replace(" - Puntaje", "")
        data = df[choice].dropna()

        st.markdown("**Histograma con estimación de densidad (KDE)**")
        st.caption(
            "Se usa una estimación de densidad no paramétrica (KDE) en vez de forzar "
            "el ajuste a una distribución teórica (normal, t, etc.): con muestras "
            "pequeñas como esta, una prueba de bondad de ajuste pierde validez cuando "
            "los parámetros se estiman con los mismos datos, y el KDE describe la "
            "forma real de los datos sin asumir una familia concreta."
        )
        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(
            x=data, histnorm="probability density", name="Datos observados",
            marker_color=CATEGORICAL[0], nbinsx=12, opacity=0.85,
        ))
        x_grid, y_kde = kde_estimate(data)
        if x_grid is not None:
            fig_hist.add_trace(go.Scatter(
                x=x_grid, y=y_kde, mode="lines", name="Densidad (KDE)",
                line=dict(color=CATEGORICAL[1], width=2.5),
            ))
        fig_hist.update_layout(**PLOTLY_LAYOUT, title=f"Distribución de {choice_label}", yaxis_title="Densidad")
        fig_hist.update_yaxes(gridcolor=GRID)
        st.plotly_chart(fig_hist, width="stretch")

        shp = shape_stats(data)
        if shp:
            asim = shp["skewness"]
            curt = shp["kurtosis"]
            asim_txt = (
                "aproximadamente simétrica" if abs(asim) < 0.5 else
                ("con asimetría a la derecha (cola hacia puntajes altos)" if asim > 0 else
                 "con asimetría a la izquierda (cola hacia puntajes bajos)")
            )
            curt_txt = (
                "similar a la normal" if abs(curt) < 0.5 else
                ("más apuntada y con colas más pesadas que la normal" if curt > 0 else
                 "más aplanada que la normal")
            )
            st.caption(
                f"Forma de la distribución: asimetría = {asim:.2f} ({asim_txt}); "
                f"curtosis (exceso) = {curt:.2f} ({curt_txt})."
            )

        st.markdown("**Diagrama de caja y bigotes**")
        st.caption(
            "Los bigotes se calculan como el dato más extremo dentro de 1.5 veces el "
            "rango intercuartílico (regla de Tukey); los valores por fuera de ese "
            "rango se muestran como puntos individuales, etiquetados con el "
            "estudiante anónimo correspondiente."
        )
        fig_box = go.Figure()
        add_box_with_outliers(fig_box, df, choice, choice_label, choice_label, CATEGORICAL[0])
        fig_box.update_layout(**PLOTLY_LAYOUT, showlegend=False, yaxis_title="Puntaje")
        st.plotly_chart(fig_box, width="stretch")

        if len(score_cols) > 1:
            st.subheader("Comparación de todas las competencias")
            fig_multi = go.Figure()
            for i, (c, label) in enumerate(zip(score_cols, score_labels)):
                color = CATEGORICAL[i % len(CATEGORICAL)]
                add_box_with_outliers(fig_multi, df, c, label, label, color)
            fig_multi.update_layout(**PLOTLY_LAYOUT, showlegend=False, yaxis_title="Puntaje")
            st.plotly_chart(fig_multi, width="stretch")

            st.markdown("**Diagrama de violín (forma completa de la distribución)**")
            st.caption(
                "El violín complementa a la caja y bigotes: mientras la caja resume la "
                "distribución en cinco números (mínimo, cuartiles y máximo), el violín "
                "muestra la densidad completa —dónde se concentran realmente los "
                "puntajes— a través de una estimación de densidad (KDE) reflejada a "
                "cada lado. La caja interior y la línea de la media quedan marcadas "
                "dentro de cada violín."
            )
            fig_violin = go.Figure()
            for i, (c, label) in enumerate(zip(score_cols, score_labels)):
                color = CATEGORICAL[i % len(CATEGORICAL)]
                vals = df[c].dropna()
                fig_violin.add_trace(go.Violin(
                    y=vals, x=[label] * len(vals), name=label,
                    line_color=OUTLIER_COLOR, fillcolor=color, opacity=0.75,
                    box_visible=True, meanline_visible=True, points=False,
                    showlegend=False,
                ))
            fig_violin.update_layout(**PLOTLY_LAYOUT, showlegend=False, yaxis_title="Puntaje")
            st.plotly_chart(fig_violin, width="stretch")
    else:
        st.warning("No hay columnas de puntaje para graficar.")

# --- Percentiles nacionales --------------------------------------------
with tabs[3]:
    st.subheader("Percentiles nacionales (NBC y Nacional)")
    st.markdown(
        "**NBC** es el percentil del estudiante frente a los Núcleos Básicos de "
        "Conocimiento afines (por ejemplo, Ingeniería de Sistemas y afines a nivel "
        "nacional). **Nacional** es el percentil frente a todos los evaluados del "
        "país. Un percentil de 50 equivale a la mediana nacional; valores por "
        "encima de 50 indican un desempeño relativo superior al de la mitad de los "
        "evaluados."
    )
    if competencies and nbc_cols and nacional_cols:
        labels = competencies
        nbc_means = [df[f"{c} - NBC"].mean() for c in competencies]
        nac_means = [df[f"{c} - Nacional"].mean() for c in competencies]
        fig = go.Figure()
        fig.add_bar(name="Percentil NBC (afines)", x=labels, y=nbc_means, marker_color=CATEGORICAL[0])
        fig.add_bar(name="Percentil Nacional", x=labels, y=nac_means, marker_color=CATEGORICAL[1])
        fig.add_hline(y=50, line_dash="dash", line_color=OUTLIER_COLOR,
                      annotation_text="Mediana nacional (percentil 50)", annotation_position="top left")
        fig.update_layout(**PLOTLY_LAYOUT, barmode="group", yaxis_title="Percentil promedio (0-100)")
        fig.update_yaxes(gridcolor=GRID, range=[0, 100])
        st.plotly_chart(fig, width="stretch")

        table = pd.DataFrame({
            "Competencia": labels,
            "Percentil NBC promedio": nbc_means,
            "Percentil Nacional promedio": nac_means,
        })
        st.dataframe(
            table.style.format({"Percentil NBC promedio": "{:.1f}", "Percentil Nacional promedio": "{:.1f}"}),
            width="stretch",
        )

        st.markdown("---")
        st.subheader("Detalle por estudiante")
        st.caption(
            "Selecciona una competencia para ver el percentil de cada uno de los "
            f"{len(df)} estudiantes frente a la mediana nacional (percentil 50)."
        )
        comp_choice = st.selectbox("Competencia", competencies, key="percentil_detalle_comp")

        for kind in ["NBC", "Nacional"]:
            value_col = f"{comp_choice} - {kind}"
            if value_col not in df.columns:
                continue
            ranked = diverging_from_baseline(df, value_col, 50)
            colors = [DIVERGING_HIGH if v >= 0 else DIVERGING_LOW for v in ranked["delta"]]
            fig_d = go.Figure(go.Bar(
                x=ranked["delta"], y=ranked["Estudiante"], orientation="h",
                marker_color=colors,
                text=[f"{v:+.0f}" for v in ranked["delta"]],
                textposition="outside",
            ))
            fig_d.add_vline(x=0, line_color=TEXT_PRIMARY, line_width=1)
            fig_d.update_layout(
                **PLOTLY_LAYOUT,
                title=f"Percentil {kind} — {comp_choice}",
                xaxis_title="Diferencia frente a la mediana nacional (percentil 50)",
                yaxis=dict(autorange="reversed"), height=max(320, 22 * len(ranked)),
                showlegend=False,
            )
            fig_d.update_xaxes(gridcolor=GRID)
            st.plotly_chart(fig_d, width="stretch")

            n_above = int((ranked["delta"] > 0).sum())
            n_below = int((ranked["delta"] < 0).sum())
            n_equal = len(ranked) - n_above - n_below
            st.caption(
                f"{kind} — {comp_choice}: {n_above} estudiantes "
                f"({100 * n_above / len(ranked):.0f}%) por encima de la mediana nacional, "
                f"{n_below} ({100 * n_below / len(ranked):.0f}%) por debajo"
                + (f" y {n_equal} exactamente en la mediana" if n_equal else "")
                + "."
            )
    else:
        st.info("El archivo no incluye columnas de percentil NBC y Nacional por competencia para comparar.")

# --- Correlaciones ---------------------------------------------------------
with tabs[4]:
    st.subheader("Correlación entre competencias (puntajes absolutos)")
    st.markdown(
        "El siguiente mapa de calor muestra el coeficiente de correlación de "
        "Pearson entre los puntajes absolutos de cada competencia, en una escala "
        "divergente institucional de azul marino (correlación negativa) a verde "
        "(correlación positiva), con el crema institucional en el punto neutro (0). "
        "La diagonal principal siempre vale 1 (una variable correlaciona "
        "perfectamente consigo misma), por lo que aparece en el extremo verde de la "
        "escala. Un valor cercano a **1** indica "
        "que los estudiantes con puntajes altos en una competencia tienden también "
        "a tener puntajes altos en la otra; cercano a **-1** indicaría una relación "
        "inversa (poco frecuente en este tipo de pruebas); y cercano a **0** indica "
        "que no hay una relación lineal clara entre ambas. Esta correlación no "
        "implica causalidad."
    )
    if len(score_cols) > 1:
        corr = df[score_cols].corr()
        fig = go.Figure(
            go.Heatmap(
                z=corr.values, x=score_labels, y=score_labels,
                colorscale=DIVERGING_SCALE,
                zmin=-1, zmax=1,
                text=np.round(corr.values, 2), texttemplate="%{text}",
                colorbar=dict(title="r"),
            )
        )
        fig.update_layout(**PLOTLY_LAYOUT, title="Matriz de correlación (Pearson)")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, width="stretch")
    else:
        st.info("Se necesitan al menos dos variables numéricas para calcular correlaciones.")

# --- Ranking -------------------------------------------------------------
with tabs[5]:
    st.subheader("Ranking de puntaje total frente al promedio del grupo")
    st.caption(
        "Se muestra la diferencia (delta) de cada estudiante frente al promedio del "
        "grupo, en vez de un ranking simple o un análisis de Pareto: esta forma "
        "(barras divergentes contra una línea base) es la recomendada para comparar "
        "magnitudes individuales contra una referencia, mientras que el análisis de "
        "Pareto está pensado para medir concentración de causas (por ejemplo, qué "
        "porcentaje de defectos explican unas pocas categorías), no para puntajes "
        "individuales de un examen."
    )
    if total_col:
        ranked, mean_val = diverging_ranking(df, total_col)
        n_show = st.slider("N° de estudiantes a mostrar", 5, len(ranked), len(ranked))
        top = ranked.head(n_show)

        colors = [DIVERGING_HIGH if v >= 0 else DIVERGING_LOW for v in top["delta"]]
        fig = go.Figure(go.Bar(
            x=top["delta"], y=top["Estudiante"], orientation="h",
            marker_color=colors,
            text=[f"{v:+.0f}" for v in top["delta"]],
            textposition="outside",
        ))
        fig.add_vline(x=0, line_color=TEXT_PRIMARY, line_width=1)
        fig.update_layout(
            **PLOTLY_LAYOUT,
            xaxis_title=f"Diferencia frente al promedio del grupo ({mean_val:.1f})",
            yaxis=dict(autorange="reversed"), height=max(320, 26 * n_show),
            showlegend=False,
        )
        fig.update_xaxes(gridcolor=GRID)
        st.plotly_chart(fig, width="stretch")

        n_above = int((ranked["delta"] > 0).sum())
        n_below = int((ranked["delta"] < 0).sum())
        n_equal = len(ranked) - n_above - n_below
        max_row = ranked.iloc[0]
        min_row = ranked.iloc[-1]
        st.markdown(
            f"**Análisis:** el promedio del grupo es **{mean_val:.1f}** (sobre 300). "
            f"**{n_above}** estudiantes ({100 * n_above / len(ranked):.0f}%) están por "
            f"encima del promedio y **{n_below}** ({100 * n_below / len(ranked):.0f}%) "
            f"por debajo"
            + (f", con {n_equal} en el promedio exacto" if n_equal else "")
            + f". El mayor desempeño relativo es **{max_row['Estudiante']}**, "
            f"{max_row['delta']:+.0f} puntos frente al promedio, y el menor es "
            f"**{min_row['Estudiante']}**, {min_row['delta']:+.0f} puntos."
        )
    else:
        st.info("No se detectó una columna de puntaje total para generar el ranking.")
