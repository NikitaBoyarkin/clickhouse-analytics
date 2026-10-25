# PRD — ClickHouse Analytics Lab

```yaml
title: "ClickHouse Analytics Lab"
date: 2026-09-28
updated: 2026-10-25
status: in progress
priority: P0
```

## Статус на 2026-10-25

Сверено с диском, не по памяти. Evidence-класс каждой строки: Verified = проверено
запуском/чтением кода; Missing = обещано, артефакта нет.

| # | Обещание PRD | Факт | Доказательство |
|---|---|---|---|
| 1 | 10 CH-кейсов на реальном сервере | 10 номеров: 01–09 одиночные `.sql`, 10 — каталог | `cases/01…09*.sql`, `cases/10_optimization/` |
| 2 | Ускорение ≥×10, воспроизводимо | ассерт `speedup >= 10`, медиана 3 прогона slow / 5 fast | `tests/test_cases.py:89-112` |
| 3 | `EXPLAIN PLAN` до/после | Missing — только закомментированная подсказка `-- EXPLAIN SELECT …` | `cases/10_optimization/fix.sql:20` |
| 4 | `clickhouse-benchmark`, N прогонов, p50/p95 | Missing — `statistics.median`, не p50/p95, не 100 прогонов | `tests/test_cases.py:98,104,108` |
| 5 | ≥8 перенесённых паттернов | 8: funnel, retention, sessionization, gaps-and-islands, top-N, LTV, attribution, RFM | `cases/01…08` |
| 6 | README с интерпретацией **каждого** кейса | Partial — сводка + разбор `avg(amount)`, по-кейсного разбора нет | `README.md:20-58` |
| 7 | `cases/expected.json` | 9 ключей; кейс 10 не снапшотится — он про время, не про строки | `cases/expected.json` |
| 8 | seed ≥50M строк | 50 000 000 ровно | `scripts/seed.py:18`, `tests/test_cases.py:62` |
| 9 | `explain_slow.md`, `explain_fast.md`, `benchmark.md` | Missing — 0 файлов `.md` в `cases/` | `cases/10_optimization/` |
| 10 | Docker CH 24.8, uv, clickhouse-connect, pandas, pytest | Есть | `docker-compose.yml:3`, `pyproject.toml:5-13` |

**Итог:** 6 из 10 обязательств закрыты. Ядро (кейсы + ускорение + паттерны + seed)
готово; не закрыт **измерительный слой** кейса 10 — EXPLAIN и benchmark. Плюс
`cases/expected.json` не версионировался: каталог `cases/` был под игнором
`00 portfolio/.gitignore:61` (правило `cases/` без якоря), из-за чего свежий клон
падал на `FileNotFoundError: cases/expected.json` (6 failed / 3 passed, замерено).
Исправлено 2026-10-25: правило заякорено на `/cases/`.

Закрыто 2026-10-25:

- `README.md` приведён в соответствие с кодом: было «p50/p95 over 100 runs» и «~100×»,
  стало «median of 3 and 5 runs» и «`speedup >= 10` asserted»; сняты заявления об
  EXPLAIN/benchmark как о готовых артефактах.
- `numpy` добавлен в `[project].dependencies` (`pyproject.toml`), `uv.lock` пересобран.

Осталось (блокировано: нужна живая лаборатория, `docker compose up -d`):
`cases/10_optimization/explain_slow.md`, `explain_fast.md`, `benchmark.md`.

Порядок для следующей сессии (Docker Desktop должен быть не на паузе):

```bash
docker compose up -d                       # CH 24.8, HTTP :8123
uv run python scripts/seed.py              # MergeTree events = 50 000 000
uv run python scripts/run.py               # все кейсы сверяются с expected.json
# EXPLAIN до:  EXPLAIN PLAN SELECT ... WHERE product_id = 42 AND event_type = 4
# затем cases/10_optimization/fix.sql (ADD + MATERIALIZE PROJECTION p_product)
# EXPLAIN после: тот же SELECT, план должен ссылаться на events.p_product
# benchmark: clickhouse-benchmark, N>=100 прогонов, p50/p95 до и после
uv run pytest -q
```

Заодно проверить расхождение кейса 06 (см. `cases.md`): после `--snapshot`
`payer_pct` должен стать ~81.3%, а не 100.0 — если останется 100.0, значит
`SETTINGS join_use_nulls = 1` в `cases/06_ltv_by_cohort.sql` не применяется, и
чинить нужно сам запрос, а не снапшот.

## Проблема

Интервью BI/DA middle в Авито/Яндекс/Т-банк: ~50% отбора — SQL, живущий на ClickHouse.
Портфолио покрывает SQL только на DuckDB (26 кейсов), ноль исполняемого ClickHouse-кода
и ноль кейсов оптимизации запросов (EXPLAIN/планы/индексы — 0 попаданий по grep).
Разница диалектов (ARRAY JOIN, материализованные представления, оконные отличия,
skip-indexes) не переносится 1:1 из DuckDB.

## Цель (SMART)

К 2026-10-31: 10 кейсов выполняются на реальном ClickHouse (docker), из них
1 оптимизационный кейс с документированным ускорением ≥×10 от медленной версии
запроса до оптимизированной (EXPLAIN PLAN до/после, замеры по `clickhouse-benchmark`).

## Успех = метрика

| Метрика | Target |
|---|---|
| CH-кейсы, проходящие на реальном сервере | 10/10 |
| Ускорение в оптимизационном кейсе | ≥×10, воспроизводимо benchmark-ом |
| Перенесённые паттерны из DuckDB-кейсов | ≥8 (funnel, retention, sessionization, gaps-and-islands, top-N, LTV, attribution, RFM) |
| README с интерпретацией каждого кейса | да |

## Решение

**Стек:** Python ≥3.11, uv, `clickhouse-connect` (HTTP), docker-compose
(single-node ClickHouse 24.x + данные в MergeTree), pandas для сверки результатов,
pytest.

**Структура:**

```
cases/            # 01_funnel.sql … 10_optimization.sql + expected outputs
cases/10_optimization/
  slow.sql        # наивный запрос (крестовина, без индексов)
  fast.sql        # оптимизированный (projection / skip-index / prewhere)
  explain_slow.md # EXPLAIN PLAN/AST/SYNTAX + анализ
  explain_fast.md
  benchmark.md    # clickhouse-benchmark, N прогонов, медиана/p95
scripts/
  run.py          # прогон кейсов против CH, сверка с expected
  seed.py         # генерация/загрузка данных в MergeTree
docker-compose.yml
tests/
```

**Оптимизационный кейс — сюжет:** «аналитик прислал запрос на 90 секунд, прод —
ускорить». Инструменты разора: `EXPLAIN`, prewhere vs where, ORDER BY под
MergeTree-ключ, skip-indexes (minmax/bloom_filter/set), projections,
материализованное представление, `LIMIT BY`. Каждый шаг замеряется, итог — таблица
«шаг → время → почему».

**Перенос из sql-analytics-case-study:** берём кейсы как есть, переписываем под CH
с сохранением бизнес-смысла; expected-результаты сверяются с DuckDB-эталоном.

## Out of scope

- ClickHouse Cluster / репликация / distributed tables
- dbt-clickhouse adapter (отдельная итерация)
- Real-time ingestion (Kafka)

## Milestones

| Дата | Что |
|---|---|
| неделя 1 | docker + seed + кейсы 1-3 |
| неделя 2 | кейсы 4-8 |
| неделя 3 | оптимизационный кейс + benchmark |
| неделя 4 | README + tests + публикация |

## Риски и митигации

| Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|
| Различия версий CH в docker | низкая | среднее | пин версии в compose, `clickhouse-connect` >=0.7 |
| Данные слишком малы для честного benchmark | средняя | высокое | seed ≥50M строк, p50/p95 по 100 прогонам |
| Кейс ускорения тривиален (×2) | средняя | среднее | готовим slow-запрос специально плохим: `any()` по крестовине, без индексов, sort в памяти |

## Связи

- Источник паттернов: `../sql-analytics-case-study/` (DuckDB-кейсы)
- Обоснование: `Аудит портфолио и план новых проектов 2026-09` (vault, ось B гэпы 1-2)