"""ES Telegram channel promo for X/Twitter via Buffer."""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from content_factory.integrations.buffer import BufferClient, BufferError
X_CHANNEL_ID = os.environ.get("BUFFER_X_CHANNEL_ID", "6951b346457dae6a34bd5e32").strip()
KEY_PATH = ROOT.parent / ".local" / "affiliate" / "buffer-api-key.txt"
STATE_PATH = ROOT / "data" / "buffer_es_channels_promo_state.json"
LOG_PATH = ROOT / "data" / "logs" / "buffer_es_channels_promo.jsonl"
MAX_WEIGHTED = 280
URL_RE = re.compile(r"https?://\S+")

CHANNELS = {
 "tech-ai-es": {
  "name": "ES AI News",
  "url": "https://t.me/WORLDNews0007",
  "image": "https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/docs/assets/channel-cards/tech-ai-es.png",
  "variants": [
   "La IA no para: nuevos modelos, herramientas y cambios que sí importan. En ES AI News lo resumimos en español, sin hype y sin hilos eternos.\n\nÚnete gratis: {url}\n\n#IA #Tecnología",
   "¿Sin tiempo para seguir la IA? En ES AI News tienes lo esencial en español: modelos, empresas, productos y regulación. Directo al grano.\n\nGratis en Telegram: {url}\n\n#InteligenciaArtificial #Tech",
   "IA explicada sin ruido. Cada día, lo que de verdad cambia en modelos, startups y política tecnológica, en español.\n\nSigue ES AI News: {url}\n\n#IA #Telegram",
  ],
 },
 "crypto-es": {
  "name": "ES Crypto & Blockchain",
  "url": "https://t.me/TechnologiesNews01",
  "image": "https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/docs/assets/channel-cards/crypto-es.png",
  "variants": [
   "Cripto se mueve rápido. En ES Crypto & Blockchain seguimos mercados, regulación y narrativas on-chain en español, con contexto y sin señales mágicas.\n\nGratis en Telegram: {url}\n\n#Cripto #Blockchain",
   "Bitcoin, Ethereum y regulación: lo que mueve el mercado, resumido en español y sin humo. Contexto, no gritos de 'lambo'.\n\nÚnete: {url}\n\n#Bitcoin #Cripto",
   "¿Cansado del ruido cripto? En ES Crypto & Blockchain tienes mercado, ETFs y regulación en español, con análisis claro y sin promesas.\n\nGratis: {url}\n\n#Blockchain #Cripto",
  ],
 },
 "futbol-es": {
  "name": "ES Sports News",
  "url": "https://t.me/SPORTSAnalytics007",
  "image": "https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/docs/assets/channel-cards/futbol-es.png",
  "variants": [
   "Fútbol, fichajes y análisis: LaLiga, Liga MX, Argentina y MLS en un solo canal en español. Sin relleno, solo lo que importa.\n\nSigue ES Sports News: {url}\n\n#Fútbol #LaLiga #LigaMX",
   "Resultados, fichajes y análisis táctico de LaLiga, Champions y selecciones. Todo en español, todos los días.\n\nÚnete gratis: {url}\n\n#Fútbol #Champions",
   "LaLiga, Liga MX y Argentina: la actualidad del fútbol en español, sin vueltas. Resultados, rumores y análisis en un solo lugar.\n\nSigue ES Sports News: {url}\n\n#Deportes #Fútbol",
  ],
 },
}
ORDER = ("tech-ai-es", "crypto-es", "futbol-es")

def weighted_length(text):
    return len(URL_RE.sub("x" * 23, text))

def load_state():
    try:
        data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_PATH)

def log_event(event):
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

def pick(state, requested=""):
    if requested:
        if requested not in CHANNELS:
            raise SystemExit("unknown channel: " + requested)
        key = requested
    else:
        key = ORDER[int(state.get("index", 0)) % len(ORDER)]
    variants = CHANNELS[key]["variants"]
    variant = int((state.get("variants") or {}).get(key, 0)) % len(variants)
    return key, variant

def build_text(key, variant):
    channel = CHANNELS[key]
    body = channel["variants"][variant].format(url=channel["url"])
    return body.rstrip() + "\n\nPublicidad"

def main(argv=None):
    parser = argparse.ArgumentParser(description="ES Telegram channel promo for X via Buffer")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--channel", default="", choices=("",) + ORDER)
    parser.add_argument("--mode", default="shareNow", choices=("shareNow", "addToQueue", "customScheduled"))
    parser.add_argument("--due-at", default="")
    parser.add_argument("--variant", type=int, default=-1)
    args = parser.parse_args(argv)
    state = load_state()
    key, variant = pick(state, args.channel)
    channel = CHANNELS[key]
    if args.variant >= 0:
        variant = args.variant % len(channel["variants"])
    text = build_text(key, variant)
    length = weighted_length(text)
    if length > MAX_WEIGHTED:
        raise SystemExit("%s variant %s: weighted %s > %s" % (key, variant, length, MAX_WEIGHTED))
    print(json.dumps({"channel": key, "name": channel["name"], "variant": variant, "weighted_len": length, "image": channel["image"], "mode": args.mode, "text": text, "live": args.live}, ensure_ascii=False, indent=2))
    if not args.live:
        print("dry-run: post not created")
        return 0
    token = os.environ.get("BUFFER_API_KEY", "").strip()
    if not token and KEY_PATH.exists():
        token = KEY_PATH.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("BUFFER_API_KEY is not set")
    client = BufferClient(token=token)
    try:
        post = client.create_post(X_CHANNEL_ID, text, mode=args.mode, due_at=args.due_at, assets=[{"image": {"url": channel["image"]}}])
    except BufferError as error:
        log_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "channel": key, "error": str(error)})
        raise SystemExit("Buffer error: %s" % error) from error
    state["index"] = (ORDER.index(key) + 1) % len(ORDER)
    state.setdefault("variants", {})[key] = (variant + 1) % len(channel["variants"])
    state.setdefault("posted", []).append({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "channel": key, "variant": variant, "buffer_id": post.get("id"), "status": post.get("status"), "url": post.get("externalLink")})
    state["posted"] = state["posted"][-50:]
    save_state(state)
    log_event({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "channel": key, "variant": variant, "result": post})
    print(json.dumps({"ok": True, "post": post}, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
