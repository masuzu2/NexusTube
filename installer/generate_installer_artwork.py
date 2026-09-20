# -*- coding: utf-8 -*-
"""
NexusTube Ultra-Modern MSI Artwork Generator
============================================
Generates pixel-perfect, 24-bit uncompressed BMP files for WiX Toolset v3:
1. WixUIDialog.bmp  (493 x 312 px) — Welcome & Exit dialogs
2. WixUIBanner.bmp  (493 x  58 px) — Top header on all intermediate dialogs

Aesthetic:
Dark OLED · Dynamic Neon Accent (Cyan/Emerald/Violet) · Glassmorphism · Studio Audio
"""

import os
import math
import struct
from PIL import Image, ImageDraw, ImageFont, ImageFilter

INSTALLER_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = r"C:\Windows\Fonts"

def get_font(name="segoeuib.ttf", size=14):
    path = os.path.join(FONTS_DIR, name)
    if os.path.exists(path):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    # Fallback to arial
    arial = os.path.join(FONTS_DIR, "arialbd.ttf" if "b" in name else "arial.ttf")
    if os.path.exists(arial):
        try:
            return ImageFont.truetype(arial, size)
        except Exception:
            pass
    return ImageFont.load_default()

def save_24bit_bmp(image: Image.Image, output_path: str):
    """
    Saves image as a clean, strictly compliant 24-bit uncompressed Windows BMP file.
    Guarantees compatibility with WiX Toolset light.exe and Windows Installer MSI engine.
    """
    rgb_im = image.convert("RGB")
    width, height = rgb_im.size
    pixels = rgb_im.load()

    # BMP row padding (must be multiple of 4 bytes)
    row_bytes = width * 3
    pad_bytes = (4 - (row_bytes % 4)) % 4

    pixel_data = bytearray()
    # BMP is stored bottom-up
    for y in range(height - 1, -1, -1):
        for x in range(width):
            r, g, b = pixels[x, y]
            pixel_data.extend([b, g, r]) # BGR order
        if pad_bytes:
            pixel_data.extend([0] * pad_bytes)

    file_size = 54 + len(pixel_data)
    bmp_header = struct.pack(
        '<2sIHHI',
        b'BM',
        file_size,
        0,
        0,
        54
    )
    dib_header = struct.pack(
        '<IIIHHIIIIII',
        40,          # Header size
        width,
        height,
        1,           # Color planes
        24,          # Bit depth
        0,           # Compression (none)
        len(pixel_data),
        2835,        # 72 DPI horizontal
        2835,        # 72 DPI vertical
        0,
        0
    )

    with open(output_path, "wb") as f:
        f.write(bmp_header)
        f.write(dib_header)
        f.write(pixel_data)

    print(f"[OK] Generated: {output_path} ({width}x{height}, {os.path.getsize(output_path)} bytes)")


# ==============================================================================
# 1. GENERATE WixUIDialog.bmp (493 x 312)
# ==============================================================================
def create_dialog_bmp():
    w, h = 493, 312
    banner_w = 164

    # High-res supersampling for razor sharp anti-aliasing (2x)
    scale = 2
    sw, sh = w * scale, h * scale
    sbanner_w = banner_w * scale

    canvas = Image.new("RGB", (sw, sh), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # ── Right Area: Studio Clean Backdrop (x: sbanner_w to sw) ────────────────
    for x in range(sbanner_w, sw):
        # Ultra subtle off-white gradient
        progress = (x - sbanner_w) / max(1, sw - sbanner_w)
        r = int(255 - progress * 4)
        g = int(255 - progress * 3)
        b = int(255 - progress * 1)
        draw.line([(x, 0), (x, sh)], fill=(r, g, b))

    # Bottom button area highlight divider on right side
    button_bar_y = int(268 * scale)
    draw.line([(sbanner_w, button_bar_y), (sw, button_bar_y)], fill=(226, 232, 240), width=int(1.5 * scale))
    # Bottom button bar area subtle slate tint
    for y in range(button_bar_y + 1, sh):
        draw.line([(sbanner_w, y), (sw, y)], fill=(248, 250, 252))

    # Decorative subtle watermark icon on upper right
    wm_cx = int(435 * scale)
    wm_cy = int(50 * scale)
    wm_r = int(28 * scale)
    for ring in range(3):
        rr = wm_r - ring * int(8 * scale)
        if rr > 0:
            draw.ellipse([(wm_cx - rr, wm_cy - rr), (wm_cx + rr, wm_cy + rr)], outline=(235, 240, 248), width=int(1.5 * scale))
    draw.polygon([
        (wm_cx - int(6 * scale), wm_cy - int(10 * scale)),
        (wm_cx - int(6 * scale), wm_cy + int(10 * scale)),
        (wm_cx + int(10 * scale), wm_cy)
    ], fill=(230, 236, 246))

    # ── Left Area: Deep OLED Cyberpunk Studio Banner (x: 0 to sbanner_w) ─────
    # Base dark gradient
    for y in range(sh):
        py = y / sh
        # Deep space dark OLED: #040509 -> #0A0D18 -> #05060B
        if py < 0.5:
            t = py / 0.5
            r = int(4 + t * 6)
            g = int(5 + t * 8)
            b = int(9 + t * 15)
        else:
            t = (py - 0.5) / 0.5
            r = int(10 - t * 5)
            g = int(13 - t * 7)
            b = int(24 - t * 13)
        draw.line([(0, y), (sbanner_w, y)], fill=(r, g, b))

    # Ambient Glow Orbs (Cyan & Violet)
    glow_layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)

    def draw_radial_glow(cx, cy, radius, color_rgb, max_alpha=120):
        for dr in range(radius, 0, -3):
            alpha = int(max_alpha * (1 - dr / radius) ** 1.8)
            glow_draw.ellipse(
                [(cx - dr, cy - dr), (cx + dr, cy + dr)],
                fill=(color_rgb[0], color_rgb[1], color_rgb[2], alpha)
            )

    # Cyan / Emerald center glow
    draw_radial_glow(int(82 * scale), int(140 * scale), int(75 * scale), (6, 182, 212), max_alpha=90)
    draw_radial_glow(int(82 * scale), int(140 * scale), int(45 * scale), (34, 197, 94), max_alpha=110)
    # Violet upper glow
    draw_radial_glow(int(65 * scale), int(70 * scale), int(60 * scale), (139, 92, 246), max_alpha=70)
    # Magenta bottom accent glow
    draw_radial_glow(int(90 * scale), int(240 * scale), int(50 * scale), (236, 72, 153), max_alpha=55)

    # Subtle tech grid lines in banner
    for gx in range(0, sbanner_w, int(20 * scale)):
        glow_draw.line([(gx, 0), (gx, sh)], fill=(255, 255, 255, 10), width=1)
    for gy in range(0, sh, int(20 * scale)):
        glow_draw.line([(0, gy), (sbanner_w, gy)], fill=(255, 255, 255, 10), width=1)

    # Composite glow layer
    canvas.paste(Image.alpha_composite(canvas.convert("RGBA"), glow_layer).convert("RGB"))
    draw = ImageDraw.Draw(canvas)

    # ── Header Branding in Banner (Top) ──────────────────────────────────────
    # Pill Badge: [ • STUDIO SUITE ]
    pill_x1 = int(24 * scale)
    pill_y1 = int(22 * scale)
    pill_x2 = int(140 * scale)
    pill_y2 = int(37 * scale)
    draw.rounded_rectangle([(pill_x1, pill_y1), (pill_x2, pill_y2)], radius=int(7 * scale),
                           fill=(12, 20, 34), outline=(6, 182, 212), width=int(1 * scale))
    # Glowing dot
    draw.ellipse([(pill_x1 + int(8 * scale), pill_y1 + int(5 * scale)),
                  (pill_x1 + int(14 * scale), pill_y1 + int(11 * scale))], fill=(34, 197, 94))
    font_badge = get_font("segoeuib.ttf", int(8 * scale))
    draw.text((pill_x1 + int(19 * scale), pill_y1 + int(2.5 * scale)), "STUDIO SUITE", fill=(6, 182, 212), font=font_badge)

    # Title: NEXUSTUBE
    font_title = get_font("segoeuib.ttf", int(17 * scale))
    draw.text((int(24 * scale), int(42 * scale)), "NEXUS", fill=(255, 255, 255), font=font_title)
    # Measure width of NEXUS
    bbox = draw.textbbox((int(24 * scale), int(42 * scale)), "NEXUS", font=font_title)
    draw.text((bbox[2] + int(2 * scale), int(42 * scale)), "TUBE", fill=(34, 197, 94), font=font_title)

    font_sub = get_font("segoeui.ttf", int(7.5 * scale))
    draw.text((int(24 * scale), int(64 * scale)), "NEXT-GEN AUDIO SUITE", fill=(148, 163, 184), font=font_sub)

    # ── Hero Element: 3D Holographic Music Disc / Equalizer Core ─────────────
    core_cx = int(82 * scale)
    core_cy = int(140 * scale)
    core_r  = int(38 * scale)

    # Outer neon soundwave rings
    for step in range(3):
        ring_r = core_r + int((step + 1) * 11 * scale)
        alpha_color = [(6, 182, 212), (139, 92, 246), (34, 197, 94)][step]
        draw.ellipse([(core_cx - ring_r, core_cy - ring_r), (core_cx + ring_r, core_cy + ring_r)],
                     outline=alpha_color, width=int(1.2 * scale))

    # Core glass disc
    draw.ellipse([(core_cx - core_r, core_cy - core_r), (core_cx + core_r, core_cy + core_r)],
                 fill=(15, 23, 42), outline=(6, 182, 212), width=int(2.5 * scale))
    inner_r = int(core_r * 0.72)
    draw.ellipse([(core_cx - inner_r, core_cy - inner_r), (core_cx + inner_r, core_cy + inner_r)],
                 fill=(8, 14, 28), outline=(34, 197, 94), width=int(1.8 * scale))

    # Play Icon triangle with glow
    triangle = [
        (core_cx - int(9 * scale), core_cy - int(14 * scale)),
        (core_cx - int(9 * scale), core_cy + int(14 * scale)),
        (core_cx + int(14 * scale), core_cy)
    ]
    draw.polygon(triangle, fill=(255, 255, 255))

    # Circular orbit dots
    for angle_deg in [30, 110, 195, 285]:
        rad = math.radians(angle_deg)
        dot_r = core_r + int(11 * scale)
        dot_x = core_cx + int(math.cos(rad) * dot_r)
        dot_y = core_cy + int(math.sin(rad) * dot_r)
        draw.ellipse([(dot_x - int(3 * scale), dot_y - int(3 * scale)),
                      (dot_x + int(3 * scale), dot_y + int(3 * scale))], fill=(34, 197, 94))

    # ── Dynamic Audio Spectrum Equalizer Bars (y: 200 to 245) ────────────────
    eq_x_start = int(22 * scale)
    eq_y_base  = int(238 * scale)
    bar_w      = int(6 * scale)
    bar_gap    = int(4 * scale)
    bar_heights = [12, 22, 34, 26, 42, 30, 48, 38, 28, 44, 20, 14]

    for idx, bh in enumerate(bar_heights):
        bx = eq_x_start + idx * (bar_w + bar_gap)
        actual_h = int(bh * scale * 0.75)
        by1 = eq_y_base - actual_h
        by2 = eq_y_base

        # Color gradient: Cyan -> Emerald -> Violet
        if idx < 4:
            bar_color = (6, 182, 212)
        elif idx < 8:
            bar_color = (34, 197, 94)
        else:
            bar_color = (139, 92, 246)

        draw.rounded_rectangle([(bx, by1), (bx + bar_w, by2)], radius=int(3 * scale), fill=bar_color)
        # Glowing peak pip
        draw.ellipse([(bx, by1 - int(4 * scale)), (bx + bar_w, by1 - int(1 * scale))], fill=(255, 255, 255))

    # ── Bottom Glass Feature Card (y: 250 to 295) ────────────────────────────
    card_x1 = int(18 * scale)
    card_y1 = int(250 * scale)
    card_x2 = int(148 * scale)
    card_y2 = int(296 * scale)
    draw.rounded_rectangle([(card_x1, card_y1), (card_x2, card_y2)], radius=int(8 * scale),
                           fill=(10, 16, 30), outline=(255, 255, 255), width=int(1 * scale))

    font_v = get_font("segoeuib.ttf", int(9 * scale))
    draw.text((card_x1 + int(10 * scale), card_y1 + int(6 * scale)), "NexusTube v3.2.0", fill=(255, 255, 255), font=font_v)

    font_tags = get_font("segoeui.ttf", int(7.5 * scale))
    draw.text((card_x1 + int(10 * scale), card_y1 + int(22 * scale)), "FLAC · Hi-Res · 4K UHD", fill=(6, 182, 212), font=font_tags)

    # ── Vertical Neon Laser Beam Divider (at x = sbanner_w) ──────────────────
    # Shadow line
    draw.line([(sbanner_w - int(2 * scale), 0), (sbanner_w - int(2 * scale), sh)], fill=(0, 0, 0), width=int(2 * scale))
    # Glowing neon line: Cyan top -> Emerald middle -> Violet bottom
    for y in range(sh):
        t = y / sh
        if t < 0.5:
            lt = t / 0.5
            r = int(6 + lt * (34 - 6))
            g = int(182 + lt * (197 - 182))
            b = int(212 + lt * (94 - 212))
        else:
            lt = (t - 0.5) / 0.5
            r = int(34 + lt * (139 - 34))
            g = int(197 + lt * (92 - 197))
            b = int(94 + lt * (246 - 94))
        draw.line([(sbanner_w, y), (sbanner_w + int(1.5 * scale), y)], fill=(r, g, b))

    # Downsample using high-quality Lanczos filter for razor-sharp antialiasing
    final_img = canvas.resize((w, h), Image.Resampling.LANCZOS)
    output_path = os.path.join(INSTALLER_DIR, "WixUIDialog.bmp")
    save_24bit_bmp(final_img, output_path)


# ==============================================================================
# 2. GENERATE WixUIBanner.bmp (493 x 58)
# ==============================================================================
def create_banner_bmp():
    w, h = 493, 58
    scale = 2
    sw, sh = w * scale, h * scale

    canvas = Image.new("RGB", (sw, sh), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    # Left & center background: Ultra-clean studio off-white gradient
    for x in range(sw):
        prog = x / sw
        r = int(255 - prog * 4)
        g = int(255 - prog * 3)
        b = int(255 - prog * 1)
        draw.line([(x, 0), (x, sh)], fill=(r, g, b))

    # Right side: Modern dark OLED studio badge (x: 360 to 480)
    badge_x1 = int(360 * scale)
    badge_y1 = int(8 * scale)
    badge_x2 = int(482 * scale)
    badge_y2 = int(48 * scale)

    # Dark badge container with rounded corners
    draw.rounded_rectangle([(badge_x1, badge_y1), (badge_x2, badge_y2)], radius=int(10 * scale),
                           fill=(11, 16, 30), outline=(6, 182, 212), width=int(1.5 * scale))

    # Mini animated equalizer inside badge
    mini_eq_x = badge_x1 + int(12 * scale)
    mini_eq_y = badge_y1 + int(28 * scale)
    m_heights = [10, 18, 24, 14, 20]
    for idx, mh in enumerate(m_heights):
        bx = mini_eq_x + idx * int(5 * scale)
        by = mini_eq_y - int(mh * scale * 0.7)
        color = (6, 182, 212) if idx % 2 == 0 else (34, 197, 94)
        draw.rounded_rectangle([(bx, by), (bx + int(3 * scale), mini_eq_y)], radius=int(1.5 * scale), fill=color)

    # Branding text inside badge
    text_x = badge_x1 + int(42 * scale)
    font_b1 = get_font("segoeuib.ttf", int(10 * scale))
    draw.text((text_x, badge_y1 + int(6 * scale)), "NEXUS", fill=(255, 255, 255), font=font_b1)
    bbox = draw.textbbox((text_x, badge_y1 + int(6 * scale)), "NEXUS", font=font_b1)
    draw.text((bbox[2] + int(2 * scale), badge_y1 + int(6 * scale)), "TUBE", fill=(34, 197, 94), font=font_b1)

    # Subtag inside badge: [ v3.2 PRO ]
    tag_x1 = text_x
    tag_y1 = badge_y1 + int(22 * scale)
    tag_x2 = tag_x1 + int(52 * scale)
    tag_y2 = tag_y1 + int(13 * scale)
    draw.rounded_rectangle([(tag_x1, tag_y1), (tag_x2, tag_y2)], radius=int(4 * scale),
                           fill=(17, 24, 39), outline=(34, 197, 94), width=int(1 * scale))
    font_tag = get_font("segoeuib.ttf", int(7 * scale))
    draw.text((tag_x1 + int(5 * scale), tag_y1 + int(1.5 * scale)), "v3.2.0 PRO", fill=(6, 182, 212), font=font_tag)

    # ── Bottom 2px Dual-Tone Neon Gradient Laser Line (Full width) ───────────
    line_y1 = sh - int(3 * scale)
    line_y2 = sh
    for x in range(sw):
        t = x / sw
        if t < 0.5:
            lt = t / 0.5
            r = int(6 + lt * (34 - 6))
            g = int(182 + lt * (197 - 182))
            b = int(212 + lt * (94 - 212))
        else:
            lt = (t - 0.5) / 0.5
            r = int(34 + lt * (139 - 34))
            g = int(197 + lt * (92 - 197))
            b = int(94 + lt * (246 - 94))
        draw.line([(x, line_y1), (x, line_y2)], fill=(r, g, b))

    # Downsample using Lanczos
    final_img = canvas.resize((w, h), Image.Resampling.LANCZOS)
    output_path = os.path.join(INSTALLER_DIR, "WixUIBanner.bmp")
    save_24bit_bmp(final_img, output_path)


if __name__ == "__main__":
    print("Generating ultra-modern MSI installer graphics...")
    create_dialog_bmp()
    create_banner_bmp()
    print("Done! Both WixUIDialog.bmp and WixUIBanner.bmp generated successfully.")
