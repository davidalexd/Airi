"""Tests de compatibilidad de RESPONSE_SCHEMA con salida estricta (json_schema).

El modo `strict_schema` exige (reglas OpenAI/llama.cpp): todas las propiedades
en `required` y `additionalProperties: false` en cada nivel anidado.
"""

from airi.domain.llm_output import RESPONSE_SCHEMA


def test_response_schema_requires_all_properties():
    assert set(RESPONSE_SCHEMA["required"]) == set(RESPONSE_SCHEMA["properties"])


def test_response_schema_disallows_additional_properties():
    assert RESPONSE_SCHEMA["additionalProperties"] is False


def test_response_schema_actions_items_are_strict_too():
    items = RESPONSE_SCHEMA["properties"]["actions"]["items"]
    assert items["additionalProperties"] is False
    assert set(items["required"]) == set(items["properties"])


def test_response_schema_uses_enums_for_closed_fields():
    # Campos con conjunto cerrado: la gramática los limita a esos valores.
    assert RESPONSE_SCHEMA["properties"]["gif"]["enum"]
    assert RESPONSE_SCHEMA["properties"]["date_decision"]["enum"]
    assert RESPONSE_SCHEMA["properties"]["last_chance_result"]["enum"]
