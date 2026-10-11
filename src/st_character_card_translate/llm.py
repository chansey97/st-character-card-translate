"""Synchronous, non-streaming structured requests without business retries."""

import json
import time

from pydantic import BaseModel


def request_json(
    client, model: str, prompt: str, request: dict,
    response_schema: type[BaseModel], delay_between_requests: float = 0.0,
) -> dict:
    if delay_between_requests:
        time.sleep(delay_between_requests)
    response = client.chat.completions.create(
        model=model,
        stream=False,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": response_schema.__name__,
                "strict": True,
                "schema": response_schema.model_json_schema(),
            },
        },
        reasoning_effort="none",
    )
    if not response.choices:
        raise ValueError("Model returned no choices")
    choice = response.choices[0]
    if choice.finish_reason != "stop":
        raise ValueError(f"Unexpected finish_reason: {choice.finish_reason}")
    if choice.message.refusal:
        raise ValueError(f"Model refused the request: {choice.message.refusal}")
    if choice.message.content is None:
        raise ValueError("Model returned no content")
    return response_schema.model_validate_json(choice.message.content).model_dump()
