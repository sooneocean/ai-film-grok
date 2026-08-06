"""Title/end card + subtitle PNG helpers (peeled from render_final · W4 residual)."""

from __future__ import annotations

from pathlib import Path

from final.errors import RenderError
from final.media_ops import run
from PIL import Image, ImageDraw, ImageFont

FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]


def resolve_font(candidates: list[str] | None = None) -> str:
    """Resolve a Chinese-capable system font.

    ``candidates`` lets callers/tests override the search list (monkeypatch
    ``render_final.FONT_CANDIDATES`` then call the re-export wrapper).
    """
    for path in candidates if candidates is not None else FONT_CANDIDATES:
        if Path(path).is_file():
            return path
    raise RenderError("No Chinese-capable system font found")


def _wrap_title_lines(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        current += char
        if char in "，。！？… " or len(current) >= max_chars:
            lines.append(current.strip())
            current = ""
    if current.strip():
        lines.append(current.strip())
    return lines


def sub_png(
    text: str,
    path: Path,
    *,
    width: int,
    height: int,
    font_path: str,
    title: bool = False,
    dodge: bool = False,
    italic: bool = False,
) -> None:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    if title:
        font = ImageFont.truetype(font_path, max(42, width // 18))
        lines = _wrap_title_lines(text, 10)
        lh = font.size + 18
        total_h = len(lines) * lh
        y0 = (height - total_h) // 2
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            draw.text(
                (x, y0 + i * lh),
                line,
                font=font,
                fill=(255, 236, 242, 255),
                stroke_width=2,
                stroke_fill=(40, 10, 24, 255),
            )
    else:
        try:
            from subtitle_typesetter import break_text_semantically

            lines = break_text_semantically(text, max_chars=18)
        except Exception:
            lines = [text]

        font = ImageFont.truetype(font_path, max(30, width // 21))
        lh = font.size + 10
        total_th = len(lines) * lh
        bar_h = total_th + max(40, height // 20)

        text_img = Image.new("RGBA", (width, bar_h + 20), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_img)

        y0 = (bar_h - total_th) // 2

        for i, line in enumerate(lines):
            bbox = text_draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            y = y0 + i * lh

            shadow_offset = 3
            text_draw.text(
                (x + shadow_offset, y + shadow_offset),
                line,
                font=font,
                fill=(0, 0, 0, 180),
                stroke_width=3,
                stroke_fill=(0, 0, 0, 180),
            )
            text_draw.text(
                (x, y),
                line,
                font=font,
                fill=(255, 250, 252, 255),
                stroke_width=2,
                stroke_fill=(0, 0, 0, 255),
            )

        if italic:
            text_img = text_img.transform(
                (width, bar_h + 20),
                Image.AFFINE,
                (1, -0.25, 0.25 * (bar_h / 2), 0, 1, 0),
                resample=Image.BICUBIC,
            )

        if dodge:
            for dy in range(bar_h):
                a = int(120 + 70 * ((bar_h - dy) / max(1, bar_h - 1)))
                draw.line([(0, dy), (width, dy)], fill=(0, 0, 0, a))
            img.alpha_composite(text_img, (0, 0))
        else:
            for dy in range(bar_h):
                a = int(120 + 70 * (dy / max(1, bar_h - 1)))
                draw.line(
                    [(0, height - bar_h + dy), (width, height - bar_h + dy)], fill=(0, 0, 0, a)
                )
            img.alpha_composite(text_img, (0, height - bar_h))

    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def mkcard_video(
    text: str, out: Path, *, width: int, height: int, duration: float, fps: int, font_path: str
) -> None:
    """Title/end card: dark wine gradient + soft highlight (色气 short-film feel).

    Empty ``text`` → **blank pad** (same gradient, no glyphs). Used when designed
    post (HyperFrames/Remotion) owns title/end lettering so FFmpeg does not
    double-burn under the designed card.
    """
    work = out.parent
    png = work / f"{out.stem}_card.png"
    img = Image.new("RGB", (width, height), (12, 6, 14))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(18 + 22 * (1 - t))
        g = int(6 + 4 * (1 - t))
        b = int(22 + 18 * (1 - t))
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    draw.rectangle([0, 0, width, height // 8], fill=(0, 0, 0))
    draw.rectangle([0, height - height // 8, width, height], fill=(0, 0, 0))
    label = (text or "").strip()
    if label:
        font = ImageFont.truetype(font_path, max(40, width // 16))
        lines = _wrap_title_lines(label, max(16, len(label)))
        lh = font.size + 18
        y0 = (height - len(lines) * lh) // 2
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            tw = bbox[2] - bbox[0]
            x = (width - tw) // 2
            draw.text(
                (x, y0 + i * lh),
                line,
                font=font,
                fill=(255, 236, 242),
                stroke_width=2,
                stroke_fill=(40, 10, 24),
            )
    img.save(png)
    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-r",
            str(fps),
            "-i",
            str(png),
            "-t",
            f"{duration:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(out),
        ]
    )
