from __future__ import annotations

import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "XAUUSD盘中波动Regime驱动因素研究_基于MT5与开源多因子数据的实证分析.md"
PDF_PATH = ROOT / "XAUUSD盘中波动Regime驱动因素研究_基于MT5与开源多因子数据的实证分析.pdf"


def register_fonts() -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))


def build_styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="PaperTitleCN",
            parent=styles["Title"],
            fontName="STSong-Light",
            fontSize=20,
            leading=26,
            alignment=TA_CENTER,
            textColor=colors.black,
            spaceAfter=6,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperSubtitleCN",
            parent=styles["Heading2"],
            fontName="STSong-Light",
            fontSize=14,
            leading=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
            spaceAfter=16,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperHeading1CN",
            parent=styles["Heading1"],
            fontName="STSong-Light",
            fontSize=15,
            leading=20,
            alignment=TA_LEFT,
            textColor=colors.black,
            spaceBefore=12,
            spaceAfter=8,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperHeading2CN",
            parent=styles["Heading2"],
            fontName="STSong-Light",
            fontSize=12.5,
            leading=18,
            alignment=TA_LEFT,
            textColor=colors.black,
            spaceBefore=10,
            spaceAfter=6,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperBodyCN",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=10.5,
            leading=17,
            alignment=TA_JUSTIFY,
            textColor=colors.black,
            spaceAfter=8,
            firstLineIndent=0.75 * cm,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperBulletCN",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=10.2,
            leading=16,
            alignment=TA_LEFT,
            textColor=colors.black,
            spaceAfter=5,
            leftIndent=0.55 * cm,
            firstLineIndent=-0.35 * cm,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperCodeCN",
            parent=styles["BodyText"],
            fontName="Courier",
            fontSize=8.6,
            leading=12,
            textColor=colors.HexColor("#222222"),
            backColor=colors.HexColor("#f5f5f5"),
            borderColor=colors.HexColor("#cccccc"),
            borderWidth=0.5,
            borderPadding=4,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PaperTableCN",
            parent=styles["BodyText"],
            fontName="STSong-Light",
            fontSize=8.8,
            leading=11,
            alignment=TA_LEFT,
            textColor=colors.black,
            wordWrap="CJK",
        )
    )
    return styles


def transform_inline(text: str) -> str:
    code_tokens: list[str] = []

    def pull_code(match: re.Match[str]) -> str:
        code_tokens.append(match.group(1))
        return f"@@CODE{len(code_tokens) - 1}@@"

    text = re.sub(r"`([^`]+)`", pull_code, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("**", "")
    text = text.replace("*", "")
    text = html.escape(text)
    for idx, token in enumerate(code_tokens):
        text = text.replace(f"@@CODE{idx}@@", f"<font name='Courier'>{html.escape(token)}</font>")
    return text


def parse_table(lines: list[str], styles, available_width: float) -> Table:
    rows: list[list[str]] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if all(set(cell) <= {"-", ":"} for cell in cells):
            continue
        rows.append(cells)
    max_cols = max(len(row) for row in rows)
    col_width = available_width / max_cols
    para_rows = []
    for row in rows:
        padded = row + [""] * (max_cols - len(row))
        para_rows.append([Paragraph(transform_inline(cell), styles["PaperTableCN"]) for cell in padded])
    table = Table(para_rows, colWidths=[col_width] * max_cols, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9eef6")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#aab4c3")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def add_image(story, img_path: Path, caption: str, styles) -> None:
    if not img_path.exists():
        return
    img = Image(str(img_path))
    max_width = A4[0] - 4.4 * cm
    max_height = 9.0 * cm
    ratio = img.imageHeight / img.imageWidth
    img.drawWidth = max_width
    img.drawHeight = max_width * ratio
    if img.drawHeight > max_height:
        scale = max_height / img.drawHeight
        img.drawHeight = max_height
        img.drawWidth *= scale
    story.append(img)
    if caption:
        story.append(Spacer(1, 0.12 * cm))
        story.append(Paragraph(transform_inline(caption), styles["PaperBulletCN"]))
    story.append(Spacer(1, 0.28 * cm))


def add_page_number(canvas, doc):
    canvas.saveState()
    canvas.setFont("STSong-Light", 9)
    canvas.setFillColor(colors.HexColor("#444444"))
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"{doc.page}")
    canvas.restoreState()


def main() -> None:
    register_fonts()
    styles = build_styles()
    lines = MD_PATH.read_text(encoding="utf-8").splitlines()
    story = []
    available_width = A4[0] - 4.0 * cm

    title = ""
    subtitle = ""
    idx = 0
    if idx < len(lines) and lines[idx].startswith("# "):
        title = lines[idx][2:].strip()
        idx += 1
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx < len(lines) and lines[idx].startswith("## "):
        subtitle = lines[idx][3:].strip()
        idx += 1

    if title:
        story.append(Paragraph(transform_inline(title), styles["PaperTitleCN"]))
    if subtitle:
        story.append(Paragraph(transform_inline(subtitle), styles["PaperSubtitleCN"]))

    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        if stripped.startswith("## "):
            story.append(Paragraph(transform_inline(stripped[3:].strip()), styles["PaperHeading1CN"]))
            idx += 1
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(transform_inline(stripped[4:].strip()), styles["PaperHeading2CN"]))
            idx += 1
            continue
        image_match = re.match(r"^!\[([^\]]*)\]\((.+)\)$", stripped)
        if image_match:
            caption = image_match.group(1).strip()
            img_path = Path(image_match.group(2).strip())
            add_image(story, img_path, caption, styles)
            idx += 1
            continue
        if stripped.startswith("|"):
            table_lines = []
            while idx < len(lines) and lines[idx].strip().startswith("|"):
                table_lines.append(lines[idx])
                idx += 1
            story.append(parse_table(table_lines, styles, available_width))
            story.append(Spacer(1, 0.24 * cm))
            continue
        if stripped.startswith("- ") or re.match(r"^\d+\.\s+", stripped):
            bullets = []
            while idx < len(lines):
                current = lines[idx].strip()
                if current.startswith("- "):
                    bullets.append(current[2:].strip())
                    idx += 1
                    continue
                numbered = re.match(r"^(\d+)\.\s+(.*)$", current)
                if numbered:
                    bullets.append(f"{numbered.group(1)}. {numbered.group(2).strip()}")
                    idx += 1
                    continue
                break
            for bullet in bullets:
                story.append(Paragraph(transform_inline(f"- {bullet}"), styles["PaperBulletCN"]))
            continue

        block_lines = []
        while idx < len(lines):
            current = lines[idx].strip()
            if not current:
                idx += 1
                break
            if current.startswith("#") or current.startswith("|") or current.startswith("- ") or re.match(r"^\d+\.\s+", current) or current.startswith("!["):
                break
            block_lines.append(current)
            idx += 1
        block_text = " ".join(block_lines).strip()
        if not block_text:
            continue
        if block_text.startswith("`") and block_text.endswith("`") and block_text.count("`") >= 2:
            story.append(Paragraph(transform_inline(block_text), styles["PaperCodeCN"]))
        else:
            story.append(Paragraph(transform_inline(block_text), styles["PaperBodyCN"]))

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=2.1 * cm,
        bottomMargin=1.8 * cm,
        title=title or MD_PATH.stem,
        author="Codex",
    )
    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    print(f"Saved PDF: {PDF_PATH}")


if __name__ == "__main__":
    main()
