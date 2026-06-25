import os
from typing import Any

import asyncpg
from dotenv import load_dotenv

from heandlers.polygon_validation import (
    normalize_vertexes_for_db,
    validate_polygon_data,
)


def _get_env_value(*names: str, default: str | None = None) -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value

    if default is not None:
        return default

    raise ValueError(f"Не найдена переменная окружения: {', '.join(names)}")


async def init_pool(
    user: str,
    password: str,
    host: str,
    port: str | int,
    database: str,
    MIN_SIZE: int = 1,
    MAX_SIZE: int = 10,
) -> asyncpg.Pool:

    pool = await asyncpg.create_pool(user=user,
                                     password=password,
                                     host=host,
                                     port=int(port),
                                     database=database,
                                     min_size=MIN_SIZE,
                                     max_size=MAX_SIZE)
    return pool


async def init_pool_from_env(
    env_path: str = "data/.env",
    MIN_SIZE: int = 1,
    MAX_SIZE: int = 10,
) -> asyncpg.Pool:
    load_dotenv(env_path, override=True)

    return await init_pool(
        user=_get_env_value("DB_USER", "POSTGRES_USER", "USER"),
        password=_get_env_value("DB_PASSWORD", "POSTGRES_PASSWORD", "PASSWORD"),
        host=_get_env_value("DB_HOST", "HOST", default="localhost"),
        port=_get_env_value("DB_PORT", "PORT", default="5433"),
        database=_get_env_value("DB_NAME", "POSTGRES_DB", "DATABASE"),
        MIN_SIZE=MIN_SIZE,
        MAX_SIZE=MAX_SIZE,
    )


async def close_pool(pool: asyncpg.Pool | None) -> None:
    if pool:
        await pool.close()


async def fetch_vertexes_polygons(pool: asyncpg.Pool | None,
                                  polygon_id: int,
                                  timeout: int = 10):
    if not pool:
        raise ValueError("Пул подключений к базе данных не создан")

    async with pool.acquire(timeout=timeout) as conn:
        q = """
        SELECT
        vertexorder,
        x,
        y
        FROM vertexpolygon
        WHERE polygonid = $1
        ORDER BY vertexorder
        """
        vertexes = await conn.fetch(q, polygon_id)
    return vertexes


async def fetch_polygon(pool: asyncpg.Pool | None,
                        name: str,
                        timeout: int = 10):
    if not pool:
        raise ValueError("Пул подключений к базе данных не создан")

    async with pool.acquire(timeout=timeout) as conn:
        q = """
        SELECT
            polygonid,
            p.name as polygon_name,
            c.name as color_name
        FROM Polygon as p
        JOIN color as c ON c.colorid = p.colorid
        WHERE p.name = $1
        """

        polygons = await conn.fetch(q, name)

    responses = []

    for polygon in polygons:
        polygon_id = polygon["polygonid"]

        vertexes = await fetch_vertexes_polygons(pool, polygon_id)

        responses.append({
            "polygon_id": polygon_id,
            "polygon_name": polygon["polygon_name"],
            "color_name": polygon["color_name"],
            "vertexes": [dict(vertex) for vertex in vertexes],
        })

    return responses


async def insert_polygon(pool: asyncpg.Pool | None,
                         polygon_data: dict[str, Any],
                         timeout: int = 10):
    if not pool:
        raise ValueError("Пул подключений к базе данных не создан")

    polygon_data = validate_polygon_data(polygon_data)
    name = polygon_data["name"]
    color = polygon_data["color"]
    vertexes = normalize_vertexes_for_db(polygon_data["vertexes"])

    async with pool.acquire(timeout=timeout) as conn:
        async with conn.transaction():
            color_id = await conn.fetchval(
                """
                SELECT colorid
                FROM color
                WHERE lower(name) = lower($1)
                """,
                color,
            )

            if color_id is None:
                color_id = await conn.fetchval(
                    """
                    INSERT INTO color(name)
                    VALUES ($1)
                    RETURNING colorid
                    """,
                    color,
                )

            polygon_id = await conn.fetchval(
                """
                INSERT INTO polygon(name, colorid)
                VALUES ($1, $2)
                RETURNING polygonid
                """,
                name,
                color_id,
            )

            await conn.executemany(
                """
                INSERT INTO vertexpolygon(polygonid, vertexorder, x, y)
                VALUES ($1, $2, $3, $4)
                """,
                [
                    (
                        polygon_id,
                        vertex["vertexorder"],
                        vertex["x"],
                        vertex["y"],
                    )
                    for vertex in vertexes
                ],
            )

    return {
        "polygon_id": polygon_id,
        "polygon_name": name,
        "color_name": color,
        "vertexes": vertexes,
    }
