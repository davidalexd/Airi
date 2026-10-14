"""Tests de caracterización del parseo de la salida del modelo.

Congelan `clean_reply`, `extract_json_object`, `extract_reply_field`,
`parse_actions`, `parse_scene_list` y casos límite de `parse_model_output`.
"""

import bot

# ---------------------------------------------------------------------------
# clean_reply
# ---------------------------------------------------------------------------


def test_clean_reply_non_string_returns_empty():
    assert bot.clean_reply(None) == ""
    assert bot.clean_reply(42) == ""


def test_clean_reply_strips_unicode_emoji():
    assert bot.clean_reply("hola 😄 mundo") == "hola mundo"
    assert bot.clean_reply("nos vemos 🎉") == "nos vemos"


def test_clean_reply_strips_custom_discord_emoji():
    assert bot.clean_reply("mira <a:sparkle:123456> algo") == "mira algo"
    assert bot.clean_reply("mira <:rojo:99> algo") == "mira algo"


def test_clean_reply_strips_discord_asset_links():
    text = "https://discordapp.com/assets/abc123.png hola"
    assert bot.clean_reply(text) == "hola"
    markdown = "[logo](https://discord.com/assets/logo.png) hola"
    assert bot.clean_reply(markdown) == "hola"


def test_clean_reply_collapses_whitespace_and_newlines():
    assert bot.clean_reply("hola    mundo") == "hola mundo"
    assert bot.clean_reply("a\n\n\n\n\nb") == "a\n\nb"
    assert bot.clean_reply("  con espacios  ") == "con espacios"


# ---------------------------------------------------------------------------
# extract_json_object
# ---------------------------------------------------------------------------


def test_extract_json_object_plain_dict():
    assert bot.extract_json_object('{"a": 1}') == {"a": 1}


def test_extract_json_object_fenced():
    raw = '```json\n{"a": 1}\n```'
    assert bot.extract_json_object(raw) == {"a": 1}


def test_extract_json_object_with_leading_text():
    raw = 'Aquí va: {"reply": "hola"} espero que sirva'
    assert bot.extract_json_object(raw) == {"reply": "hola"}


def test_extract_json_object_non_dict_is_none():
    assert bot.extract_json_object("[1, 2]") is None
    assert bot.extract_json_object('"texto"') is None


def test_extract_json_object_non_string_is_none():
    assert bot.extract_json_object(None) is None
    assert bot.extract_json_object({"a": 1}) is None


def test_extract_json_object_broken_is_none():
    assert bot.extract_json_object("{reply: sin comillas") is None


# ---------------------------------------------------------------------------
# extract_reply_field
# ---------------------------------------------------------------------------


def test_extract_reply_field_recovers_from_broken_json():
    raw = 'algo raro {"reply": "  hola  ", "gif": '
    assert bot.extract_reply_field(raw) == "hola"


def test_extract_reply_field_missing_returns_none():
    assert bot.extract_reply_field('{"gif": "happy"}') is None
    assert bot.extract_reply_field("sin json") is None
    assert bot.extract_reply_field(None) is None


def test_extract_reply_field_empty_value_returns_none():
    assert bot.extract_reply_field('{"reply": "   "}') is None


def test_extract_reply_field_handles_escapes():
    raw = '{"reply": "línea\\ncon salto"}'
    assert bot.extract_reply_field(raw) == "línea\ncon salto"


# ---------------------------------------------------------------------------
# parse_actions / parse_scene_list
# ---------------------------------------------------------------------------


def test_parse_actions_non_list_is_empty():
    assert bot.parse_actions(None) == []
    assert bot.parse_actions("nope") == []


def test_parse_actions_skips_invalid_entries():
    raw = [
        None,
        "texto",
        {"action": ""},
        {"label": "sin action"},
        {"action": "abrazarla", "label": "  Abra  zarla  "},
    ]
    actions = bot.parse_actions(raw)
    assert len(actions) == 1
    assert actions[0]["action"] == "abrazarla"
    assert actions[0]["label"] == "Abra zarla"


def test_parse_actions_label_defaults_to_action():
    actions = bot.parse_actions([{"action": "decir hola"}])
    assert actions[0]["label"] == "decir hola"


def test_parse_actions_limits_count_and_label():
    raw = [{"action": f"accion {i}", "label": "x" * 200} for i in range(10)]
    actions = bot.parse_actions(raw)
    assert len(actions) == bot.DATE_ACTION_MAX
    assert len(actions[0]["label"]) == bot.DATE_ACTION_LABEL_MAX


def test_parse_scene_list_non_list_is_empty():
    assert bot.parse_scene_list(None) == []
    assert bot.parse_scene_list({"a": 1}) == []


def test_parse_scene_list_dedupes_truncates_and_limits():
    raw = ["un paseo", "un paseo", 42, "  cena   romántica  ", "x" * 300, "cinco", "seis"]
    scenes = bot.parse_scene_list(raw)
    assert scenes[0] == "un paseo"
    assert scenes[1] == "cena romántica"
    assert len(scenes) == bot.DATE_SCENE_MAX
    assert all(len(s) <= bot.DATE_ACTION_LABEL_MAX for s in scenes)


# ---------------------------------------------------------------------------
# parse_model_output — casos límite
# ---------------------------------------------------------------------------


def test_parse_empty_is_default():
    out = bot.parse_model_output("")
    assert out.reply is None
    assert out.gif == "none"
    assert out.affinity_delta == 0
    assert out.actions == []


def test_parse_invalid_gif_becomes_none():
    out = bot.parse_model_output('{"reply": "hola", "gif": "naruto"}')
    assert out.gif == "none"


def test_parse_float_delta_truncates():
    out = bot.parse_model_output(
        '{"reply": "hola", "affinity_delta": 3.9, "affinity_event": "risas"}'
    )
    assert out.affinity_delta == 3


def test_parse_bool_delta_is_zero():
    out = bot.parse_model_output(
        '{"reply": "hola", "affinity_delta": true, "affinity_event": "risas"}'
    )
    assert out.affinity_delta == 0


def test_parse_delta_clamped_to_max():
    out = bot.parse_model_output(
        '{"reply": "hola", "affinity_delta": 99, "affinity_event": "risas"}'
    )
    assert out.affinity_delta == bot.game.AFFINITY_DELTA_MAX


def test_parse_delta_max_param_overrides_default():
    out = bot.parse_model_output(
        '{"reply": "hola", "affinity_delta": 99, "affinity_event": "risas"}',
        delta_max=8,
    )
    assert out.affinity_delta == 8


def test_parse_invalid_date_decision_becomes_continue():
    out = bot.parse_model_output('{"reply": "hola", "date_decision": "romper"}')
    assert out.date_decision == "continue"


def test_parse_invalid_last_chance_result_becomes_none():
    out = bot.parse_model_output('{"reply": "hola", "last_chance_result": "quizas"}')
    assert out.last_chance_result == "none"


def test_parse_recovery_from_raw_text_reply():
    out = bot.parse_model_output("esto no es json pero tiene reply: hola")
    assert out.reply == "esto no es json pero tiene reply: hola"
    assert out.gif == "none"
    assert out.affinity_delta == 0


def test_parse_broken_json_recovers_reply_field():
    out = bot.parse_model_output('{"reply": "hola recuperada", "gif": ')
    assert out.reply == "hola recuperada"
    assert out.gif == "none"


def test_parse_whitespace_only_reply_becomes_default():
    out = bot.parse_model_output('{"reply": "   "}')
    assert out.reply is None


def test_parse_memory_and_diary_truncated_to_400():
    out = bot.parse_model_output(
        '{"reply": "hola", "memory": "%s", "diary": "%s"}' % ("m" * 500, "d" * 500)
    )
    assert len(out.memory) == 400
    assert len(out.diary) == 400

