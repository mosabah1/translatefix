# -*- coding: utf-8 -*-
"""
يولّد translatefix.ico - حرفان بينهما سهم ذو رأسين.

اللون اخضر مزرق عمدا، لا ازرق layoutfix: الاداتان تعملان معا في شريط
المهام، فيجب ان تتميزا بلمحة لا بالتدقيق.
يُشغَّل مرة واحدة عند تغيير التصميم:  python make_icon.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

SIZE = 256
BG = (13, 148, 136)         # اخضر مزرق
FG = (255, 255, 255)
ACCENT = (153, 246, 228)    # فاتح للسهم


def pick_font(size, names=("segoeui.ttf", "tahoma.ttf", "arial.ttf")):
    for name in names:
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                            "Fonts", name)
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
    return ImageFont.load_default()


def centered(draw, xy, text, font, fill):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text((xy[0] - (right + left) / 2, xy[1] - (bottom + top) / 2),
              text, font=font, fill=fill)


def build():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=52, fill=BG)

    big = pick_font(104)
    centered(d, (SIZE * 0.30, SIZE * 0.34), "A", big, FG)
    centered(d, (SIZE * 0.70, SIZE * 0.34), "ع", big, FG)

    # سهم ذو رأسين اسفل الحرفين: ترجمة في الاتجاهين
    y = SIZE * 0.72
    d.line([(SIZE * 0.26, y), (SIZE * 0.74, y)], fill=ACCENT, width=13)
    d.polygon([(SIZE * 0.20, y), (SIZE * 0.31, y - 0.07 * SIZE),
               (SIZE * 0.31, y + 0.07 * SIZE)], fill=ACCENT)
    d.polygon([(SIZE * 0.80, y), (SIZE * 0.69, y - 0.07 * SIZE),
               (SIZE * 0.69, y + 0.07 * SIZE)], fill=ACCENT)

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "translatefix.ico")
    img.save(out, sizes=[(256, 256), (128, 128), (64, 64),
                         (48, 48), (32, 32), (16, 16)])
    print("كُتبت:", out)
    return out


if __name__ == "__main__":
    build()
