# Análisis Estadístico Saber Pro (app en Streamlit)

App para cargar el listado de resultados del Saber Pro y ver estadísticas y
gráficos, **sin exponer nombres ni números de identificación** de los
estudiantes.

## Cómo ejecutarla

1. Instala las dependencias (una sola vez):

   ```
   pip install -r requirements.txt  (incluye streamlit, pandas, numpy, plotly, openpyxl y scipy)
   ```

2. Ejecuta la app:

   ```
   streamlit run app.py
   ```

3. Se abrirá en tu navegador (normalmente `http://localhost:8501`). Desde la
   barra lateral, carga el archivo `.xlsx` con los resultados (por ejemplo
   `RESULTADOS 1-2026.xlsx`; no se aceptan otros formatos) y, si el libro
   tiene varias hojas, marca con el checkbox la hoja que quieres analizar
   (solo puede haber una hoja seleccionada a la vez).

## Qué hace con la privacidad de los datos

- Detecta automáticamente las columnas de **Nombre, Apellido, Identificación
  (documento), correo, teléfono**, etc., por el nombre de la columna, y las
  elimina antes de mostrar, graficar o permitir descargar cualquier dato.
- Cada estudiante se identifica solo con un rótulo anónimo ("Estudiante 1",
  "Estudiante 2", ...) según su posición en el listado original.
- El botón de descarga solo exporta los datos ya anonimizados.

## Qué incluye el análisis

- **Resumen**: número de estudiantes, competencias detectadas, puntaje total
  promedio y puntaje promedio por competencia (puntajes absolutos, sobre 300).
- **Estadísticas descriptivas**: tabla transpuesta (un estadístico por fila,
  una competencia por columna) con mínimo, Q1, mediana, media, Q3, máximo,
  rango y coeficiente de variación — solo para los puntajes absolutos (NBC y
  Nacional son percentiles y se analizan en la pestaña "Percentiles").
- **Distribuciones**: histograma con una estimación de densidad no
  paramétrica (KDE) — más robusta que forzar el ajuste a una distribución
  teórica cuando la muestra es pequeña — junto con la asimetría y curtosis de
  cada competencia, y diagrama de caja con los bigotes recalculados según la
  regla de Tukey (1.5×IQR) para que los estudiantes atípicos (outliers) queden
  siempre por fuera del bigote y etiquetados con su rótulo anónimo. Debajo de
  la comparación de todas las competencias en cajas, se agrega la misma
  comparación como diagrama de violín, que muestra la forma completa de la
  densidad (no solo los cinco números que resume la caja).
- **Percentiles nacionales**: compara el percentil NBC promedio (frente a los
  Núcleos Básicos de Conocimiento afines, p. ej. Ingeniería de Sistemas y
  afines) y el percentil Nacional promedio (frente a todos los evaluados del
  país) por competencia, contra la mediana nacional (percentil 50). Incluye
  además un detalle por estudiante: eligiendo una competencia en la lista
  desplegable, se muestra el percentil (NBC y Nacional) de cada uno de los
  estudiantes frente a la mediana nacional.
- **Correlaciones**: mapa de calor de correlación de Pearson entre los
  puntajes absolutos de cada competencia, en escala divergente institucional
  de azul marino (negativa) a verde (positiva) con la diagonal principal
  siempre en 1, y una breve explicación de cómo interpretarlo.
- **Ranking**: diferencia (delta) de cada estudiante frente al promedio del
  grupo, como un diagrama de barras divergente — la forma recomendada para
  comparar magnitudes individuales contra una línea base — en vez de un
  ranking simple o un análisis de Pareto (pensado para concentración de
  causas, no para puntajes individuales), con un análisis corto sobre cuántos
  estudiantes están por encima o por debajo del promedio.

## Sobre las variables del archivo

- **Puntaje**: resultado absoluto de la prueba, sobre 300.
- **NBC**: percentil del estudiante frente a los Núcleos Básicos de
  Conocimiento afines a nivel nacional (p. ej. Ingeniería de Sistemas y
  afines).
- **Nacional**: percentil del estudiante frente a todos los evaluados del
  país.

## Formato de archivo esperado

La app reconoce automáticamente el formato típico del listado Saber Pro (dos
filas de encabezado: categorías de competencia arriba, y Puntaje/NBC/Nacional
debajo). Si el archivo tiene otro formato, la app usa la primera fila como
encabezado normal y de todas formas elimina cualquier columna que parezca
contener datos personales.

## Identidad visual (Manual de identidad UCO 2024)

La app aplica la identidad de la Universidad Católica de Oriente:

- **Ícono de la pestaña del navegador**: `assets/E&B.png`.
- **Logo institucional** en la parte superior izquierda: `assets/UCO.png`,
  dentro de una tarjeta blanca con esquinas redondeadas y sombra suave, como
  indica el manual para el uso del logo en positivo.
- **Colores institucionales**: verde `#008b50` y amarillo/oro `#ffca00` como
  colores principales (barra de acento bajo el encabezado, títulos, métricas,
  pestaña activa y botón de descarga), con `#024426` (verde oscuro) para
  subtítulos y una barra lateral con un tono crema suave (`#f9ead4`).
- **Tipografía**: Montserrat (bold) para títulos, como alternativa cercana a
  Latinka (la fuente de títulos del manual, no disponible como fuente web);
  Roboto para el texto general, como alternativa a Nimbus Sans.
- **Gráficas**: usan la paleta institucional completa de la guía de color del
  manual (verde, dorado, azul marino, naranja, turquesa y verde oliva) para
  distinguir competencias, y una escala divergente azul marino–crema–verde
  para correlaciones y comparaciones contra un promedio o mediana. Como
  algunos tonos institucionales (dorado, naranja, turquesa, oliva) tienen bajo
  contraste sobre fondo claro, siempre van acompañados de etiquetas de datos
  visibles o de una tabla con los valores exactos, y los outliers y líneas de
  referencia usan un color oscuro fijo (no parte de la paleta de competencias)
  para que nunca se confundan con una serie de datos.

Si cambias el logo o el ícono, solo reemplaza los archivos `assets/UCO.png` y
`assets/E&B.png` manteniendo esos nombres.
