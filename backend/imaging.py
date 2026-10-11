import io
from typing import List
import pymupdf
from PIL import Image, ImageOps, ImageDraw

RENDER_ZOOM = 2.5  # ~180 dpi crops
AI_ZOOM = 1.4


def render_page(doc, p: int, zoom: float = RENDER_ZOOM) -> Image.Image:
    pix = doc[p].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def page_jpeg(doc, p: int) -> bytes:
    return doc[p].get_pixmap(matrix=pymupdf.Matrix(AI_ZOOM, AI_ZOOM)).tobytes("jpeg", jpg_quality=85)


def trim_vertical(img: Image.Image, pad: int = 12) -> Image.Image:
    bbox = ImageOps.invert(img.convert("L")).point(lambda p: 255 if p > 40 else 0).getbbox()
    if not bbox:
        return img
    return img.crop((0, max(0, bbox[1] - pad), img.width, min(img.height, bbox[3] + pad)))


def stitch(parts: List[Image.Image]) -> Image.Image:
    w = max(p.width for p in parts)
    gap = 16
    out = Image.new("RGB", (w, sum(p.height for p in parts) + gap * (len(parts) - 1)), "white")
    y = 0
    for p in parts:
        out.paste(p, (0, y))
        y += p.height + gap
    return out


def apply_masks(img: Image.Image, boxes) -> Image.Image:
    draw = ImageDraw.Draw(img)
    for y0, x0, y1, x1 in boxes:
        draw.rectangle([img.width * max(0, x0 - 4) / 1000, img.height * max(0, y0 - 3) / 1000,
                        img.width * min(1000, x1 + 4) / 1000, img.height * min(1000, y1 + 3) / 1000], fill="white")
    return img


def render_question(doc, parts, cache: dict, masks: list) -> Image.Image:
    crops = []
    for part in parts:
        if part.page not in cache:
            boxes = masks[part.page] if part.page < len(masks) else []
            cache[part.page] = apply_masks(render_page(doc, part.page), boxes)
        im = cache[part.page]
        crop = im.crop((0, int(im.height * part.y0 / 1000), im.width, int(im.height * part.y1 / 1000)))
        crops.append(trim_vertical(crop))
    return stitch(crops)


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
