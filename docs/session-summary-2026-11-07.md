# Сводка: 6–7 ноября 2026 (content-factory)

## 1. Что сделано

### a) Исследования и стратегия
- Разобрали **postman.com** под Telegram-канал: блог/RSS-фиды (blog.postman.com/feed), State of the API 2025 (5 700+ респондентов, 89% используют ИИ, 24% проектируют API для агентов), API Network, MCP-серверы; вывод — контент на английском, ниша свободна.
- Собрали гайд по росту Telegram-каналов (бесплатные/платные механики, цены интеграций, Telegram Ads, риски накрутки).
- Исследовали рынки **США и испаноязычных стран**: Telegram в США нишевый (крипто/AI/новости), ЛатАм — лучший ROI (Мексика 30+ млн, Аргентина 10–12 млн, Колумбия 8–10 млн); Telegram Ads через агентства, CPM EN ~$2,4–3, ES ~$3,6–4,8; цена подписчика ~$0,3–1,5.
- Подобрали и проверили источники: EN (TechCrunch, Verge, MIT TR, Wired, CNBC, OpenAI, NVIDIA, HF; CoinDesk, The Block, Decrypt, SEC, CFTC; ESPN, CBS, Sporting News, PFT, MLB.com) и ES (Hipertextual, FayerWayer, ABC Tecnología, La Nación, El Financiero; CriptoNoticias, BeInCrypto ES, CriptoTendencia, Observatorio Blockchain; ESPN lang=es, Relevo, 90min, La Nación/Deportes, El Universal/Deportes, Récord).

### b) Код и каналы
- Адаптер **ESPN JSON API** (`type: espn`, в т.ч. `lang: es` для футбола; RSS ESPN закрыт антиботом 202 — поэтому JSON).
- Фикс RSS: непустой `<description>` больше не перекрывает `<content:encoded>` (NVIDIA, DL News, PFT, ClutchPoints и др.).
- **Испанский язык в ядре**: `lang.py`, generator (промпты, стили, даты, хэштеги, CTA, fallback), analyzer, keywords (стоп-слова), sentiment, extractive; +84 ES-теста.
- **6 каналов**: 3 EN (US Sports News, AI News, Crypto & Blockchain) + 3 ES (ES AI News, ES Crypto & Blockchain, ES Sports News — переименованы из старых каналов, ID прописаны в конфигах).
- Брендинг: названия/описания применены через бота, логотипы и обложки, workflow `set-channel-photos`.
- **Фото-карточки** к постам (Playfair Display заголовок + Inter текст, fallback при ошибках), фикс парсинга card-текста, `publish-once` теперь соблюдает dry_run.
- Утренние доработки (не закоммичены): формат `interactive`, `content_mix` 30/40/30 story/analysis/interactive, ночной режим (до 900 символов), новые расписания, `trends.py` (Google Trends, CoinGecko, GitHub Trending, HN).

### c) Публикация и инфраструктура
- Приватный репозиторий **valdislavn-spec/content-factory**, 7 workflow, 16 секретов, `CONTENT_FACTORY_DRY_RUN=false`.
- Бот **@Novyi0007Bot** — администратор во всех 6 каналах (`can_post=True`).
- Первые живые посты опубликованы; каналы работают через числа ID, а не @username.
- **GitHub cron ненадёжен** (за сутки 3 schedule-запуска, 2 падения «0 steps» из-за дублирующего concurrency — исправлено).
- Поэтому поднят **Cloudflare Worker `tg-cron`** (cron `*/15`, антидубль 8 минут — дёргает `workflow_dispatch`); плюс существующий `telegram-proxy` (обход блокировки Telegram из РФ).
- Плавающее расписание: 16 триггеров со сдвигом +2…+19 минут от ровных слотов.
- Дубли постов (от ручных прогонов) удалены; добавлен workflow `delete-messages`.

## 2. Текущее состояние

| Параметр | Значение |
|---|---|
| Коммитов за сутки | 25 (HEAD `58b7be0`) |
| Тесты | **487 passed** |
| Каналы | 6 (3 EN + 3 ES), бот админ везде |
| Последние посты | AI News /13, US Sports News /12, Crypto & Blockchain /5997, ES AI News /11, ES Crypto /17, ES Sports News /8 |
| Публикации по логам | ~20 постов за сутки (ручные прогоны + cron) |
| Запуски Actions за 24ч | 26 (21 success, 2 cancelled, 2 failure → исправлено), ~0,5 мин/запуск |
| Планировщик | Cloudflare `tg-cron` `*/22` + 4 резервных GitHub-cron |
| LLM | ollama_cloud (gemma4:31b) → cloudflare → … → deepseek (последний fallback) |

## 3. Открытые вопросы и риски
1. **Actions-минуты**: снижены до `*/22` (~1500–1700 мин/мес) + 4 резервных GitHub-cron; до лимита Free остаётся запас. При желании можно сделать репозиторий публичным (безлимит).
2. **Незакоммиченные изменения** (`trends.py`, pipeline, configs, models) — доделать/закоммитить.
3. @username каналов остались старые (`@WORLDNews0007`, `@TechnologiesNews01`, `@SPORTSAnalytics007`) — меняются только вручную в Telegram.
4. Ключи и токены засветились в чате — после стабилизации перевыпустить.
5. Проверить качество постов и дубли при новых форматах/карточках.

## 4. Мониторинг и защита от сбоев (добавлено после сводки)
- Алерты в Telegram: падение workflow, сбой Cloudflare-диспатча, health «протух» (>2 ч без успешного запуска), пропуск cron (>45 мин). Антиспам — 3 часа.
- Health-endpoint воркера: https://tg-cron.valdislav-n.workers.dev/ (200/503 + JSON).
- Ежедневный heartbeat 09:00 UTC и еженедельный бэкап (artifact 90 дней).
- Состояние слотов дублируется в GitHub variable `CF_SCHEDULE_STATE` — потеря кэша больше не даёт дублей.
- Отдельный workflow-чек: если слоты были, а публикаций нет — run падает и приходит алерт.
- Исходники воркера лежат в репозитории: `cloudflare/`.
