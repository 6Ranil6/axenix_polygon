# Axenix task3

Проект генерирует JSON с многоугольником через LLM, проверяет данные и сохраняет их в PostgreSQL.

В `heandlers` лежат обычные функции для LLM, валидации и работы с БД.
`EXAMPLE.ipynb` - пример использования проекта.

## data

- `data/.env.docker.example` - пример переменных для PostgreSQL, который запускается через Docker Compose.
- `data/colors.json` - словарь русских цветов и английских CSS-названий для отрисовки.
- `data/system_prompt.txt` - системный промпт с правилами JSON-ответа и примерами.

## heandlers/llm.py

- `create_tokenizer_model` - загружает 4-bit базовую модель и подключает LoRA-адаптер, если он есть.
- `fetch_system_prompt` - асинхронно читает системный промпт из файла.
- `parse_model_json` - достает первый валидный JSON-объект из ответа модели.
- `build_full_answer` - добавляет prefill к ответу, если модель продолжила JSON без начала.
- `validate_model_json` - проверяет JSON модели или возвращает корректный error-ответ.
- `create_json_from_prompt` - отправляет prompt в модель и возвращает проверенный polygon JSON.

## heandlers/pg_db.py

- `_get_env_value` - берет первое найденное значение из списка переменных окружения.
- `init_pool` - создает пул подключений asyncpg по переданным параметрам.
- `init_pool_from_env` - создает пул подключений asyncpg из переменных окружения.
- `close_pool` - закрывает пул подключений, если он был создан.
- `fetch_vertexes_polygons` - получает вершины многоугольника по `polygonid`.
- `fetch_polygon` - ищет многоугольники по имени и возвращает цвет с вершинами.
- `insert_polygon` - проверяет данные и вставляет цвет, многоугольник и вершины в БД.

## heandlers/polygon_validation.py

- `validate_polygon_data` - проверяет верхний уровень polygon JSON и чистит строки.
- `validate_vertexes` - проверяет вершины, координаты и последовательность `order`.
- `normalize_vertexes_for_db` - переводит вершины в формат таблицы `vertexpolygon`.

## pg_db

- `pg_db/init.sql` - создает таблицы `color`, `polygon`, `vertexpolygon` и индексы.
- `pg_db/add_data.sql` - добавляет базовые цвета без дублей и падений при повторном запуске.

## Для старта
    Нужно добавить переменные окружения в `data/.env` по примеру из `data/.env.docker.example`
    Чтобы использовать LoRA-адаптер, скачайте zip архив с [яндекс диска](https://disk.yandex.ru/d/TnQQsI7rJ8d3Zw) и распакуйте его в корень проекта. 
## Docker PostgreSQL

Запуск БД:

```bash
docker compose up -d
```

Остановка без удаления данных:

```bash
docker compose down
```

Данные PostgreSQL лежат в Docker volume `polygon_pg_data`, поэтому не пропадают после падения контейнера.

```env
Пример подключения:

```python
from heandlers.pg_db import init_pool_from_env, insert_polygon

pool = await init_pool_from_env()
await insert_polygon(pool, polygon_data)
```

## LoRA-адаптер
`create_tokenizer_model()` подключит ее автоматически.

Если вы хотите дообучить свою модель, то можно явно указать другой путь:

```python
tokenizer, model = create_tokenizer_model("models/polygon-json-lora")
```

Или задать путь через `.env`:

```env
LORA_ADAPTER_PATH=polygon-json-lora
```
