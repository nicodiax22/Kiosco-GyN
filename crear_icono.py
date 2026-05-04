"""Genera kiosco.ico con diseño oscuro/amarillo"""
from PIL import Image, ImageDraw, ImageFont
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kiosco.ico")

def make_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Fondo redondeado oscuro
    pad = size // 12
    r = size // 5
    d.rounded_rectangle([pad, pad, size-pad, size-pad], radius=r, fill=(26, 18, 0, 255))

    # Techo del kiosco (trapecio)
    cx = size // 2
    roof_top = size * 18 // 100
    roof_bot = size * 38 // 100
    roof_left = size * 20 // 100
    roof_right = size * 80 // 100
    roof_tl = size * 28 // 100
    roof_tr = size * 72 // 100
    d.polygon([
        (roof_tl, roof_top), (roof_tr, roof_top),
        (roof_right, roof_bot), (roof_left, roof_bot)
    ], fill=(245, 200, 0, 255))

    # Frente de la tienda
    body_top = roof_bot
    body_bot = size * 82 // 100
    body_left = size * 20 // 100
    body_right = size * 80 // 100
    d.rectangle([body_left, body_top, body_right, body_bot], fill=(255, 255, 255, 255))

    # Puerta
    door_w = size * 18 // 100
    door_h = size * 24 // 100
    door_x = cx - door_w // 2
    door_y = body_bot - door_h
    d.rounded_rectangle([door_x, door_y, door_x+door_w, body_bot], radius=size//16, fill=(26, 18, 0, 255))

    # Ventana izquierda
    win_size = size * 12 // 100
    win_y = body_top + size * 8 // 100
    d.rounded_rectangle([body_left + size*8//100, win_y, body_left + size*8//100 + win_size, win_y + win_size],
                        radius=2, fill=(0, 87, 255, 200))

    # Ventana derecha
    d.rounded_rectangle([body_right - size*8//100 - win_size, win_y, body_right - size*8//100, win_y + win_size],
                        radius=2, fill=(0, 87, 255, 200))

    # Línea de base
    base_y = body_bot
    d.rectangle([body_left - size*4//100, base_y, body_right + size*4//100, base_y + size*6//100],
                fill=(245, 200, 0, 255))

    return img

sizes = [16, 32, 48, 64, 128, 256]
images = [make_icon(s) for s in sizes]
images[0].save(OUT, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[1:])
print(f"Icono creado: {OUT}")
