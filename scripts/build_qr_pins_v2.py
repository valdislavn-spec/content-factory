#!/usr/bin/env python3
"""Pinterest pins v2 — editorial poster style (2026 best practices)."""
from __future__ import annotations
import argparse, io, json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import segno

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_factory.integrations.partner_links import (
    load_partner_links,
    resolve_program_link,
    validate_link,
)

W, H = 1000, 1500
CREAM, INK, MUTED = (247, 242, 233), (20, 20, 20), (78, 78, 74)

PINS = [
 {"slug":"bali-budget-qr","tag":"BUDGET","headline":"BALI ON\nA BUDGET","promise":"7 days of rice terraces, surf and $3 meals","cta":"Find flights","program":"aviasales","accent":(34,160,120),"scene":"island"},
 {"slug":"dubai-weekend-qr","tag":"WEEKEND","headline":"DUBAI IN\n3 DAYS","promise":"Desert dunes, skyline and duty-free — one carry-on","cta":"Find flights","program":"aviasales","accent":(214,138,42),"scene":"desert"},
 {"slug":"winter-sun-qr","tag":"WINTER SUN","headline":"3 WINTER\nESCAPES","promise":"Lisbon 15°C · Dubai 25°C · Bali 30°C","cta":"Find flights","program":"aviasales","accent":(42,116,196),"scene":"coast"},
 {"slug":"europe-under-300-qr","tag":"BUDGET","headline":"EUROPE\nUNDER $300","promise":"A 3-night city break: cheapest months and booking windows","cta":"Find flights","program":"aviasales","accent":(176,62,92),"scene":"city"},
 {"slug":"travel-esim-qr","tag":"TRAVEL ESSENTIAL","headline":"TRAVEL eSIM\nTHAT WORKS","promise":"Install before you fly — data in 200+ countries","cta":"Get eSIM","program":"yesim","accent":(110,88,230),"scene":"city"},
 {"slug":"car-rental-qr","tag":"TRAVEL ESSENTIAL","headline":"CAR RENTAL\nNO SURPRISES","promise":"Local renters, clear fuel policy, excess cover","cta":"Rent a car","program":"localrent","accent":(222,104,44),"scene":"road"},
 {"slug":"flight-compensation-qr","tag":"TRAVEL MONEY","headline":"FLIGHT\nDELAYED?","promise":"You may be owed up to €600 — check in 2 minutes","cta":"Check my flight","program":"airhelp","accent":(26,152,148),"scene":"plane"},
]

def draw_scene(draw, box, accent, scene):
    x0,y0,x1,y1 = box; w,h = x1-x0, y1-y0
    for i in range(h):
        t = i/h
        r = int(accent[0]*0.45*(1-t) + 247*0.55 + 255*0.10*t)
        g = int(accent[1]*0.45*(1-t) + 242*0.55 + 235*0.10*t)
        b = int(accent[2]*0.45*(1-t) + 233*0.55 + 210*0.10*t)
        draw.line([(x0,y0+i),(x1,y0+i)], fill=(min(r,255),min(g,255),min(b,255)))
    sr = int(w*0.10); scx,scy = x0+int(w*0.73), y0+int(h*0.25)
    draw.ellipse((scx-sr,scy-sr,scx+sr,scy+sr), fill=(255,238,205))
    horizon = y0+int(h*0.64)
    layers = [(1.0,0.45),(0.8,0.62),(0.55,0.78)]
    for k,alpha in layers:
        c = tuple(int(v*alpha) for v in accent)
        pts=[(x0,y1),(x0,horizon+int(h*0.05*(1-alpha)))]
        for j in range(5):
            px = x0+int(w*(0.05+0.22*j)); ph = int(h*(0.10+0.06*((j*7+k*3)%3)))
            pts.append((px, horizon-ph))
        pts += [(x1,y1)]
        draw.polygon(pts, fill=c)
    py = y0+int(h*0.44)
    for xx in range(x0+int(w*0.10), x0+int(w*0.60), 48):
        draw.line([(xx,py),(min(xx+24,x0+int(w*0.60)),py)], fill=(255,255,255), width=5)
    px = x0+int(w*0.62)
    draw.polygon([(px,py-15),(px+38,py),(px,py+15),(px+7,py)], fill=(255,255,255))
    if scene=="city":
        for i,bw in enumerate((0.09,0.13,0.07,0.15,0.10)):
            bx = x0+int(w*(0.44+0.10*i)); bh = int(h*(0.14+0.06*(i%2)))
            draw.rectangle((bx,horizon-bh,bx+int(w*bw*0.5),horizon), fill=tuple(int(v*0.5) for v in accent))

def wrap(draw, text, font, max_w):
    out=[]
    for raw in text.split("\n"):
        words,cur = raw.split(), ""
        for w in words:
            probe=(cur+" "+w).strip()
            if draw.textlength(probe,font=font)<=max_w: cur=probe
            else:
                if cur: out.append(cur)
                cur=w
        if cur: out.append(cur)
    return out

def render(pin, out_dir):
    img=Image.new("RGB",(W,H),CREAM); draw=ImageDraw.Draw(img)
    fonts=ROOT/"assets"/"fonts"; inter=str(fonts/"Inter.ttf"); playfair=str(fonts/"PlayfairDisplay.ttf")
    brand=ImageFont.truetype(inter,26); tagf=ImageFont.truetype(inter,22)
    head=ImageFont.truetype(playfair,124); prom=ImageFont.truetype(inter,34)
    cta=ImageFont.truetype(inter,30); tiny=ImageFont.truetype(inter,22)
    accent=pin["accent"]
    tw=draw.textlength(pin["tag"],font=tagf)
    draw.rounded_rectangle((W-64-tw-44,64,W-64,112),radius=24,fill=INK)
    draw.text((W-64-tw-22,78),pin["tag"],font=tagf,fill=CREAM)
    y=248
    for line in wrap(draw,pin["headline"],head,W-128)[:3]:
        draw.text((64,y),line,font=head,fill=INK); y+=126
    y += 26
    draw.rectangle((64,y,64+132,y+10),fill=accent); y+=44
    for line in wrap(draw,pin["promise"],prom,W-128)[:2]:
        draw.text((64,y),line,font=prom,fill=MUTED); y+=44
    box=(64,780,W-64,1210)
    draw.rounded_rectangle(box,radius=34,fill=(255,255,255))
    scene=Image.new("RGB",(box[2]-box[0],box[3]-box[1]),(255,255,255))
    sdraw=ImageDraw.Draw(scene)
    draw_scene(sdraw,(0,0,scene.width,scene.height),accent,pin["scene"])
    mask=Image.new("L",scene.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((0,0,scene.width-1,scene.height-1),radius=26,fill=255)
    img.paste(scene,(box[0],box[1]),mask)
    qr=segno.make(pin["url"],error="m"); buf=io.BytesIO()
    qr.save(buf,kind="png",scale=10,border=2,dark="#141414",light="#ffffff"); buf.seek(0)
    qr_img=Image.open(buf).convert("RGB").resize((186,186))
    draw.rounded_rectangle((50,1238,50+186+28,1238+186+28),radius=22,fill=(255,255,255))
    img.paste(qr_img,(64,1252))
    ctext=pin["cta"]+"  \u2192"; cw=draw.textlength(ctext,font=cta)
    draw.rounded_rectangle((64+186+40,1358,64+186+40+cw+56,1428),radius=35,fill=INK)
    draw.text((64+186+40+28,1376),ctext,font=cta,fill=CREAM)
    draw.text((64,1464),"Ad",font=tiny,fill=MUTED)
    out_dir.mkdir(parents=True,exist_ok=True)
    path=out_dir/f"{pin['slug']}.png"; img.save(path,"PNG"); return path

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--out",default=str(ROOT/"docs"/"assets"/"pins"/"qr-v2")); args=ap.parse_args()
    out=Path(args.out)
    hub = "https://valdislavn-spec.github.io/content-factory/"
    links = load_partner_links()
    resolved = {}
    for pin in PINS:
        link = resolve_program_link(pin.get("program"), links, fallback=hub)
        problems = validate_link(link)
        if problems:
            print("pin %s: неактивная ссылка: %s" % (pin["slug"], "; ".join(problems)), file=sys.stderr)
            return 2
        resolved[pin["slug"]] = link
    meta=[]
    for pin in PINS:
        pin = dict(pin, url=resolved[pin["slug"]])
        p=render(pin,out); print("pin:",p)
        meta.append({"slug":pin["slug"],"file":str(p),"url":resolved[pin["slug"]],"program":pin.get("program","")})
    (out/"meta.json").write_text(json.dumps(meta,ensure_ascii=False,indent=1),encoding="utf-8")
    print("meta:",out/"meta.json"); return 0

if __name__=="__main__":
    raise SystemExit(main())
