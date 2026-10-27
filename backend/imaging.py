import io
from typing import List, Optional
import pymupdf
from PIL import Image, ImageOps, ImageDraw, ImageStat

RENDER_ZOOM = 2.5  # ~180 dpi crops
AI_ZOOM = 1.4
OUTPUT_WIDTH = 1400
COL_PAD = 24


def render_page(doc, p: int, zoom: float = RENDER_ZOOM) -> Image.Image:
    pix = doc[p].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def page_jpeg(doc, p: int) -> bytes:
    return doc[p].get_pixmap(matrix=pymupdf.Matrix(AI_ZOOM, AI_ZOOM)).tobytes("jpeg", jpg_quality=85)


def magic_erase(img: Image.Image, boxes, white_boxes=None) -> Image.Image:
    """Fill each box with the median colour of its surroundings so shaded backgrounds stay seamless."""
    draw = ImageDraw.Draw(img)
    W, H = img.width, img.height
    for y0, x0, y1, x1 in boxes:
        bx = [W * max(0, x0 - 4) / 1000, H * max(0, y0 - 3) / 1000, W * min(1000, x1 + 4) / 1000, H * min(1000, y1 + 3) / 1000]
        ring = img.crop((max(0, int(bx[0]) - 10), max(0, int(bx[1]) - 10), min(W, int(bx[2]) + 10), min(H, int(bx[3]) + 10)))
        fill = tuple(int(v) for v in ImageStat.Stat(ring).median)
        draw.rectangle(bx, fill=fill)
    for y0, x0, y1, x1 in white_boxes or []:
        bx = [W * max(0, x0) / 1000, H * max(0, y0) / 1000, W * min(1000, x1) / 1000, H * min(1000, y1) / 1000]
        draw.rectangle(bx, fill="white")
    return img


def _ink_bbox(img: Image.Image):
    return ImageOps.invert(img.convert("L")).point(lambda p: 255 if p > 40 else 0).getbbox()


def trim_vertical(img: Image.Image, pad: int = 12) -> Image.Image:
    bbox = _ink_bbox(img)
    if not bbox:
        return img
    return img.crop((0, max(0, bbox[1] - pad), img.width, min(img.height, bbox[3] + pad)))


def x_bounds(img: Image.Image) -> Optional[List[int]]:
    bbox = _ink_bbox(img)
    return [bbox[0], bbox[2]] if bbox else None


def union_col(col: Optional[List[int]], b: Optional[List[int]]) -> Optional[List[int]]:
    if not b:
        return col
    return [min(col[0], b[0]), max(col[1], b[1])] if col else list(b)


def crop_parts(doc, parts, cache: dict, masks: list, white_masks=None) -> List[Image.Image]:
    crops = []
    for part in parts:
        if part.page not in cache:
            boxes = masks[part.page] if part.page < len(masks) else []
            white_boxes = white_masks[part.page] if white_masks and part.page < len(white_masks) else []
            cache[part.page] = magic_erase(render_page(doc, part.page), boxes, white_boxes)
        im = cache[part.page]
        crops.append(trim_vertical(im.crop((0, int(im.height * part.y0 / 1000), im.width, int(im.height * part.y1 / 1000)))))
    return crops


def finalize(crops: List[Image.Image], col: Optional[List[int]]) -> Image.Image:
    """Crop to the shared content column, stitch vertically, scale to the fixed output width."""
    w = crops[0].width
    x0, x1 = (max(0, col[0] - COL_PAD), min(w, col[1] + COL_PAD)) if col else (0, w)
    pieces = [trim_vertical(c.crop((x0, 0, x1, c.height))) for c in crops]
    gap = 16
    out = Image.new("RGB", (x1 - x0, sum(p.height for p in pieces) + gap * (len(pieces) - 1)), "white")
    y = 0
    for p in pieces:
        out.paste(p, (0, y))
        y += p.height + gap
    h = max(1, round(out.height * OUTPUT_WIDTH / out.width))
    return out.resize((OUTPUT_WIDTH, h), Image.LANCZOS)


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
