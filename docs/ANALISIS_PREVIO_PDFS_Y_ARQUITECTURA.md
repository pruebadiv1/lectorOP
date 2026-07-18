# Preparador Inteligente de Materiales para Winmaker

## Análisis previo de PDFs y propuesta de arquitectura

Estado: **actualizado con la iteración DIVANNI del 18/07/2026**.  
Alcance de este documento: análisis y diseño que gobiernan el MVP.

## 1. Muestra analizada

Se inspeccionaron las tres Órdenes de Producción suministradas:

| Documento | Páginas | Tipologías | Filas de vidrio | Cantidad física informada | Filas de tela importadas | Filas de accesorios |
|---|---:|---:|---:|---:|---:|---:|
| Sebastián Solsona | 11 | 11 | 10 | 11 | 4 | 121 |
| Marcelo Torres | 10 | 10 | 16 | 20 | 0 | 170 |
| Lenan Planta Baja | 15 | 15 | 30 | 30 | 1 | 251 |
| **Total** | **36** | **36** | **56** | **61** | **5** | **542** |

La diferencia entre “filas” y “piezas físicas” es importante: Winmaker puede representar varias piezas iguales en una sola fila. Por ejemplo, se observaron filas de vidrio con cantidad 2 y 3.

Los tres archivos son PDFs generados digitalmente y contienen capa de texto; no son escaneos. Aun así, la capa de texto presenta fragmentaciones y caracteres defectuosos, por lo que “tener texto” no equivale a “tener datos confiables”.

## 2. Patrones detectados

### 2.1 Estructura general

- Cada página de la muestra corresponde a una tipología.
- Todas las páginas contienen los anclajes semánticos `TIPOLOGIA`, `CANTIDAD`, `DETALLE`, `Perfiles`, `Interiores` y `Accesorios`.
- `TIPOLOGIA`, `CANTIDAD` y `DETALLE` cambian de altura según la complejidad del dibujo y del encabezado, pero conservan su etiqueta.
- `Interiores` aparece después de `Perfiles`, aunque a distinta altura en cada página.
- `Accesorios` corre en paralelo a la tabla de perfiles/interiores. Por eso el orden lineal de texto del PDF puede mezclar filas de distintas tablas.
- Las descripciones pueden contener espacios, signos, comillas, barras, puntos, guiones, mayúsculas/minúsculas y caracteres acentuados.
- Las tipologías no siguen un único formato: hay valores como `V6`, `V4A`, `MV6`, `C1-V1`, `FI 1`, `FV 2`, `PV1A`.
- El detalle de abertura también es texto libre y contiene variantes/errores de escritura propios del origen.

### 2.2 Cliente

- El valor visible correcto es `SOLSONA`, `MARCELO TORRES` o `LENAN`.
- En la capa de texto se observan separaciones anómalas: `CLIENTE S: OLSONA`, `CLIENTE M: ARCELO TORRES` y `CLIENTE L: ENAN`.
- Por lo tanto, no es seguro extraer el cliente tomando literalmente todo lo situado después de `CLIENTE`.
- El cliente principal será ingresado manualmente durante la carga.
- El valor extraído se utilizará solamente como control informativo. Una diferencia o baja confianza generará una advertencia no bloqueante.
- No se implementará lógica compleja para reconstruir el cliente en el MVP.

### 2.3 Interiores y vidrios

- Las filas observadas siguen el patrón semántico:
  `código + cantidad + ancho x alto + descripción`.
- Se encontraron códigos de vidrio muy diversos: `FL4DVH`, `DVH9`, `DVHLUC`, `DVH123`, `1DVH12`, `LAMIN4`, `DVH29`. No conviene decidir si algo es vidrio usando una lista cerrada de códigos.
- La identificación más estable es una fila válida de `Interiores` con cantidad y medida reconocibles. El código o detalle determina si se presenta como vidrio o tela.
- Hay medidas con `x` y podrían aparecer variantes `X` o `×`; el parser debe normalizarlas al formato visual `ancho x alto`, conservando además los valores numéricos separados.
- Hay filas repetidas idénticas que deben preservarse.
- Hay filas cuyo campo `Cantidad` es mayor que 1. La definición final es conservar cada fila exactamente una vez y mantener la cantidad original.
- Las descripciones de vidrio no siempre comienzan con `DVH`; por ejemplo, existen `3+3 + 12 + 3+3` y `TEMP SOL NEUTRO LIGHT...`.

### 2.4 Telas

- Se observaron `TELA` y la descripción `TELA ALUMINIO IMPORTADO`.
- Pueden convivir vidrio y tela en una misma tipología.
- Las filas de tela se conservan en el JSON de negocio con `material_type: "mesh"`.
- Aparecen junto a los vidrios en revisión y admiten modificación, observaciones, exclusión y alta manual.
- La clasificación se realiza por coincidencia normalizada en código o descripción (`TELA`, `TELA ALUMINIO`, `TELA MOSQUITERA`), tolerando mayúsculas, minúsculas y espacios.

### 2.5 Accesorios

- Las filas siguen conceptualmente:
  `código + cantidad + detalle`.
- Hay códigos puramente alfabéticos (`B`, `D`, `N`), alfanuméricos (`B30`, `E69`, `T01`, `H4507`) y numéricos (`227251`).
- Las cantidades incluyen enteros y decimales.
- En la capa de texto algunos códigos aparecen fragmentados, por ejemplo `R 4 9`, `H 5 7`, `E 6 9` o `T 9 6`, aunque visualmente son `R49`, `H57`, `E69` y `T96`.
- Se detectó una anomalía de codificación similar a `B68(cid:9) 3.0`, con pérdida o corrupción de parte del texto. Esa fila no debe “adivinarse”: se conservará lo recuperable, se marcará con baja confianza y requerirá confirmación.
- La descripción puede envolver a una segunda línea. Una línea sin nuevo código/cantidad debe anexarse a la fila anterior solo cuando la continuidad resulte inequívoca; de lo contrario se genera advertencia.

### 2.6 Cantidad de tipología

- Solo una tipología de la muestra tiene cantidad mayor que uno: Solsona, página 11, `MV6`, cantidad 2.
- Los accesorios de esa página se conservarán exactamente como aparecen.
- Se emitirá la advertencia solicitada y no se multiplicará ni modificará ninguna cantidad.

## 3. Supuestos propuestos

Estos supuestos deben aprobarse antes de implementar:

1. Cada página que contenga los seis encabezados requeridos se considera una tipología.
2. Una página sin alguno de los encabezados obligatorios no se interpreta parcialmente como válida: se crea un resultado de extracción fallido/revisable para esa página.
3. Las regiones se delimitan a partir de los encabezados detectados y de su relación entre sí, no mediante coordenadas absolutas, porcentajes fijos ni número fijo de renglones.
4. `Perfiles` se usa únicamente como frontera semántica; sus filas no ingresan al JSON de negocio ni a la base de datos.
5. Un interior se importa cuando contiene cantidad y medida válidas. Se clasifica como vidrio o tela sin eliminarlo.
6. Una fila de vidrio con cantidad `N` se conserva como una única fila con cantidad `N`. Filas distintas nunca se consolidan, aunque sean idénticas.
7. Las dimensiones se conservan en el orden impreso; no se reordenan ancho/alto.
8. Las cantidades de accesorios se guardan con tipo decimal exacto, nunca como punto flotante binario. No se almacena unidad.
9. La interpretación visual “decimal = metros / entero = unidades” es solo presentación; no modifica el valor ni agrega una unidad inferida al dato.
10. Los códigos se conservan como texto para no perder ceros iniciales (`T01`).
11. La consolidación final de accesorios se realiza por código normalizado para comparación, preservando el código visible original.
12. Si un mismo código consolidado presenta descripciones diferentes, no se elige una automáticamente: el resultado muestra el conflicto y exige revisión.
13. Un PDF escaneado, protegido, sin texto suficiente o con estructura distinta se rechaza de forma explicable en V1. No se incorporará OCR automático en la primera versión.

## 4. Casos borde y respuesta segura

| Caso | Comportamiento propuesto |
|---|---|
| Encabezado ausente, duplicado o ilegible | Bloquear confirmación de la página y mostrar diagnóstico |
| Dos tipologías en una página | No asumir; marcar estructura no soportada |
| Tipología repartida en dos páginas | No unir automáticamente; exigir revisión |
| Tabla vacía de interiores | Tipología válida con cero vidrios |
| Tabla vacía de accesorios | Tipología válida con cero accesorios, con aviso visible |
| Cantidad de tipología mayor que 1 | Advertencia; sin multiplicación |
| Cantidad de accesorio ilegible | Mantener fila revisable; no usarla en listado final hasta confirmar |
| Código fragmentado | Recomponer solo con evidencia tipográfica; registrar original y normalizado |
| Descripción multilínea | Unir solo por continuidad inequívoca |
| Código repetido en una misma página | Mantener filas separadas durante revisión; consolidar solo al final |
| Mismo código con detalles distintos | Conflicto bloqueante antes de finalizar |
| Decimal con coma | Normalizar a decimal exacto, conservando el texto original |
| Cantidad cero o negativa | Advertencia/error de validación; nunca corregir |
| Medida repetida | Mantener piezas independientes |
| Fila de vidrio con cantidad mayor que 1 | Mantener una fila con la cantidad original |
| Tela mezclada con vidrio | Importar ambas filas y marcar la tela por tipo |
| Caracteres corruptos `(cid:...)` | Baja confianza y revisión obligatoria |
| Página adicional sin tipología | No ignorar silenciosamente; informar página no reconocida |
| PDF duplicado | Detectar por hash y pedir confirmación antes de crear otra orden |

## 5. Estrategia de extracción

El motor será determinista y explicable:

1. Validar archivo, tamaño, cifrado, número de páginas y existencia de texto.
2. Calcular hash SHA-256 del PDF y crear una ejecución de extracción.
3. Extraer palabras y caracteres con metadatos de lectura.
4. Localizar encabezados por texto normalizado y variantes controladas.
5. Construir secciones relativas a esos encabezados.
6. Ignorar la sección `Perfiles`.
7. Parsear `Interiores`; conservar vidrios y telas sin consolidarlos ni expandirlos.
8. Parsear `Accesorios`; conservar valor original, normalizado y confianza.
9. Ejecutar validaciones cruzadas.
10. Producir un JSON versionado y una lista de advertencias/errores.

Las coordenadas del PDF podrán usarse internamente como evidencia para reconstruir renglones y columnas **solo después de localizar los encabezados**, nunca como posiciones fijas del diseño. Esto resulta necesario porque las tablas de `Perfiles/Interiores` y `Accesorios` están impresas en paralelo y el flujo de texto plano puede mezclarlas.

Cada campo extraído tendrá:

- valor original;
- valor normalizado;
- página;
- referencia a la fila de origen;
- confianza (`alta`, `media`, `baja`);
- advertencias asociadas.

No se propone inteligencia artificial generativa para decidir valores. Si en el futuro se agrega como asistente, su salida nunca reemplazará el parser determinista ni evitará la revisión.

## 6. JSON propuesto

El JSON operativo será versionado y distinguirá extracción original, estado de revisión y modificaciones. Ejemplo abreviado:

```json
{
  "schema_version": "1.0",
  "documento": {
    "id": "uuid",
    "archivo_nombre": "SEBASTIAN SOLSONA.pdf",
    "sha256": "...",
    "paginas_total": 11,
    "numero_presupuesto": "20169",
    "cliente": {
      "original": "S: OLSONA",
      "valor": "SOLSONA",
      "confianza": "media",
      "confirmado": false
    }
  },
  "extraccion": {
    "parser_version": "winmaker-v1",
    "fecha": "2026-07-18T00:00:00Z",
    "estado": "requiere_revision",
    "advertencias": []
  },
  "tipologias": [
    {
      "id": "uuid",
      "pagina": 10,
      "tipologia": {
        "original": "V6",
        "valor": "V6",
        "confianza": "alta"
      },
      "cantidad_tipologia": {
        "original": "1",
        "valor": 1,
        "confianza": "alta"
      },
      "detalle": {
        "original": "FRENTE",
        "valor": "FRENTE",
        "confianza": "alta"
      },
      "revision": {
        "estado": "pendiente",
        "confirmada_por": null,
        "confirmada_en": null
      },
      "vidrios": [
        {
          "id": "uuid",
          "cantidad": 1,
          "medida": "2470 x 749",
          "ancho": 2470,
          "alto": 749,
          "descripcion": "DVH 6+9+6",
          "origen": {
            "pagina": 10,
            "fila_id": "p10-interiores-1",
            "codigo_original": "DVH9",
            "cantidad_original_fila": 1,
            "texto_original": "DVH9 1 2470 x 749 DVH 6+9+6"
          },
          "confianza": "alta"
        }
      ],
      "accesorios": [
        {
          "id": "uuid",
          "codigo_original": "E69",
          "codigo": "E69",
          "cantidad_original": 16,
          "cantidad_final": 16,
          "detalle_original": "ESCUAD.ARMADO MARCOS Y HOJAS 35;6x10;6mm",
          "detalle_final": "ESCUAD.ARMADO MARCOS Y HOJAS 35;6x10;6mm",
          "estado": "detectado",
          "origen": "winmaker",
          "confianza": "alta",
          "excluido": false,
          "stock_ref": null,
          "ubicacion_ref": null
        }
      ],
      "advertencias": []
    }
  ],
  "modificaciones": [
    {
      "id": "uuid",
      "tipo": "cantidad_modificada",
      "entidad_tipo": "accesorio",
      "entidad_id": "uuid",
      "tipologia_id": "uuid",
      "pagina": 10,
      "campo": "cantidad",
      "valor_original": 18,
      "valor_anterior": 18,
      "valor_final": 36,
      "fecha": "2026-07-18T00:00:00Z",
      "usuario_id": null
    }
  ]
}
```

### Decisiones del modelo

- El JSON de extracción original será inmutable.
- Las modificaciones serán eventos anexados, no sobrescrituras destructivas.
- Se conservarán `cantidad_original` y `cantidad_final`.
- Un accesorio excluido permanece en el modelo.
- Los accesorios manuales tendrán `cantidad_original: null`, `origen: agregado_manualmente` y su evento de creación.
- Se dejan referencias opcionales para stock y ubicación, pero no se implementan esas funciones.
- Las exportaciones se generan desde una proyección validada del JSON y sus eventos, no desde el PDF.

## 7. Estados y reglas de revisión

### Tipología

- `pendiente`
- `en_revision`
- `confirmada`
- `requiere_atencion`

### Accesorio

- `detectado`
- `cantidad_modificada`
- `agregado_manualmente`
- `excluido`

### Reglas bloqueantes

No se podrá finalizar si:

- existe una tipología no confirmada;
- hay campos obligatorios de baja confianza sin confirmación;
- existe una fila no clasificable;
- hay un conflicto de descripción para el mismo código;
- una cantidad es inválida;
- alguna página del PDF no fue procesada o justificada.

Confirmar una tipología significa que el usuario revisó los datos mostrados, no que el parser “cree” que están bien.

## 8. Consolidación y exportaciones

### Vidrios y telas

- Una fila por fila original de Winmaker, conservando su cantidad.
- Sin consolidación.
- Orden estable: página y orden de fila de origen.
- Columnas: Cliente, Tipología, Detalle abertura, Cantidad, Medida, Descripción.
- Los valores editados y las observaciones se exportan; los originales permanecen en la trazabilidad.
- Excel y PDF se generan por listado activo. Los PDF usan orientación vertical.

### Accesorios

- Se excluyen los registros con estado `excluido`.
- Se agrupan únicamente por código normalizado.
- Las cantidades se suman con aritmética decimal exacta.
- Orden natural alfanumérico, sin ordenar por descripción.
- `Origen` consolidado:
  - `Winmaker`: todos los aportes son detectados y no modificados.
  - `Winmaker Modificado`: existe al menos un aporte Winmaker modificado.
  - `Agregado Manualmente`: todos los aportes son manuales.
  - `Mixto`: confluyen aportes Winmaker y manuales. Internamente se conservan los subtotales detectado, modificado y manual.

## 9. Arquitectura recomendada

Se recomienda un **monolito modular** para V1. Mantiene despliegue y operación simples, pero separa claramente dominios:

```text
PDF
  -> Ingesta y validación
  -> Motor Winmaker
  -> JSON original versionado
  -> Revisión + eventos de auditoría
  -> Proyecciones finales
  -> Exportadores
```

Módulos:

- `ingestion`: carga, hash, almacenamiento y validación.
- `parser_core`: contratos comunes, resultados, confianza y diagnósticos.
- `parsers/winmaker`: implementación versionada del formato Winmaker.
- `domain`: tipologías, vidrios, accesorios, estados y reglas.
- `review`: confirmaciones y modificaciones.
- `audit`: eventos append-only.
- `exports`: listado de vidrios y accesorios.
- `catalog`: futuro enlace a stock/ubicación.
- `api`: interfaz estable para web e integraciones futuras.
- `web`: interfaz responsive de revisión.

La lógica de parsing no dependerá de React, HTTP, base de datos ni componentes visuales. Recibirá un PDF y devolverá un resultado tipado. Esto permitirá probar el motor con un corpus creciente de órdenes reales.

## 10. Tecnologías recomendadas

- **Backend:** Python 3.12+ con FastAPI y Pydantic. Python tiene el ecosistema más directo para análisis de PDF; FastAPI aporta contratos OpenAPI claros y validación tipada.
- **PDF:** `pdfplumber` sobre `pdfminer.six` para palabras, caracteres, búsqueda de anclajes y depuración de tablas. Es adecuado para PDFs digitales y expone tanto texto como geometría.
- **Frontend:** React + TypeScript, con tablas accesibles y estado de servidor mediante TanStack Query. Sin animaciones como dependencia funcional.
- **Base de datos:** SQLite mediante SQLAlchemy. Cantidades con representación decimal exacta y JSON versionado como texto. La lógica de negocio no dependerá de características exclusivas de SQLite.
- **Migraciones/ORM:** SQLAlchemy 2 + Alembic.
- **Archivos:** almacenamiento local administrado en V1, detrás de una interfaz compatible posteriormente con S3.
- **Exportación:** XLSX y CSV como adaptadores independientes; PDF imprimible puede agregarse sin alterar el dominio.
- **Pruebas:** pytest, pruebas doradas de JSON, pruebas por página y regresión con PDFs anonimizados.
- **Despliegue:** aplicación local sencilla, sin servicios externos. El parsing puede ejecutarse inicialmente en el mismo proceso detrás de una interfaz desacoplada.

Referencias técnicas primarias:

- [pdfplumber](https://github.com/jsvine/pdfplumber)
- [FastAPI](https://fastapi.tiangolo.com/learn/)
- [PostgreSQL: tipos de datos](https://www.postgresql.org/docs/current/datatype.html)
- [React con TypeScript](https://react.dev/learn/typescript)

## 11. Plan de validación del parser

1. Crear resultados esperados revisados manualmente para las 36 páginas.
2. Verificar campos de encabezado página por página.
3. Verificar 56 filas de vidrio y 5 filas de tela, sin pérdida ni consolidación.
4. Verificar las 542 filas de accesorios antes de consolidar.
5. Probar códigos fragmentados, numéricos y con cero inicial.
6. Probar cantidades enteras, decimales y futuras comas decimales.
7. Probar descripciones repetidas, multilínea y conflictivas.
8. Confirmar que la tipología `MV6`, cantidad 2, emita advertencia sin multiplicar.
9. Comparar el listado final contra una revisión humana.
10. Añadir cada nuevo PDF real al corpus de regresión, debidamente anonimizado si corresponde.

Métricas mínimas para aceptar V1:

- 100% de páginas contabilizadas;
- 100% de telas presentes y correctamente clasificadas en el JSON;
- 100% de filas de baja confianza visibles para revisión;
- cero decisiones silenciosas sobre datos ambiguos;
- trazabilidad completa de cada cantidad final;
- pruebas de regresión reproducibles por versión del parser.

## 12. Decisiones finales aprobadas

1. **Vidrios:** conservar cada fila y su cantidad original; nunca expandir ni consolidar filas.
2. **Origen mixto:** utilizar `Mixto` y conservar subtotales por procedencia.
3. **Cliente:** ingreso manual obligatorio; extracción informativa y advertencias no bloqueantes.
4. **PDF escaneado:** rechazarlo en V1; no implementar OCR.
5. **Descripción conflictiva:** mostrar todas las variantes y bloquear solo la confirmación final hasta que el usuario confirme o edite la descripción final.
6. **Base de datos:** SQLite con SQLAlchemy, sin servidor externo y con portabilidad futura a PostgreSQL.

## 13. Iteración de identidad y edición

- Identidad visual DIVANNI con logo oficial y paleta azul, gris y turquesa.
- Vidrios y telas comparten estados: detectado, modificado, agregado manualmente y excluido.
- Cantidad, medida, descripción y observaciones conservan valores originales/finales y eventos de auditoría.
- Accesorios ordenados alfanuméricamente durante revisión y consolidación.
- Exportaciones Excel y PDF separadas por pestaña.
