"""
Theme and Asset Manager for Steam Card Auto-Farmer: SecretBall Edition
Handles dynamic wallpaper generation, neon avatars, and styled widgets.
"""

import os
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageDraw, ImageTk

# --- Palette: SecretBall Cyber Edition (Vibrant & Stylish) ---
BG_DARK = "#070c16"         # Deep cyber midnight
BG_CARD = "#0d1728"         # Sleek modern navy card
BG_CARD_BORDER = "#1b2c4c"  # Card outline
BG_HOVER = "#1c3258"        # Interactive glow
BG_INPUT = "#080e1a"        # Deep inset
TEXT_WHITE = "#ffffff"
TEXT_LIGHT = "#cde4ff"      # Soft icy blue-white
TEXT_MUTED = "#738ba8"      # Subdued tech grey-blue

# Neon Accents
ACCENT_CYAN = "#00e5ff"     # SecretBall Electric Cyan
COLOR_LIME = "#00ff66"      # SecretBall Neon Lime
COLOR_GOLD = "#ffb300"      # Golden drop warning / count
COLOR_RED = "#ff2e55"       # Neon Crimson stop
COLOR_PURPLE = "#b347ff"    # Cyber boost purple
COLOR_BLUE = "#0088ff"      # Electric Blue

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SOURCE_PHOTO = os.path.join(ASSETS_DIR, "secretball.png")
AVATAR_HEADER_PATH = os.path.join(ASSETS_DIR, "avatar_header.png")
MASCOT_PATH = os.path.join(ASSETS_DIR, "mascot_card.png")
WALLPAPER_PATH = os.path.join(ASSETS_DIR, "wallpaper_styled.png")

_cached_wallpaper = None
_cached_wallpaper_size = (0, 0)
_cached_header_avatar = None
_cached_mascot = None

def ensure_assets():
    """Generates all stylish graphical assets if missing or needed."""
    if not os.path.exists(ASSETS_DIR):
        os.makedirs(ASSETS_DIR, exist_ok=True)

    if not os.path.exists(SOURCE_PHOTO):
        return

    if not os.path.exists(AVATAR_HEADER_PATH):
        _generate_header_avatar()

    if not os.path.exists(MASCOT_PATH):
        _generate_mascot()

    if not os.path.exists(WALLPAPER_PATH):
        _generate_wallpaper(1200, 800)

def _generate_header_avatar():
    try:
        raw = Image.open(SOURCE_PHOTO).convert('RGBA')
        size = (50, 50)
        crop_box = (150, 20, 480, 350)
        face = raw.crop(crop_box).resize(size, Image.Resampling.LANCZOS)
        face = ImageEnhance.Color(face).enhance(1.25)
        face = ImageEnhance.Contrast(face).enhance(1.15)

        mask = Image.new('L', (size[0]*4, size[1]*4), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size[0]*4, size[1]*4), fill=255)
        mask = mask.resize(size, Image.Resampling.LANCZOS)

        avatar = Image.new('RGBA', size, (0, 0, 0, 0))
        avatar.paste(face, (0, 0), mask=mask)

        final_size = (56, 56)
        avatar_bordered = Image.new('RGBA', final_size, (0, 0, 0, 0))
        b_draw = ImageDraw.Draw(avatar_bordered)
        b_draw.ellipse((0, 0, 55, 55), outline=(0, 229, 255, 255), width=2)
        b_draw.ellipse((2, 2, 53, 53), outline=(0, 255, 102, 200), width=1)
        avatar_bordered.paste(avatar, (3, 3), mask=mask)
        avatar_bordered.save(AVATAR_HEADER_PATH)
    except Exception as e:
        print(f"Error generating header avatar: {e}")

def _generate_mascot():
    try:
        raw = Image.open(SOURCE_PHOTO).convert('RGBA')
        target_w, target_h = 240, 290
        aspect = raw.width / raw.height
        card_img = raw.resize((int(target_h * aspect), target_h), Image.Resampling.LANCZOS)
        left = (card_img.width - target_w) // 2
        card_img = card_img.crop((left, 0, left + target_w, target_h))

        card_img = ImageEnhance.Color(card_img).enhance(1.25)
        card_img = ImageEnhance.Contrast(card_img).enhance(1.15)

        radius = 14
        mask = Image.new('L', (target_w * 4, target_h * 4), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.rounded_rectangle((0, 0, target_w * 4, target_h * 4), radius=radius*4, fill=255)
        mask = mask.resize((target_w, target_h), Image.Resampling.LANCZOS)

        mascot_card = Image.new('RGBA', (target_w, target_h), (0, 0, 0, 0))
        mascot_card.paste(card_img, (0, 0), mask=mask)

        b_draw = ImageDraw.Draw(mascot_card)
        b_draw.rounded_rectangle((1, 1, target_w - 2, target_h - 2), radius=radius, outline=(0, 229, 255, 230), width=3)
        b_draw.rounded_rectangle((4, 4, target_w - 5, target_h - 5), radius=radius-3, outline=(0, 255, 102, 160), width=1)

        mascot_card.save(MASCOT_PATH)
    except Exception as e:
        print(f"Error generating mascot: {e}")

def _generate_wallpaper(w, h):
    try:
        w = max(900, w)
        h = max(600, h)
        base = Image.new('RGBA', (w, h), (6, 11, 20, 255))
        draw = ImageDraw.Draw(base)
        for y in range(h):
            r = int(6 + (14 - 6) * (y / h))
            g = int(11 + (22 - 11) * (y / h))
            b = int(20 + (42 - 20) * (y / h))
            draw.line([(0, y), (w, y)], fill=(r, g, b, 255))

        lights = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        l_draw = ImageDraw.Draw(lights)
        l_draw.polygon([(w - 180, 0), (w - 20, 0), (w - 120, h), (w - 480, h)], fill=(0, 160, 255, 26))
        l_draw.polygon([(w - 380, 0), (w - 260, 0), (w - 200, h), (w - 600, h)], fill=(0, 255, 120, 18))
        base = Image.alpha_composite(base, lights)

        grid = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grid)
        for x in range(0, w, 45):
            g_draw.line([(x, 0), (x, h)], fill=(0, 200, 255, 6))
        for y in range(0, h, 45):
            g_draw.line([(0, y), (w, y)], fill=(0, 200, 255, 6))
        base = Image.alpha_composite(base, grid)

        if os.path.exists(SOURCE_PHOTO):
            raw = Image.open(SOURCE_PHOTO).convert('RGBA')
            char_h = int(h * 0.88)
            char_w = int(char_h * (raw.width / raw.height))
            char = raw.resize((char_w, char_h), Image.Resampling.LANCZOS)
            char = ImageEnhance.Color(char).enhance(1.25)
            char = ImageEnhance.Contrast(char).enhance(1.15)

            feather_mask = Image.new('L', (char_w, char_h), 255)
            fm_draw = ImageDraw.Draw(feather_mask)
            fade_px = 70
            for x in range(fade_px):
                alpha = int(255 * (x / fade_px))
                fm_draw.line([(x, 0), (x, char_h)], fill=alpha)
            for y in range(fade_px):
                alpha = int(255 * (y / fade_px))
                for x in range(char_w):
                    current = feather_mask.getpixel((x, y))
                    feather_mask.putpixel((x, y), min(current, alpha))

            glow = Image.new('RGBA', (char_w + 100, char_h + 100), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_draw.ellipse([30, 30, char_w + 70, char_h + 70], fill=(0, 220, 255, 55))
            glow_draw.ellipse([60, 60, char_w + 40, char_h + 40], fill=(0, 255, 100, 40))
            glow = glow.filter(ImageFilter.GaussianBlur(35))

            pos_x = w - char_w - 25
            pos_y = h - char_h
            base.paste(glow, (pos_x - 50, pos_y - 50), glow)
            base.paste(char, (pos_x, pos_y), feather_mask)

        left_dark = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        ld_draw = ImageDraw.Draw(left_dark)
        for x in range(w):
            if x < w * 0.58:
                alpha = 232
            else:
                t = (x - w * 0.58) / (w * 0.42)
                alpha = int(232 * max(0.0, 1.0 - t * 1.5))
            ld_draw.line([(x, 0), (x, h)], fill=(7, 12, 22, alpha))
        base = Image.alpha_composite(base, left_dark)
        base.save(WALLPAPER_PATH)
        return base
    except Exception as e:
        print(f"Error generating wallpaper: {e}")
        return None

def get_wallpaper_image(w, h):
    """Returns PhotoImage for Tkinter canvas at (w, h)."""
    global _cached_wallpaper, _cached_wallpaper_size
    if _cached_wallpaper and abs(_cached_wallpaper_size[0] - w) < 30 and abs(_cached_wallpaper_size[1] - h) < 30:
        return _cached_wallpaper

    if not os.path.exists(WALLPAPER_PATH):
        img = _generate_wallpaper(w, h)
    else:
        try:
            raw = Image.open(WALLPAPER_PATH)
            if abs(raw.width - w) > 40 or abs(raw.height - h) > 40:
                img = _generate_wallpaper(w, h)
            else:
                img = raw
        except Exception:
            img = _generate_wallpaper(w, h)

    if img:
        _cached_wallpaper = ImageTk.PhotoImage(img)
        _cached_wallpaper_size = (w, h)
        return _cached_wallpaper
    return None

def get_header_avatar():
    """Returns PhotoImage for header avatar."""
    global _cached_header_avatar
    if _cached_header_avatar:
        return _cached_header_avatar
    if not os.path.exists(AVATAR_HEADER_PATH):
        _generate_header_avatar()
    if os.path.exists(AVATAR_HEADER_PATH):
        _cached_header_avatar = ImageTk.PhotoImage(Image.open(AVATAR_HEADER_PATH))
        return _cached_header_avatar
    return None

def get_mascot_image():
    """Returns PhotoImage for mascot panel."""
    global _cached_mascot
    if _cached_mascot:
        return _cached_mascot
    if not os.path.exists(MASCOT_PATH):
        _generate_mascot()
    if os.path.exists(MASCOT_PATH):
        _cached_mascot = ImageTk.PhotoImage(Image.open(MASCOT_PATH))
        return _cached_mascot
    return None
