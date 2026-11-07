# Запуск без ПК: GitHub Actions

Если компьютер не может работать круглосуточно, а Oracle недоступен,
самый простой бесплатный вариант — **GitHub Actions**: GitHub запускает
контейнер по расписанию, выполняет одну проверку слотов и завершает работу.
Ваш ПК при этом выключен.

```
GitHub Actions (cron в слоты каналов, матрица EN+ES)
  → checkout проекта
  → restore SQLite + schedule_state из кэша (свой на каждый язык)
  → python -m content_factory daemon --once
  → публикация в Telegram
  → save state в кэш + artifact с outbox/логами
```

Готовый workflow: [`.github/workflows/content-factory.yml`](../.github/workflows/content-factory.yml) —
workflow **`content-factory-cloud-en-es`**, матрица `lang = [en, es]`
(EN — `channels.en.yaml`, ES — `channels.es.yaml`).

## 1. Что это даёт и чего не даёт

**Даёт:**

- 0 ₽, без карты, без Oracle и без своего сервера;
- запуск в слоты каналов (EN — 16/сутки, ES — 6/сутки), время — по Москве;
- реальную публикацию в Telegram/VK, если заданы токены;
- сохранение SQLite и состояния расписания между запусками;
- артефакты с outbox, отчётами и логами.

**Не даёт:**

- мгновенного запуска: cron в GitHub может задерживаться на 5–20 минут;
- настоящего «always-on»: это периодический запуск, а не демон;
- бесплатных минут для приватных репозиториев (см. лимиты);
- локальной Ollama: в runner нет вашей модели и GPU.

## 2. Ограничения GitHub Actions

| Ограничение | Значение | Что делать |
|---|---|---|
| Минимальный шаг cron | 5 минут | 10 минут — нормально |
| Задержка запуска | 5–20 минут в пик | слоты публикации с запасом |
| Лимит job | 6 часов | тик занимает минуты |
| Минуты, публичный репозиторий | без лимита | **рекомендуется** |
| Минуты, приватный репозиторий | ~2 000 Linux/мес на Free | cron раз в час или self-hosted runner |
| Простой репозитория | scheduled workflows отключаются после ~60 дней без активности | держите репозиторий живым |
| Кэш | 10 ГБ, вытесняется после 7 дней без использования | запуски частые, но кэш может потеряться |
| Параллельные запуски | запрещены через `concurrency` | не убирайте |

Расчёт для приватного репозитория: cron каждые 10 минут — это 144 запуска в
день. Даже по 2 минуты это ~8 600 минут в месяц, то есть больше бесплатных
2 000. Поэтому:

- **публичный репозиторий** — 10 минут, бесплатно;
- **приватный** — cron раз в час (~1 440 минут) или self-hosted runner.

Код проекта открыт (MIT), секреты хранятся в Secrets и в логи не попадают.
Если публичный репозиторий не подходит — берите дешёвый VPS (раздел 8).

## 3. Пошаговая настройка

### Шаг 1. Репозиторий

1. Создайте репозиторий на GitHub (лучше **public**).
2. Загрузите проект `content-factory` вместе с папкой `.github/`.
3. Убедитесь, что `.env`, `data/` и токены не попали в git (они в `.gitignore`).

Если проект ещё не в git:

```bash
cd content-factory
git init
git add .
git commit -m "content factory + GitHub Actions"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### Шаг 2. Бот и каналы

1. Создайте бота у `@BotFather` (`/newbot`), получите токен.
2. Добавьте бота **администратором** в каждый канал с правом публикации.
3. Пропишите chat_id в `config/channels.yaml`:

```yaml
- id: tech-ai
  telegram_chat_id: '@my_tech_channel'
```

или задайте секреты `TELEGRAM_CHAT_ID_TECH_AI` и т. д. (имена — в workflow).
Chat_id не секретны; токен — секрет.

### Шаг 3. Секреты и переменные

В GitHub: **Settings → Secrets and variables → Actions**.

Секреты (Secrets):

- `TELEGRAM_BOT_TOKEN` — обязательно для публикации;
- `TELEGRAM_CHAT_ID_*` — если не хотите хранить chat_id в конфиге;
- `TELEGRAM_CHAT_ID_TECH_AI_ES`, `TELEGRAM_CHAT_ID_CRYPTO_ES`,
  `TELEGRAM_CHAT_ID_FUTBOL_ES` — chat_id испанских каналов (без них ES
  пропускается);
- `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` — основной LLM
  (Cloudflare Workers AI, free 10 000 neurons/день), работает и из РФ;
- `OPENROUTER_API_KEY`, `GROQ_API_KEY`, `SAMBANOVA_API_KEY`,
  `OLLAMA_API_KEY`, `HUGGINGFACE_API_KEY`, `OPENAI_API_KEY`,
  `DEEPSEEK_API_KEY` — резервные LLM;
  на раннерах GitHub Actions доступны и заблокированные в РФ
  OpenAI/Groq/OpenRouter;
- `YANDEXGPT_API_KEY`, `YANDEX_FOLDER_ID`, `GIGACHAT_CREDENTIALS`,
  `OPENAI_COMPAT_API_KEY` — российские/локальные провайдеры, если используете;
- `NEWSDATA_API_KEY`, `WORLD_NEWS_API_KEY`, `CURRENTS_API_KEY`,
  `APITUBE_API_KEY`, `TRENDS_API_KEY`, `GDELT_CLOUD_API_KEY`,
  `TAVILY_API_KEY`, `TAVILY_API_KEY_2` — новостные API и поиск (пустые
  значения безопасны: источник пропускается);
- `VK_ACCESS_TOKEN`, `VK_GROUP_ID`, `TG_API_ID`, `TG_API_HASH`, `TG_SESSION` —
  ВКонтакте и Telegram-источники (опционально);
- `DIFY_API_KEY`, `DIFY_BASE_URL`, `DIFY_POSTS_API_KEY`, `DIFY_NEWS_API_KEY`,
  `DIFY_TRENDS_API_KEY`, `DIFY_SEO_API_KEY` — Dify-интеграции (опционально).

Переменные (Variables):

- `CONTENT_FACTORY_DRY_RUN` — **по умолчанию workflow публикует по-настоящему**;
  поставьте `true`, чтобы включить безопасный dry-run (посты только в
  artifacts).
- `CONTENT_FACTORY_CHANNELS` больше не нужна: набор каналов задаёт матрица
  workflow (`en`/`es`). Для русских каналов добавьте `ru` в матрицу и
  `TELEGRAM_CHAT_ID_*`.

### Шаг 4. Первый запуск и проверка

1. Actions → `content-factory-cloud-en-es` → **Run workflow**: запустятся
   два джоба — `en` и `es`.
2. Дождитесь окончания (1–3 минуты на язык).
3. Откройте лог: шаг `Show channels and mode` покажет каналы и режим
   (`DRY-RUN` / публикация), шаг `Show LLM chain` — какие провайдеры живы.
4. Скачайте артефакт `content-factory-<lang>-<номер>`: там `data/outbox`,
   `data/reports`, `data/logs`.

Первый запуск может «догнать» последний слот за 24 часа — по одному на канал.
Перед боевым запуском можно поставить `CONTENT_FACTORY_DRY_RUN=true`.

### Шаг 5. Публикация

Workflow публикует по-настоящему по умолчанию. Чтобы проверить безопасно —
Variable `CONTENT_FACTORY_DRY_RUN=true`; для боевого режима уберите её или
поставьте `false`. Дальше cron работает сам.

Если хотите протестировать слот быстрее — временно поставьте в
`config/channels.yaml` время на 2–3 минуты вперёд (по МСК), дождитесь тика,
затем верните расписание.

## 4. Как хранится состояние

Между запусками сохраняются:

- `data/factory.sqlite3` — статьи, посты, публикации, метрики;
- `data/schedule_state.json` — последняя проверка и отработанные слоты.

Они кладутся в кэш GitHub (`actions/cache`) с ключом
`cf-state-<run_id>` и восстановлением по префиксу `cf-state-`.

Что важно:

- кэш **может быть вытеснен** (7 дней без использования или очистка);
- при потере кэша первый запуск снова сделает catch-up — возможен повтор
  последнего поста;
- если это критично, перенесите состояние в внешнее хранилище (Supabase,
  Cloudflare R2, отдельная ветка `state`) или на VPS с диском.

## 5. Модели: что выбрать в Actions

| Вариант | Ключи | Плюсы | Минусы |
|---|---|---|---|
| `extractive` (по умолчанию) | не нужны | 0 ₽, работает всегда | текст — «умный реферат» |
| YandexGPT | `YANDEXGPT_API_KEY`, `YANDEX_FOLDER_ID` | русский, публичный CA, пробный грант | после гранта платно |
| GigaChat | `GIGACHAT_CREDENTIALS` | бесплатный лимит, русский | нужны российские корневые сертификаты в runner, иначе SSL-ошибка |
| OpenAI-совместимый API | `OPENAI_COMPAT_API_KEY` | OpenRouter/Groq/Together и др. | доступность и лимиты зависят от сервиса |
| Ollama | — | локально бесплатно | в GitHub runner нет вашей модели; не вариант |

Как включить YandexGPT:

```yaml
# config/settings.yaml
llm:
  provider: yandexgpt
```

и добавьте секреты. GigaChat включается так же (`provider: gigachat`), но
на Ubuntu-runner нужно добавить сертификат НУЦ Минцифры в системное
хранилище — без этого будет `CERTIFICATE_VERIFY_FAILED`. Если не хотите
этим заниматься, начните с `extractive` или YandexGPT.

## 6. Мониторинг

- Actions присылает письмо при падении workflow (включите уведомления).
- Артефакты хранятся 7 дней; скачивайте `outbox`/`reports`.
- В логах ищите `ERROR`, `429`, `401`, `database is locked`.
- Для внешнего мониторинга добавьте пинг healthchecks.io после успешного
  шага (отдельный шаг workflow).
- Если постов нет несколько дней — проверьте `dry_run`, chat_id, права бота
  и доступность источников.

## 7. Типичные проблемы

| Симптом | Причина | Решение |
|---|---|---|
| workflow не запускается по расписанию | репозиторий неактивен, Actions выключены, cron на другой ветке | включите Actions, сделайте коммит, проверьте default branch |
| `DRY-RUN` в логе | переменная не задана или `true` | `CONTENT_FACTORY_DRY_RUN=false` |
| постов нет | нет наступившего слота, источники упали, нет chat_id | `channels`, `sources check`, логи |
| `401 Unauthorized` | неверный токен бота | перевыпустите токен, обновите секрет |
| `403`/`chat not found` | бот не админ или неверный chat_id | добавьте бота в канал |
| `429 Too Many Requests` | слишком частые публикации | увеличьте интервалы слотов |
| `database is locked` | два запуска одновременно | не убирайте `concurrency` |
| кэш не восстановился | первый запуск или кэш вытеснен | это нормально; состояние создастся заново |

## 8. Альтернативы без ПК

| Вариант | Цена | Когда подходит |
|---|---|---|
| **GitHub Actions** | 0 ₽ (public) | основной бесплатный вариант |
| Российский VPS (Timeweb, Selectel) | 200–600 ₽/мес | нужен настоящий 24/7 и свой IP |
| Yandex Cloud / VK Cloud | грант 1–2 месяца, потом платно | есть российская карта, нужен сервер в РФ |
| Google Apps Script | 0 ₽ | 1–2 канала, без карты, простой RSS→Telegram |
| n8n на VPS | 0 ₽ + VPS | нужен no-code и визуальные сценарии |
| Make free | 0 ₽, ~1 000 операций/мес | 1–2 канала, без своего сервера |
| Cloudflare Workers | 0 ₽, 100 тыс. запросов/день | лёгкий RSS→Telegram на JS |

Oracle не используется ни в одном варианте.

## 9. Безопасность

- токены — только в Secrets, не в `config/` и не в `.env` в репозитории;
- публичный репозиторий = публичный код; chat_id каналов не секрет, но
  подумайте, хотите ли их светить;
- не запускайте публикацию на первом прогоне — сначала dry-run;
- бот — только в свои каналы, без спама и массовых рассылок;
- авторские права: резюме + ссылки, без полных текстов; см.
  [legal.md](legal.md);
- логи и outbox могут содержать тексты статей — ограничьте доступ к
  артефактам, если репозиторий публичный.

## 10. Чек-лист

- [ ] Репозиторий создан, workflow на месте.
- [ ] Бот создан и добавлен админом в каналы.
- [ ] `TELEGRAM_BOT_TOKEN` в Secrets.
- [ ] chat_id в `config/channels.yaml` или в Secrets.
- [ ] `CONTENT_FACTORY_DRY_RUN=true`, первый запуск прошёл.
- [ ] Outbox проверен, тексты устраивают.
- [ ] `CONTENT_FACTORY_DRY_RUN=false`, тестовая публикация прошла.
- [ ] Уведомления Actions включены.
- [ ] Понятно, что делать при потере кэша.
