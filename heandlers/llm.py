import os
import json
import re
from typing import Any
from peft import PeftConfig, PeftModel
import aiofiles
import torch
from dotenv import load_dotenv
from transformers import AutoModelForCausalLM
from transformers import AutoTokenizer, BitsAndBytesConfig

from heandlers.polygon_validation import validate_polygon_data


def create_tokenizer_model(adapter_path: str | None = None):
    load_dotenv('data/.env')
    qconfig = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    adapter_path = adapter_path

    if adapter_path:
        peft_config = PeftConfig.from_pretrained(adapter_path)
        base_model_name = peft_config.base_model_name_or_path

        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            device_map='auto',
            quantization_config=qconfig,
        )
        model = PeftModel.from_pretrained(base_model, adapter_path)
        tokenizer = AutoTokenizer.from_pretrained(adapter_path)
    else:
        MODEL_NAME = os.getenv('MODEL_NAME')
        if not MODEL_NAME:
            raise ValueError("В data/.env не задан MODEL_NAME")

        model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            device_map='auto',
            quantization_config=qconfig,
        )
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    model.eval()
    return tokenizer, model


async def fetch_system_prompt(file_path) -> str:
    try:
        async with aiofiles.open(file_path) as f:
            system_prompt = await f.read()

        return system_prompt
    except FileNotFoundError:
        return "Файл не найден"


def parse_model_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        data, end_index = json.JSONDecoder().raw_decode(text)
    except json.JSONDecodeError as inner_exc:
        raise ValueError(
            f"Модель вернула невалидный JSON: {inner_exc}"
        ) from inner_exc

    if not isinstance(data, dict):
        raise ValueError("Модель должна вернуть валидный JSON-объект")

    return data


def build_full_answer(prefill: str, generated_text: str) -> str:
    stripped_text = generated_text.lstrip()
    if stripped_text.startswith("{") or stripped_text.startswith("```"):
        return generated_text
    return prefill + generated_text


def validate_model_json(data: dict[str, Any]) -> dict[str, Any]:
    if "error" in data:
        if set(data) != {"error"}:
            raise ValueError("JSON с полем error не должен содержать\
                              другие поля")

        error_text = data["error"]
        if not isinstance(error_text, str) or not error_text.strip():
            raise ValueError("Поле error должно быть непустой строкой")

        technical_markers = (
            "JSON",
            "Модель",
            "Expecting",
            "line ",
            "column ",
            "Ошибка проверки",
        )
        if any(marker in error_text for marker in technical_markers):
            raise ValueError(
                "Модель скопировала техническую ошибку вместо результата"
            )

        return {"error": error_text.strip()}

    return validate_polygon_data(data)


async def create_json_from_prompt(prompt: str,
                                  model: AutoModelForCausalLM,
                                  tokenizer: AutoTokenizer,
                                  retries: int = 1) -> dict[str, Any]:
    SYSTEM_PROMPT = await fetch_system_prompt('data/system_prompt.txt')

    prefill = "{\n  "
    message = [{'role': 'system', 'content': SYSTEM_PROMPT},
               {'role': 'user', 'content': prompt},
               {'role': 'assistant', 'content': prefill}]
    last_error = None
    generated_text = ""

    for attempt in range(retries + 1):
        text = tokenizer.apply_chat_template(message,
                                             tokenize=False,
                                             continue_final_message=True)

        model_device = next(model.parameters()).device
        inputs = tokenizer(text, return_tensors='pt').to(model_device)

        with torch.inference_mode():
            if tokenizer.pad_token_id is not None:
                pad_token = tokenizer.pad_token_id
            else:
                pad_token = tokenizer.eos_token_id
            output_ids = model.generate(**inputs,
                                        max_new_tokens=512,
                                        do_sample=False,
                                        pad_token_id=pad_token)

        generated_ids = output_ids[0][inputs['input_ids'].shape[-1]:]
        generated_text = tokenizer.decode(generated_ids,
                                          skip_special_tokens=True)
        full_answer = build_full_answer(prefill, generated_text)

        try:
            data = parse_model_json(full_answer)
            return validate_model_json(data)

        except ValueError as exc:
            last_error = exc
            if attempt == retries:
                break
            message = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Исправь предыдущий ответ и верни только валидный JSON"
                        " нужного формата.\n"
                        "Не используй Markdown и блоки ```json.\n"
                        f"Исходный запрос пользователя:\n{prompt}\n"
                        f"Ошибка проверки: {str(last_error)}\n"
                        f"Предыдущий ответ модели:\n{full_answer}"
                    ),
                },
                {'role': 'assistant', 'content': prefill}
            ]

    raise ValueError(
        "Не получилось получить корректный JSON от модели. "
        f"Последняя ошибка: {last_error}. "
        f"Последний ответ модели: {prefill + generated_text}"
    )
