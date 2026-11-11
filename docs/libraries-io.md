# Libraries.io: чем полезен (и чем нет) для content-factory

**Дата проверки: 8 ноября 2026 (live).** Сайт: <https://libraries.io>, API:
<https://libraries.io/api>. Проверялись только официальные страницы/эндпоинты и живые ответы API.

## TL;DR

**Полезен ограниченно, в прод не подключаю.** Это каталог метаданных open-source пакетов
(12,3 млн пакетов, 32 менеджера: npm, PyPI, Cargo, Go, Maven, NuGet и др.) с бесплатным API
по ключу. Для наших каналов (US/EN + LatAm/ES) он даёт **только одну новую возможность**:
единый фид «свежих релизов» из PyPI+npm+Cargo и т.п. — под рубрику «Open-source радар» для
`ai-news` и `tech-ai-es`. Для остальных каналов (crypto-news, sport-news, futbol-es, crypto-es)
он не нужен.

**Что лучше сделать вместо интеграции:** для «OSS-релизов» брать **GitHub Releases API**
(бесплатно, без регистрации: проверено — `200 OK`, релизы с notes) и **PyPI/npm registry JSON**
(бесплатно, без ключей: проверено `200`). Libraries.io нужен только если хотим **один запрос
сразу по всем экосистемам** — тогда бесплатный ключ (OAuth GitHub) и 60 запросов/мин.

## Проверенные факты

| Что | Проверено 2026-11-08 |
|---|---|
| Масштаб | 12 297 137 пакетов, 32 package manager'а (npm 6,21М, PyPI 969К, Go 855К, Maven 822К, …) |
| API | `https://libraries.io/api`, ключ `api_key=`; **бесплатно** для зарегистрированных |
| Регистрация | только OAuth: GitHub / GitLab / Bitbucket (email-регистрации нет); ключ — на странице аккаунта |
| Лимит | **60 запросов/мин** на ключ; превышение → `429` |
| Пагинация | `page` (с 1), `per_page` (по умолчанию 30, **максимум 100**) |
| Ключевой эндпоинт для контента | `GET /api/search?q=…&sort=latest_release_published_at&platforms=PyPI&per_page=50` |
| Сортировки search | `rank`, `stars`, `dependents_count`, `dependent_repos_count`, **`latest_release_published_at`**, `contributions_count`, `created_at` |
| Фильтры search | `languages`, `licenses`, `keywords`, `platforms` |
| Поля проекта | `latest_release_number`, `latest_release_published_at`, `stars`, `dependents_count`, `contributions_count`, `licenses`, `rank` (SourceRank), `repository_url`, `versions[]` |
| Другие эндпоинты | проект, зависимости версии, dependents, contributors, SourceRank, GitHub repo/зависимости, подписки (alerts) |
| Без ключа | часть эндпоинтов иногда отвечает (`/api/npm/express` → 200), но **search и github-эндпоинты → 401**; полагаться нельзя |
| Открытые данные | `/data` теперь редиректит на главную; актуальный дамп — Zenodo **808273 (v1.0.0, 15.06.2017, 5,89 ГБ, 311 млн строк)**; есть копия 12.01.2020 — **устарели, для контента не годятся** |
| Риск сервиса | баннер: **Tidelift (владелец libraries.io) покупается Sonar**; сам API описан как «limited and rate restricted», данные «not validated» |

## Что реально полезно для наших каналов

| Канал | Применимость | Что можно делать |
|---|---|---|
| `ai-news` (EN) | **средняя** | рубрика «Open-source радар»: новые релизы AI/LLM/agents-пакетов за 24 ч (search + sort по `latest_release_published_at`) |
| `tech-ai-es` (ES) | **средняя** | то же на испанском, для dev-аудитории LatAm |
| `crypto-news` / `crypto-es` | низкая | релизы web3-библиотек (ethers.js, web3.py) — слишком узко для новостного канала |
| `sport-news` / `futbol-es` | нет | пакетные метаданные не относятся к теме |
| Наш стек | разово | поиск библиотек по keyword/license/language (например, клиенты Mastodon/Bluesky/Telegram) — но GitHub search покрывает это лучше |

## Плюсы и минусы

**Плюсы:**
- один API на 32 экосистемы (npm/PyPI/Cargo/Go/…) — не надо обходить 5 реестров;
- сортировка по дате релиза → можно собрать «что вышло за сутки»;
- бесплатно, ключ за 1 минуту (если есть GitHub-аккаунт).

**Минусы:**
- данные «scraped and not validated» (честно написано на самом сайте);
- ключ обязателен для search; 60 запросов/мин;
- **открытые дампы устарели (2017/2020)** — офлайн-анализ на них не сделать;
- сервис в переходе (Tidelift → Sonar) — риск смены условий/закрытия;
- для «релизов» GitHub Releases API даёт **release notes и даты** бесплатно и без регистрации;
- контент «список пакетов» — низкая вовлечённость для широкой аудитории (нужна рубрика для dev-сегмента).

## Альтернативы (проверены сегодня)

| API | Ключ | Проверка | Чем лучше |
|---|---|---|---|
| **GitHub REST /releases** | нет (60/ч анонимно, 5000/ч с токеном) | `GET api.github.com/repos/bluesky-social/atproto/releases` → **200** | release notes, теги, даты, ссылки — готовый контент |
| **PyPI JSON** | нет | `pypi.org/pypi/requests/json` → **200** | новые версии Python-пакетов |
| **npm registry** | нет | `registry.npmjs.org/express/latest` → **200** | новые версии npm-пакетов |
| ecosyste.ms API | нет | из этой сети **000** (недоступен) | аналог libraries.io, но проверить не смогли |
| libraries.io | да (OAuth) | search → **401 без ключа** | единый фид по 32 экосистемам |

## Если всё-таки подключать (план, 0 ₽)

1. Получить бесплатный ключ: зайти на libraries.io через GitHub → Account → API key.
2. Добавить в `.env` (gitignored, права 600): `LIBRARIES_IO_API_KEY=…`.
3. `scripts/oss_radar.py` (новый, ~120 строк + тесты):
   - темы: AI/LLM/agents (PyPI, npm), crypto-библиотеки (отдельно, если понадобится);
   - `GET /api/search?q=<topic>&sort=latest_release_published_at&platforms=PyPI,npm&per_page=50`;
   - фильтр `latest_release_published_at` за последние 24 ч, лицензии MIT/Apache-2.0, отсев
     пакетов без репозитория; вывод — digest «N новых open-source релизов»;
   - кэш ответов на 1–6 ч (как в `llm_cache`), лимит 60/мин не превышается.
4. Подключить как источник только `ai-news` и `tech-ai-es` (опциональный источник, 1 пост/сутки).
5. Если рубрика не зайдёт — удалить источник, ключ остаётся в `.env`.

**Без ключа** можно сделать то же на GitHub Releases API (список ~50 AI-репозиториев), это
свободно и без регистрации — рекомендую начать с него, а libraries.io добавить как второй,
«кросс-экосистемный» источник.

## Рекомендация

- **Сейчас:** не подключать. Контент-ценность для 6 каналов низкая (2 из 6 — узкая dev-рубрика),
  дампы устарели, сервис в переходе.
- **Если нужна рубрика «Open-source радар»:** сначала GitHub Releases API (0 ₽, без ключа),
  затем — по желанию — libraries.io для PyPI+npm+crates в одном запросе.
- **Ключ заводить только под эту рубрику**, не «на всякий случай».

*Все проверки — 2026-11-08, команды и URL см. выше; данные не выдуманы, отсутствующее отмечено.*
