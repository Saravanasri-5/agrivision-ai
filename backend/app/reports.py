import datetime as dt
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .engine import CLASSES, MODEL_VERSION


def _t(data: List[List[Any]], widths=None) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14532d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#9ca3af")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
    ]))
    return t


def build_pdf(path: str, study: Dict[str, Any], stats: Dict[str, Any], changes: Dict[str, Any],
              rows: List[Dict[str, Any]], year: int, a: int, b: int) -> None:
    ss = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title="AgriVision AI Report")
    h1, h2, body = ss["Title"], ss["Heading2"], ss["BodyText"]
    el: List[Any] = [Paragraph("AGRIVISION AI - Crop Intelligence Report", h1),
                     Paragraph("Satellite-Powered Agricultural Intelligence", body), Spacer(1, 10)]
    el += [Paragraph("1. Study Area", h2), _t([
        ["Field", "Value"], ["Study area", study["name"]], ["Area (km2)", f"{study['area_km2']:.2f}"],
        ["Observation year", str(year)], ["Periods compared", f"{a} vs {b}"],
        ["Report date", dt.date.today().isoformat()], ["Model", MODEL_VERSION + " (simulated Sentinel-2 features)"]],
        [5 * cm, 11 * cm]), Spacer(1, 8)]
    el += [Paragraph("2. Statistics", h2), _t([
        ["Metric", "Value"], ["Total parcels", stats["total_parcels"]], ["Total area (ha)", stats["total_area_ha"]],
        ["Agricultural area - Paddy + Banana (ha)", stats["agricultural_area_ha"]],
        ["Average confidence", f"{stats['avg_confidence'] * 100:.1f}%"]], [9 * cm, 7 * cm]), Spacer(1, 8)]
    el += [Paragraph("3. Crop Distribution", h2), _t(
        [["Class", "Parcels", "Area (ha)", "Share (%)"]] +
        [[c, stats["crop_count"][c], stats["crop_area_ha"][c], stats["crop_pct"][c]] for c in CLASSES]), Spacer(1, 8)]
    lv = stats["confidence_levels"]
    el += [Paragraph("4. Confidence Metrics", h2), _t([
        ["Level", "Parcels", "Share (%)"]] + [[k, v, round(100 * v / max(stats["total_parcels"], 1), 1)] for k, v in lv.items()]),
        Paragraph("High >= 80%, Medium 60-80%, Low < 60%. Predictions are capped at 97%; low-confidence parcels need field verification.", body),
        Spacer(1, 8)]
    ch_rows = [[k.replace("→", "to"), v["count"], v["area_ha"]] for k, v in changes["summary"].items()]
    el += [Paragraph(f"5. Detected Changes ({a} to {b})", h2),
           Paragraph(f"{changes['total_changed']} of {changes['total_parcels']} parcels changed class.", body),
           _t([["Change type", "Parcels", "Area (ha)"]] + ch_rows), Spacer(1, 8)]
    top = sorted(rows, key=lambda r: -r["area_ha"])[:30]
    el += [Paragraph("6. Parcel Summary (30 largest parcels)", h2), _t(
        [["Parcel", "Crop", "Area (ha)", "Confidence", "Level"]] +
        [[r["parcel_id"], r["crop_type"], r["area_ha"], f"{r['confidence'] * 100:.0f}%", r["confidence_level"]] for r in top])]
    doc.build(el)
