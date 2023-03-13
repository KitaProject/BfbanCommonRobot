from io import BytesIO

import cairosvg
from PIL import Image


def str_svg_2_png(svg_data: str) -> BytesIO:
    data = svg_data.encode()
    png = cairosvg.svg2png(data, scale=3)

    im = Image.open(BytesIO(png))
    x, y = im.size
    p = Image.new("RGBA", im.size, (255, 255, 255))
    p.paste(im, (0, 0, x, y), im)
    p.tobytes()

    bio = BytesIO()
    p.save(bio, format="PNG")
    bio.seek(0)

    return bio


