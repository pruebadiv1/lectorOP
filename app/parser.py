from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pdfplumber

PARSER_VERSION = "winmaker-v1"
REQUIRED_ANCHORS = ("tipologia", "cantidad", "detalle", "perfiles", "interiores", "accesorios")
TEXT_MINIMUM = 120


class ParserError(ValueError):
    pass


@dataclass
class Row:
    top: float
    words: list[dict[str, Any]]


def _id() -> str:
    return str(uuid.uuid4())


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower().strip()


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _decimal(text: str) -> Decimal:
    return Decimal(text.replace(",", "."))


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral() else float(value)


def _group_rows(words: list[dict[str, Any]], tolerance: float = 5.0) -> list[Row]:
    rows: list[Row] = []
    for word in sorted(words, key=lambda item: (item["top"], item["x0"])):
        if not rows or abs(rows[-1].top - word["top"]) > tolerance:
            rows.append(Row(word["top"], [word]))
        else:
            rows[-1].words.append(word)
    for row in rows:
        row.words.sort(key=lambda item: item["x0"])
    return rows


def _row_text(row: Row) -> str:
    return _clean(" ".join(word["text"] for word in row.words))


def _find_header_word(words: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    target = _fold(label).rstrip(":")
    for word in words:
        if _fold(word["text"]).rstrip(":") == target:
            return word
    return None


def _line_value(rows: list[Row], label: str) -> tuple[str, str]:
    target = _fold(label)
    pattern = re.compile(rf"\b{re.escape(target)}\s*:\s*(.+)", re.IGNORECASE)
    for row in rows:
        raw = _row_text(row)
        folded = _fold(raw)
        match = pattern.search(folded)
        if not match:
            continue
        colon = raw.find(":")
        value = raw[colon + 1 :].strip() if colon >= 0 else raw
        return value, raw
    return "", ""


def _header_columns(row: Row, labels: tuple[str, ...]) -> dict[str, tuple[float, float]]:
    result: dict[str, tuple[float, float]] = {}
    minimum_x = -1.0
    for label in labels:
        target = _fold(label).rstrip(".:")
        for word in row.words:
            if word["x0"] >= minimum_x and _fold(word["text"]).rstrip(".:") == target:
                result[label] = (word["x0"], word["x1"])
                minimum_x = word["x1"]
                break
    return result


def _column_boundaries(
    columns: dict[str, tuple[float, float]],
    labels: tuple[str, ...],
) -> list[float]:
    return [
        (columns[labels[index]][1] + columns[labels[index + 1]][0]) / 2
        for index in range(len(labels) - 1)
    ]


def _words_between(words: list[dict[str, Any]], start: float, end: float | None) -> list[dict[str, Any]]:
    return [
        word
        for word in words
        if word["x0"] >= start and (end is None or word["x0"] < end)
    ]


def _parse_interiors(
    page_number: int,
    rows: list[Row],
    header_row: Row,
    section_end: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    columns = _header_columns(header_row, ("Interiores", "Cant", "Medida", "Detalle"))
    if len(columns) != 4:
        return [], [
            {
                "code": "interiores_columnas_incompletas",
                "page": page_number,
                "severity": "error",
                "message": "No se pudieron identificar todas las columnas de Interiores.",
            }
        ]
    boundaries = _column_boundaries(columns, ("Interiores", "Cant", "Medida", "Detalle"))
    result: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    source_index = 0
    for row in rows:
        if row.top <= header_row.top + 5:
            continue
        cells = [
            _clean(" ".join(word["text"] for word in _words_between(row.words, columns["Interiores"][0], boundaries[0]))),
            _clean(" ".join(word["text"] for word in _words_between(row.words, boundaries[0], boundaries[1]))),
            _clean(" ".join(word["text"] for word in _words_between(row.words, boundaries[1], boundaries[2]))),
            _clean(" ".join(word["text"] for word in _words_between(row.words, boundaries[2], section_end))),
        ]
        code, quantity_text, measure_text, detail = cells
        if not any(cells):
            continue
        combined = _fold(" ".join(cells))
        material_type = (
            "mesh"
            if "tela" in _fold(code) or "tela aluminio" in combined or "tela mosquitera" in combined
            else "glass"
        )
        measure_match = re.search(r"(\d+)\s*[xX×]\s*(\d+)", measure_text)
        if not code or not quantity_text or not measure_match:
            warnings.append(
                {
                    "code": "interior_no_clasificable",
                    "page": page_number,
                    "severity": "error",
                    "message": f"Fila de Interiores no clasificable: {_row_text(row)}",
                    "source_text": _row_text(row),
                }
            )
            continue
        try:
            quantity = _decimal(quantity_text)
        except InvalidOperation:
            warnings.append(
                {
                    "code": "cantidad_vidrio_invalida",
                    "page": page_number,
                    "severity": "error",
                    "message": f"Cantidad de vidrio inválida: {quantity_text}",
                }
            )
            continue
        source_index += 1
        width, height = int(measure_match.group(1)), int(measure_match.group(2))
        result.append(
            {
                "id": _id(),
                "source_row": source_index,
                "material_type": material_type,
                "quantity_original": _json_number(quantity),
                "quantity_final": _json_number(quantity),
                "measure_original": f"{width} x {height}",
                "measure_final": f"{width} x {height}",
                "width": width,
                "height": height,
                "description_original": detail,
                "description_final": detail,
                "observations": "",
                "status": "detected",
                "origin": "winmaker",
                "excluded": False,
                "reviewed": True,
                "source": {
                    "page": page_number,
                    "row_id": f"p{page_number}-interiores-{source_index}",
                    "original_code": code,
                    "original_quantity": quantity_text,
                    "original_text": _row_text(row),
                },
                "confidence": "high",
            }
        )
    return result, warnings


def _parse_accessories(
    page_number: int,
    rows: list[Row],
    header_row: Row,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    columns = _header_columns(header_row, ("Accesorios", "Cant", "Detalle"))
    if len(columns) != 3:
        return [], [
            {
                "code": "accesorios_columnas_incompletas",
                "page": page_number,
                "severity": "error",
                "message": "No se pudieron identificar todas las columnas de Accesorios.",
            }
        ]
    boundaries = _column_boundaries(columns, ("Accesorios", "Cant", "Detalle"))
    accessories: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for row in rows:
        if row.top <= header_row.top + 5:
            continue
        code_tokens = _words_between(row.words, columns["Accesorios"][0], boundaries[0])
        quantity_tokens = _words_between(row.words, boundaries[0], boundaries[1])
        detail_tokens = _words_between(row.words, boundaries[1], None)
        code_original = _clean(" ".join(word["text"] for word in code_tokens))
        code = re.sub(r"\s+", "", code_original).upper()
        quantity_text = _clean(" ".join(word["text"] for word in quantity_tokens))
        detail = _clean(" ".join(word["text"] for word in detail_tokens))
        source_text = _row_text(row)
        if not code and not quantity_text and detail and accessories:
            accessories[-1]["detail_original"] = _clean(accessories[-1]["detail_original"] + " " + detail)
            accessories[-1]["detail_final"] = accessories[-1]["detail_original"]
            accessories[-1]["source"]["original_text"] += " " + source_text
            continue
        if not any((code, quantity_text, detail)):
            continue
        confidence = "high"
        row_warnings: list[str] = []
        if "(CID:" in code.upper() or "(cid:" in source_text:
            code = re.sub(r"\(CID:\d+\)", "", code, flags=re.IGNORECASE)
            confidence = "low"
            row_warnings.append("La capa de texto contiene caracteres corruptos.")
        try:
            quantity = _decimal(quantity_text)
        except InvalidOperation:
            warnings.append(
                {
                    "code": "accesorio_no_clasificable",
                    "page": page_number,
                    "severity": "error",
                    "message": f"Fila de Accesorios no clasificable: {source_text}",
                    "source_text": source_text,
                }
            )
            continue
        if not code:
            confidence = "low"
            row_warnings.append("No se pudo recuperar el código.")
        if not detail:
            confidence = "low"
            row_warnings.append("No se pudo recuperar la descripción.")
        accessory = {
            "id": _id(),
            "code_original": code_original,
            "code": code,
            "quantity_original": _json_number(quantity),
            "quantity_final": _json_number(quantity),
            "detail_original": detail,
            "detail_final": detail,
            "status": "detected",
            "origin": "winmaker",
            "confidence": confidence,
            "excluded": False,
            "reviewed": confidence == "high",
            "warnings": row_warnings,
            "observations": "",
            "source": {
                "page": page_number,
                "row_id": f"p{page_number}-accesorios-{len(accessories) + 1}",
                "original_text": source_text,
            },
            "stock_ref": None,
            "location_ref": None,
        }
        accessories.append(accessory)
        if confidence == "low":
            warnings.append(
                {
                    "code": "accesorio_baja_confianza",
                    "page": page_number,
                    "severity": "warning",
                    "entity_id": accessory["id"],
                    "message": f"Revise el accesorio recuperado como {code or 'sin código'}.",
                }
            )
    return accessories, warnings


def _extract_client_hint(rows: list[Row]) -> dict[str, Any]:
    for row in rows:
        text = _row_text(row)
        if _fold(text).startswith("cliente"):
            value = text.split(":", 1)[1].strip() if ":" in text else ""
            return {"original": value, "value": value, "confidence": "low"}
    return {"original": "", "value": "", "confidence": "low"}


def parse_winmaker_pdf(path: str | Path, manual_client: str) -> dict[str, Any]:
    file_path = Path(path)
    raw = file_path.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise ParserError("El archivo no es un PDF válido.")
    sha256 = hashlib.sha256(raw).hexdigest()
    try:
        pdf = pdfplumber.open(file_path)
    except Exception as exc:
        raise ParserError("No se pudo abrir el PDF. Verifique que no esté protegido o dañado.") from exc

    typologies: list[dict[str, Any]] = []
    global_warnings: list[dict[str, Any]] = []
    with pdf:
        if not pdf.pages:
            raise ParserError("El PDF no contiene páginas.")
        for page_number, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            if len(_clean(text)) < TEXT_MINIMUM:
                raise ParserError(
                    f"La página {page_number} no posee una capa de texto válida. "
                    "Cargue el PDF original exportado por Winmaker; los escaneos no son compatibles."
                )
            words = page.extract_words(x_tolerance=2, y_tolerance=2, keep_blank_chars=False)
            rows = _group_rows(words)
            found = {anchor: _find_header_word(words, anchor) for anchor in REQUIRED_ANCHORS}
            missing = [anchor for anchor, word in found.items() if word is None]
            if missing:
                raise ParserError(
                    f"La página {page_number} no mantiene la estructura esperada de Winmaker. "
                    f"Faltan encabezados: {', '.join(missing)}."
                )
            typology_value, typology_raw = _line_value(rows, "tipologia")
            quantity_value, quantity_raw = _line_value(rows, "cantidad")
            detail_value, detail_raw = _line_value(rows, "detalle")
            try:
                typology_quantity = int(re.search(r"\d+", quantity_value).group())  # type: ignore[union-attr]
            except (AttributeError, ValueError):
                raise ParserError(f"No se pudo leer la cantidad de tipología en la página {page_number}.")

            interior_header = next(
                row for row in rows if any(_fold(word["text"]).rstrip(":") == "interiores" for word in row.words)
            )
            accessory_header = next(
                row for row in rows if any(_fold(word["text"]).rstrip(":") == "accesorios" for word in row.words)
            )
            glasses, glass_warnings = _parse_interiors(
                page_number,
                rows,
                interior_header,
                found["accesorios"]["x0"],  # type: ignore[index]
            )
            accessories, accessory_warnings = _parse_accessories(page_number, rows, accessory_header)
            warnings = [*glass_warnings, *accessory_warnings]
            if typology_quantity > 1:
                warnings.append(
                    {
                        "code": "cantidad_tipologia_mayor_uno",
                        "page": page_number,
                        "severity": "warning",
                        "message": (
                            f"Esta tipología posee cantidad {typology_quantity}. Verifique manualmente "
                            "que los accesorios correspondan a una unidad o al total."
                        ),
                    }
                )
            global_warnings.extend(warnings)
            typologies.append(
                {
                    "id": _id(),
                    "page": page_number,
                    "typology": {
                        "original": typology_value,
                        "value": typology_value,
                        "confidence": "high",
                        "source_text": typology_raw,
                    },
                    "typology_quantity": {
                        "original": quantity_value,
                        "value": typology_quantity,
                        "confidence": "high",
                        "source_text": quantity_raw,
                    },
                    "detail": {
                        "original": detail_value,
                        "value": detail_value,
                        "confidence": "high",
                        "source_text": detail_raw,
                    },
                    "review": {
                        "status": "pending",
                        "confirmed_at": None,
                    },
                    "glasses": glasses,
                    "accessories": accessories,
                    "warnings": warnings,
                }
            )

    with pdfplumber.open(file_path) as client_pdf:
        client_hint = _extract_client_hint(_group_rows(client_pdf.pages[0].extract_words()))
    normalized_manual = _fold(manual_client)
    normalized_hint = _fold(client_hint["value"]).replace(":", "").strip()
    if normalized_hint and normalized_manual not in normalized_hint and normalized_hint not in normalized_manual:
        global_warnings.insert(
            0,
            {
                "code": "cliente_no_coincide",
                "page": 1,
                "severity": "warning",
                "message": "El cliente ingresado no coincide claramente con el texto de cliente recuperado del PDF.",
            },
        )

    return {
        "schema_version": "1.0",
        "document": {
            "id": _id(),
            "filename": file_path.name,
            "sha256": sha256,
            "total_pages": len(typologies),
            "manual_client": manual_client.strip(),
            "pdf_client_hint": client_hint,
        },
        "extraction": {
            "parser_version": PARSER_VERSION,
            "status": "requires_review" if global_warnings else "ready_for_review",
            "warnings": global_warnings,
        },
        "typologies": typologies,
        "modifications": [],
        "conflict_resolutions": {},
    }
