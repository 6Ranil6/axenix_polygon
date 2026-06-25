from typing import Any


def validate_polygon_data(polygon_data: Any) -> dict[str, Any]:
    if not isinstance(polygon_data, dict):
        raise ValueError("Данные передаются в неправильном формате")

    if "error" in polygon_data:
        error_text = polygon_data["error"]
        if isinstance(error_text, str) and error_text.strip():
            raise ValueError(error_text.strip())
        raise ValueError("Модель вернула ошибку без описания")

    expected_keys = {"name", "color", "vertexes"}
    extra_keys = set(polygon_data) - expected_keys
    missing_keys = expected_keys - set(polygon_data)

    if missing_keys:
        raise ValueError(f"В данных отсутствуют поля: {sorted(missing_keys)}")
    if extra_keys:
        raise ValueError(f"В данных есть лишние поля: {sorted(extra_keys)}")

    name = polygon_data["name"]
    color = polygon_data["color"]

    if not isinstance(name, str) or not name.strip():
        raise ValueError("Поле name должно быть непустой строкой")

    if not isinstance(color, str) or not color.strip():
        raise ValueError("Поле color должно быть непустой строкой")

    return {
        "name": name.strip(),
        "color": color.strip(),
        "vertexes": validate_vertexes(polygon_data["vertexes"]),
    }


def validate_vertexes(vertexes: Any) -> list[dict[str, Any]]:
    if not isinstance(vertexes, list) or not vertexes:
        raise ValueError("Поле vertexes неправильного типа или пустое")
    if len(vertexes) < 3:
        raise ValueError("Поле vertexes должно содержать минимум 3 вершины")

    validated_vertexes = []
    orders = []

    for index, vertex in enumerate(vertexes, start=1):
        prefix = f"{index} вершина"

        if not isinstance(vertex, dict):
            raise ValueError(f"{prefix} должна быть JSON-объектом")

        expected_keys = {"x", "y", "order"}
        vertex_keys = set(vertex)
        if vertex_keys != expected_keys:
            raise ValueError(f"{prefix} должна содержать только поля x, y,\
                              order")

        x = vertex["x"]
        y = vertex["y"]
        order = vertex["order"]

        if not isinstance(x, (int, float)) or isinstance(x, bool):
            raise ValueError(f"Поле x у вершины {index} должно быть числом")
        if not isinstance(y, (int, float)) or isinstance(y, bool):
            raise ValueError(f"Поле y у вершины {index} должно быть числом")
        if not isinstance(order, int) or isinstance(order, bool):
            raise ValueError(f"Поле order у вершины {index} должно быть\
                              целым числом")

        orders.append(order)
        validated_vertexes.append({
            "x": x,
            "y": y,
            "order": order,
        })

    expected_orders = list(range(1, len(validated_vertexes) + 1))
    if orders != expected_orders:
        raise ValueError(f"Порядок order должен быть {expected_orders}")

    return validated_vertexes


def normalize_vertexes_for_db(vertexes: Any) -> list[dict[str, Any]]:
    validated_vertexes = validate_vertexes(vertexes)

    return [
        {
            "vertexorder": vertex["order"],
            "x": float(vertex["x"]),
            "y": float(vertex["y"]),
        }
        for vertex in validated_vertexes
    ]
