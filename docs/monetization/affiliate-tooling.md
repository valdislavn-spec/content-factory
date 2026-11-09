# Affiliate-инструмент: реестр ссылок, UTM, блоки и ротация

**Статус: внедрено 08.11.2026.** Закрывает разрыв «affiliate-документы есть — в постах
ничего не работает». Единый реестр ссылок + готовые блоки с обязательным раскрытием
«реклама» + правило «1 партнёрский блок на N постов» + учёт показов в growth-отчёте.

## Файлы

| Файл | Роль |
|---|---|
| [config/affiliates.yaml](../../config/affiliates.yaml) | программы (11), статусы, привязка к 6 каналам, раскрытие EN/ES, правило 1:5 |
| [content_factory/affiliates.py](../../content_factory/affiliates.py) | загрузка/валидация, UTM, блоки, ротация, учёт показов |
| [scripts/affiliates.py](../../scripts/affiliates.py) | CLI: `check`, `list`, `link`, `block`, `pins`, `plan` |
| [tests/test_affiliates.py](../../tests/test_affiliates.py) | 20 тестов без сети |

## CLI

```bash
# проверка конфига: что готово, что ждёт входа
./.venv/bin/python scripts/affiliates.py check

# готовая ссылка с UTM (под канал)
./.venv/bin/python scripts/affiliates.py link --channel crypto-news --program mylead
# → https://mylead.global/r/dJ67Qo?utm_source=tg_crypto_en&utm_medium=telegram&utm_campaign=partners

# блок «Партнёры» для закрепа (HTML для Telegram + plain)
./.venv/bin/python scripts/affiliates.py block --channel ai-news
./.venv/bin/python scripts/affiliates.py block --channel sport-news --log   # + growth-событие
./.venv/bin/python scripts/affiliates.py pins --json                        # блоки для всех каналов

# план вставок: каждый 5-й пост, программы чередуются
./.venv/bin/python scripts/affiliates.py plan --channel ai-news --posts 30
```

Учёт показов: `--log` пишет событие `affiliate_block` в SQLite →
`./.venv/bin/python -m content_factory growth --days 7` показывает `by_event/by_channel/by_source`.

## Статусы программ

| Статус | Что значит | Попадает в блоки |
|---|---|---|
| `ready` | ссылка есть, можно ставить | ✅ |
| `pending` | заявка/аккаунт в процессе | ❌ |
| `awaiting_login` | аккаунт есть, нужен вход (2FA/капча/SSO) | ❌ |
| `blocked` | гео/санкции/требования (BingX для US, ElevenLabs) | ❌ |

Сейчас `ready` только **2**: MyLead и Collaborator (реферальные ссылки сетей). Остальные
9 — `pending`/`awaiting_login`/`blocked`; когда появятся реф-ссылки, достаточно вписать
`url` и поставить `status: ready` — блоки и UTM подхватят автоматически.

## Правила, которые зашиты

- **Раскрытие «реклама»** — в каждом блоке (`Advertising / affiliate link` / `Publicidad
  / enlace de afiliado`), для спортивных каналов добавляется **18+**.
- **1 партнёрский блок на 5 обычных постов** (`rules.affiliate_every`), программы
  чередуются детерминированно (`AffiliateRotator`).
- **Только `ready` + валидный http(s) URL**; ссылки с плейсхолдерами и `javascript:`
  отбрасываются при загрузке.
- HTML экранируется (название программы/ссылка), чтобы не сломать пост.
- Без обещаний доходности — формулировки в `disclosure`.

## Как добавить программу

```yaml
programs:
  bitget:
    title: "Bitget"
    kind: affiliate
    status: ready                 # после получения реф-ссылки
    url: "https://partner.bitget.com/bg/XXXX"
    commission: "CPA $20–100"
channels:
  crypto-news:
    programs: [mylead, collaborator, bitget]
```

Проверить: `scripts/affiliates.py check` → `link --channel crypto-news --program bitget`.

## Интеграция с постами

Сейчас блоки вставляются **вручную** (закрепы, партнёрские посты) — так безопаснее:
каждый партнёрский пост виден редактору. Следующий шаг — авто-вставка в генератор:
`AffiliateRotator.for_post(index)` уже готов, вставлять блок на последнем сообщении поста
при `index % 5 == 0` и писать `log_block` при публикации; тогда `growth` покажет показы.

## Ограничения

- **Заработок сейчас ≈ $0**: 5 из 6 каналов ~3 подписчика; партнёрки начнут давать
  заметные цифры после роста аудитории (см. `tg-growth.md`).
- Две готовые ссылки — это **приглашения в CPA-сети**, а не офферы для аудитории;
  офферные трекинг-ссылки создаются в кабинетах MyLead/Admitad и т.п.
- Вход в кабинеты (MEXC/Bybit/Bitget/Kraken, Hotmart, Admitad) — 2FA/SSO/капча:
  без человека не автоматизируется.
- US-крипто: BingX/Bybit/OKX ограничены — для EN-канала только US-доступные программы.
- Беттинг — 18+ и гео-ограничения; никаких «гарантированных прогнозов».

Связанные документы: [monetization-map.md](monetization-map.md),
[links-report-2026-11-08.md](links-report-2026-11-08.md),
[referral-links-register.md](referral-links-register.md).
