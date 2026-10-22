#!/usr/bin/env python3
"""MeowSynth's look on the MPC screen, redrawn from the original GUI's own bitmaps (assets/, see
re/extract_assets.py): the brushed blue panel, the cat, the black knobs with a yellow value arc, the grey
LCD boxes, the POLYCAT bar and the 4x5 pixel lettering.

    tools/meow_art.py images            -> images/ (page backgrounds, cat frames, knob and P.BEND filmstrips, POLYCAT)
    tools/meow_art.py theme <skin dir>  -> finishes a skin built by gen_vst.py: option buttons get the pixel
                                           lettering, and MPC's own name captions under the controls are
                                           dropped (the page art already names everything, as the original did)

Pillow only. Positions are page pixels (1280x628); layout.conf uses the same numbers + 86 in y."""
import json
import os
import random
import sys

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.path.join(HERE, "..")
ASSETS = os.path.join(PORT, "assets")
IMAGES = os.path.join(PORT, "images")
W, H = 1280, 628

YELLOW = (255, 228, 0)
WHITE = (255, 255, 255)
LCD_GREY = (158, 158, 158)

# ---- page geometry (shared with layout.conf) ---------------------------------------------------------
BEZEL = (24, 14, 432, 324)            # the cat's screen; the cat is 400x300 at (40, 26)
CAT = (40, 26, 400, 300)
BOX = (24, 350, 432, 196)             # logo + the five cats
LOGO_XY = (73, 362)
PANELS = [(484, 14, 772, 174), (484, 194, 772, 174), (484, 374, 772, 174)]
COLS = [580, 773, 966, 1159]          # knob centres
KNOB_DY, LABEL_DY, TITLE_DY = 96, 34, 8
SPEED = (942, 258, 240, 64)           # the popup's field (panel 2)
POLYCAT = (890, 560, 366, 48)
PRESET_SEG = (136, 33)                # enum_h sw x sh, rows of 3 + 2 centred on x=240, first row centred on y=458
PRESETS = ["CLEAR CAT", "OLD CAT", "MARCH CAT", "CATBAND", "GOSPEL CATS"]
FTYPES = ["LP", "HP", "BP1", "BP2", "NOTCH"]
SPEEDS = ["4 BAR", "2 BAR", "1 BAR", "2/1", "1/1", "1/2", "1/4", "1/8", "1/12", "1/16"]

# ---- the original's lettering: a 5-pixel-high face, read off the labels in panels.png; the letters and
# digits it never used are drawn to match ------------------------------------------------------------
FONT = {
    "A": "####/#..#/####/#..#/#..#", "B": "###./#.#./####/#..#/####", "C": "####/#.../#.../#.../####",
    "D": "###./#..#/#..#/#..#/###.", "E": "####/#.../####/#.../####", "F": "####/#.../###./#.../#...",
    "G": "####/#.../#.##/#..#/####", "H": "#..#/#..#/####/#..#/#..#", "I": "###/.#./.#./.#./###",
    "J": "..##/...#/...#/#..#/####", "K": "#..#/#..#/###./#..#/#..#", "L": "#.../#.../#.../#.../####",
    "M": "#####/#.#.#/#.#.#/#.#.#/#.#.#", "N": "#..#/##.#/#.##/#..#/#..#", "O": "####/#..#/#..#/#..#/####",
    "P": "####/#..#/#..#/####/#...", "Q": "####/#..#/#..#/#.#./##.#", "R": "####/#..#/####/#.#./#.##",
    "S": "####/#.../####/...#/####", "T": "###/.#./.#./.#./.#.", "U": "#..#/#..#/#..#/#..#/####",
    "V": "#..#/#..#/#.#./#.#./.#..", "W": "#.#.#/#.#.#/#.#.#/#.#.#/#####", "X": "#..#/#..#/.##./#..#/#..#",
    "Y": "#.#/#.#/###/.#./.#.", "Z": "####/...#/.##./#.../####",
    "0": "####/#..#/#..#/#..#/####", "1": "##./.#./.#./.#./###", "2": "####/...#/####/#.../####",
    "3": "####/...#/.###/...#/####", "4": "#..#/#..#/####/...#/...#", "5": "####/#.../####/...#/####",
    "6": "####/#.../####/#..#/####", "7": "####/...#/..#./.#../.#..", "8": "####/#..#/####/#..#/####",
    "9": "####/#..#/####/...#/####",
    ".": "./././././#", "/": "...#/..#./..#./.#../#...", ":": "./#/./#/.", "-": ".../.../###/.../...",
    " ": "../../../../..",
}


def text_width(s, scale):
    return sum(len(FONT[c].split("/")[0]) + 1 for c in s) * scale - scale


def draw_text(img, x, y, s, scale, fill=WHITE, shadow=(0, 0, 0, 110), anchor="left"):
    """Pixel text with its top-left at x,y (anchor "center": centred on x)."""
    if anchor == "center":
        x -= text_width(s, scale) // 2
    d = ImageDraw.Draw(img, "RGBA")
    for pass_fill, off in ((shadow, max(1, scale // 2)), (fill, 0)):
        if pass_fill is None:
            continue
        cx = x
        for c in s:
            rows = FONT[c].split("/")
            for r, row in enumerate(rows):
                for k, bit in enumerate(row):
                    if bit == "#":
                        d.rectangle([cx + k * scale + off, y + r * scale + off,
                                     cx + (k + 1) * scale - 1 + off, y + (r + 1) * scale - 1 + off], fill=pass_fill)
            cx += (len(rows[0]) + 1) * scale


def lcd(img, x, y, w, h, fill=LCD_GREY):
    """The original's grey display box: flat grey, a dark edge up and left, a light one down and right."""
    d = ImageDraw.Draw(img, "RGBA")
    d.rectangle([x - 2, y - 2, x + w + 1, y + h + 1], fill=(255, 255, 255, 70))
    d.rectangle([x - 2, y - 2, x + w - 1, y + h - 1], fill=(20, 32, 40, 230))
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=fill)
    d.rectangle([x, y, x + w - 1, y + 2], fill=tuple(int(c * 0.82) for c in fill))
    d.rectangle([x, y, x + 2, y + h - 1], fill=tuple(int(c * 0.82) for c in fill))


def panel(img, x, y, w, h):
    """A translucent lighter panel with a soft bevel, as in the original."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x + 3, y + 4, x + w + 3, y + h + 4], 8, fill=(0, 20, 30, 70))          # drop shadow
    d.rounded_rectangle([x, y, x + w, y + h], 8, fill=(255, 255, 255, 44), outline=(255, 255, 255, 90), width=2)
    d.line([x + 8, y + h, x + w - 6, y + h], fill=(10, 40, 55, 120), width=2)
    d.line([x + w, y + 8, x + w, y + h - 6], fill=(10, 40, 55, 120), width=2)
    img.alpha_composite(layer)


def screen(img, x, y, w, h):
    """The dark window the cat sits in."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([x, y, x + w, y + h], fill=(22, 40, 50, 205), outline=(8, 20, 28, 255), width=3)
    d.line([x + 2, y + h + 1, x + w + 1, y + h + 1], fill=(255, 255, 255, 80), width=2)
    d.line([x + w + 1, y + 2, x + w + 1, y + h + 1], fill=(255, 255, 255, 80), width=2)
    img.alpha_composite(layer)


def brushed():
    """The brushed blue metal: the original's own colours top to bottom (its clean left and right margins),
    stretched across the page, with fine horizontal streaks."""
    src = Image.open(os.path.join(ASSETS, "panels.png")).convert("RGB")
    cols = Image.new("RGB", (2, src.height))
    for i, x0 in enumerate((1, src.width - 9)):
        cols.paste(src.crop((x0, 0, x0 + 8, src.height)).resize((1, src.height), Image.BOX), (i, 0))
    base = cols.resize((W, H), Image.BICUBIC)
    rnd = random.Random(1)
    n = Image.new("L", (48, H))
    n.putdata([min(255, max(0, int(rnd.gauss(128, 46)))) for _ in range(48 * H)])
    streaks = n.resize((W, H), Image.BICUBIC).filter(ImageFilter.BoxBlur(1))
    return Image.blend(base, Image.merge("RGB", (streaks, streaks, streaks)), 0.10).convert("RGBA")


def left_column(img):
    screen(img, *BEZEL)
    panel(img, *BOX)
    logo = Image.open(os.path.join(ASSETS, "logo.png")).convert("RGBA").crop((0, 0, 167, 30)).resize((334, 60), Image.NEAREST)
    img.alpha_composite(logo, LOGO_XY)
    draw_text(img, 34, 566, "HTTP://KNOBSTER.ORG", 2, fill=(205, 224, 233), shadow=(0, 0, 0, 90))
    version = open(os.path.join(PORT, "VERSION")).read().strip()     # this port's version, as build.sh packages it
    draw_text(img, 34, 590, "MEOWSYNTH V.%s - MPC EDITION" % version, 2, fill=(205, 224, 233), shadow=(0, 0, 0, 90))


def knob_labels(img, panel_i, names):
    y = PANELS[panel_i][1] + LABEL_DY
    for cx, name in zip(COLS, names):
        if name:
            draw_text(img, cx, y, name, 3, anchor="center")


def background(page):
    img = brushed()
    left_column(img)
    for p in PANELS:
        panel(img, *p)
    px = PANELS[0][0] + 16
    if page == 0:
        draw_text(img, px, PANELS[0][1] + TITLE_DY, "MEOW ENVELOPE", 3)
        knob_labels(img, 0, ["M ATTACK", "E SUSTAIN", "O DECAY", "W RELEASE"])
        draw_text(img, (COLS[0] + COLS[1]) // 2, PANELS[1][1] + TITLE_DY, "VIBRATO", 3, anchor="center")
        knob_labels(img, 1, ["AMNT", "ATCK"])
        draw_text(img, SPEED[0] + SPEED[2] // 2, PANELS[1][1] + LABEL_DY, "SPEED", 3, anchor="center")
        lcd(img, *SPEED)
        for cx, name in zip(COLS, ["PORTA", "NOISE", "CHORUS", "P.BEND"]):
            draw_text(img, cx, PANELS[2][1] + LABEL_DY, name, 3, anchor="center")
    else:
        draw_text(img, px, PANELS[0][1] + TITLE_DY, "MEOW FILTER", 3)
        knob_labels(img, 0, ["CUTOFF", "RESONANCE", "ENV MOD", "FILTER MIX"])
        draw_text(img, px, PANELS[1][1] + TITLE_DY, "ENVELOPE FOLLOWER", 3)
        knob_labels(img, 1, ["ATTACK", "DECAY", "", "GAIN"])
        draw_text(img, px, PANELS[2][1] + TITLE_DY, "FILTER TYPE", 3)
    return img.convert("RGB")


def knob_strip(frames=64, size=176):
    """Black knob, chrome cap, a yellow arc that grows with the value (the original's knob, redrawn larger)."""
    ss = 2
    strip = Image.new("RGBA", (size, size * frames), (0, 0, 0, 0))
    for f in range(frames):
        t = f / (frames - 1)
        im = Image.new("RGBA", (size * ss, size * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        c, r = size * ss / 2, size * ss * 0.44
        d.ellipse([c - r + 5, c - r + 8, c + r + 5, c + r + 8], fill=(0, 15, 25, 70))             # shadow
        d.ellipse([c - r, c - r, c + r, c + r], fill=(18, 18, 18), outline=(52, 52, 52), width=4)
        if t > 0:
            ra = r * 0.86
            d.arc([c - ra, c - ra, c + ra, c + ra], 135, 135 + 285 * t, fill=YELLOW, width=int(r * 0.34))
        rc = r * 0.40
        d.ellipse([c - rc, c - rc, c + rc, c + rc], fill=(120, 120, 120), outline=(60, 60, 60), width=3)
        for k, (rr, col) in enumerate(((0.78, 170), (0.56, 210), (0.30, 245))):
            o = rc * 0.10 * (k + 1)
            d.ellipse([c - rc * rr - o, c - rc * rr - o, c + rc * rr - o, c + rc * rr - o], fill=(col, col, col))
        strip.paste(im.resize((size, size), Image.LANCZOS), (0, f * size))
    return strip


def bend_strip(size=176):
    """P.BEND: the original's grey number box, 1..12."""
    strip = Image.new("RGBA", (size, size * 12), (0, 0, 0, 0))
    for n in range(12):
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        lcd(im, 10, 26, size - 20, size - 52)
        draw_text(im, size // 2, size // 2 - 30, str(n + 1), 12, anchor="center", shadow=(60, 60, 60, 160))
        strip.paste(im, (0, n * size))
    return strip


def bar(w, h, label, scale, on):
    """A grey bar with lettering sunk into it; lit, the lettering glows white (the POLYCAT button)."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    lcd(im, 2, 2, w - 4, h - 4, fill=(150, 150, 150) if on else (134, 134, 134))
    ty = (h - 5 * scale) // 2
    if on:
        glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_text(glow, w // 2, ty, label, scale, fill=(255, 255, 255, 200), shadow=None, anchor="center")
        im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(scale)))
        draw_text(im, w // 2, ty, label, scale, fill=WHITE, shadow=None, anchor="center")
    else:
        draw_text(im, w // 2, ty, label, scale, fill=(96, 96, 96), shadow=(190, 190, 190, 160), anchor="center")
    return im


def option(w, h, label, scale, on, dark=False):
    """One option button: grey with white lettering; the chosen one is yellow with dark lettering."""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    off_fill = (30, 52, 64) if dark else (126, 132, 136)
    lcd(im, 2, 2, w - 4, h - 4, fill=YELLOW if on else off_fill)
    draw_text(im, w // 2, (h - 5 * scale) // 2, label, scale, fill=(24, 24, 24) if on else WHITE,
              shadow=None if on else (0, 0, 0, 110), anchor="center")
    return im


def images():
    os.makedirs(IMAGES, exist_ok=True)
    for page, name in enumerate(("bg_meow.png", "bg_filter.png")):
        background(page).save(os.path.join(IMAGES, name))
    cat = Image.open(os.path.join(ASSETS, "cat_strip.png")).convert("RGB")
    for f in range(12):
        cat.crop((0, 120 * f, 160, 120 * (f + 1))).resize(CAT[2:], Image.LANCZOS).save(os.path.join(IMAGES, "cat_%02d.png" % f))
    knob_strip().save(os.path.join(IMAGES, "knob_strip.png"))
    bend_strip().save(os.path.join(IMAGES, "bend_strip.png"))
    bar(POLYCAT[2], POLYCAT[3], "POLYCAT", 5, False).save(os.path.join(IMAGES, "polycat_off.png"))
    bar(POLYCAT[2], POLYCAT[3], "POLYCAT", 5, True).save(os.path.join(IMAGES, "polycat_on.png"))
    print("images:", ", ".join(sorted(os.listdir(IMAGES))))


# ---- finishing a built skin ---------------------------------------------------------------------------

def kind(c, ctype, label_type=None):
    cd = c.get("componentData", {})
    return cd.get("type") == ctype and (label_type is None or cd.get("data", {}).get("type") == label_type)


def placed_type(node, param):
    """The component type placed on the page for VST parameter index `param`."""
    if isinstance(node, dict):
        m = node.get("handle remapping", {}).get("map") or []
        if any(e.get("key") == "Data" and e.get("value") == "Parameter %d" % param for e in m):
            return node.get("componentData", {}).get("type")
        node = list(node.values())
    if isinstance(node, list):
        for v in node:
            t = placed_type(v, param)
            if t:
                return t
    return None


def theme(skin):
    """skin: the "Plugin Skins" folder gen_vst.py wrote."""
    path = os.path.join(skin, "TUI.json")
    tui = json.load(open(path))
    params = json.load(open(os.path.join(PORT, "params.json")))["params"]
    number_box = placed_type(tui, [p["key"] for p in params].index("bend"))   # P.BEND shows its own number
    dropped = moved = 0
    for d in tui["pageData"]["componentDefinitions"]["localComponentDefinitions"]:
        comps = d["value"].get("componentsData") or []
        names = [c for c in comps if kind(c, "Label", "Name")]
        if not names:
            continue
        if any(kind(c, "Knob") for c in comps):
            for c in comps:
                if kind(c, "Label", "Value"):
                    # the value moves up into the caption's place, right under the knob
                    x, _, w, h = c["bounds"]["bounds"].split()
                    c["bounds"]["bounds"] = "%s %s %s %s" % (x, names[0]["bounds"]["bounds"].split()[1], w, h)
                    moved += 1
        d["value"]["componentsData"] = [c for c in comps if not kind(c, "Label", "Name")
                                        and not (d["key"] == number_box and kind(c, "Label", "Value"))]
        dropped += len(names)
    json.dump(tui, open(path, "w"))
    # each option's two images, read from its button: gen_vst.py names popup ones by first use and shares them between
    # pickers with the same options (sh_po_N), so the file name says nothing about which option it shows
    images = {}
    for d in tui["pageData"]["componentDefinitions"]["localComponentDefinitions"]:
        for c in d["value"].get("componentsData") or []:
            if kind(c, "Button"):
                data = c["componentData"]["data"]
                images[d["key"]] = {"on": data["onImage"], "off": data["offImage"]}
    n = 0
    for key, labels, scale, dark in (("shSeg_preset_%d", PRESETS, 2, False), ("shSeg_ftype_%d", FTYPES, 3, False),
                                     ("shPopOpt_0_vib_speed_%d", SPEEDS, 3, True)):
        for i, label in enumerate(labels):
            for state in ("off", "on"):
                if (key % i) not in images:
                    sys.exit("theme: no button %s in TUI.json (did the layout change?)" % (key % i))
                f = os.path.join(skin, images[key % i][state])
                if not os.path.isfile(f):
                    sys.exit("theme: %s is missing (did the layout change?)" % os.path.basename(f))
                w, h = Image.open(f).size
                option(w, h, label, scale, state == "on", dark).save(f)
                n += 1
    print("theme: %d name captions dropped, %d values moved up, %d option images redrawn" % (dropped, moved, n))


def main():
    if sys.argv[1:] == ["images"]:
        images()
    elif len(sys.argv) == 3 and sys.argv[1] == "theme":
        theme(sys.argv[2])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
