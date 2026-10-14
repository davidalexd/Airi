"""Tests de integración de la capa bot.py (sin red ni Discord real)."""

import asyncio
import time

import bot
import game


class FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content)


def test_confession_text_mentions_name():
    text = bot.confession_text("Ana")
    assert "Ana" in text
    assert "novios" in text.lower()


def test_gift_reaction_tone():
    assert "Gracias" in bot.gift_reaction("flores", 3)
    assert "detalle" in bot.gift_reaction("piedra", -2)
    assert "Gracias" in bot.gift_reaction("cafe", 0)


def test_win_status_line_soltera():
    bot.world_data = game.default_world()
    assert "soltera" in bot.win_status_line().lower()


def test_help_embed_mentions_commands():
    embed = bot.build_help_embed()
    desc = embed.description
    for token in ("!afinidad", "!relacion", "!ranking", "!cita", "!regalo", "!memorias", "!diario"):
        assert token in desc
    assert "Novios" in desc
    assert "100" in desc


def test_settle_relationship_crowns_winner(monkeypatch):
    monkeypatch.setattr(bot, "save_world", lambda: None)
    monkeypatch.setattr(bot, "save_affinity", lambda: None)
    monkeypatch.setattr(bot, "save_diary", lambda: None)
    bot.diary_data = []
    bot.world_data = game.default_world()
    bot.affinity_data = {
        "111": game.default_entry(),
        "222": game.default_entry(),
    }
    bot.users_data = {"222": {"name": "Beto"}}
    bot.affinity_data["222"]["points"] = game.CONFESS_THRESHOLD

    channel = FakeChannel()
    winner = asyncio.run(bot.settle_relationship(channel, now=1000.0))

    assert winner == "222"
    assert bot.world_data["winner_id"] == "222"
    assert any("Beto" in (m or "") for m in channel.sent)


def test_settle_relationship_is_idempotent(monkeypatch):
    monkeypatch.setattr(bot, "save_world", lambda: None)
    monkeypatch.setattr(bot, "save_affinity", lambda: None)
    monkeypatch.setattr(bot, "save_diary", lambda: None)
    bot.diary_data = []
    bot.world_data = game.default_world()
    bot.world_data["winner_id"] = "222"
    bot.affinity_data = {"111": {"points": 90}, "222": {"points": 100}}
    bot.users_data = {}

    channel = FakeChannel()
    winner = asyncio.run(bot.settle_relationship(channel, now=1000.0))

    assert winner is None
    assert channel.sent == []
    # El perdedor queda capado por el bloqueo de ganador.
    assert bot.affinity_data["111"]["points"] == game.FRIENDZONE_CAP


class FakeUser:
    def __init__(self, user_id, name):
        self.id = user_id
        self.display_name = name


def test_schema_includes_optional_diary():
    props = bot.RESPONSE_SCHEMA["properties"]
    assert "diary" in props
    # Opcional: no se exige al modelo para no encarecer la salida.
    assert "diary" not in bot.RESPONSE_SCHEMA["required"]


def test_schema_requires_affinity_event():
    # El candado necesita que el modelo declare siempre el motivo (aunque sea "none").
    assert "affinity_event" in bot.RESPONSE_SCHEMA["properties"]
    assert "affinity_event" in bot.RESPONSE_SCHEMA["required"]


def test_parse_model_output_returns_diary():
    raw = (
        '{"reply":"hola","gif":"none","memory":"none",'
        '"diary":"Me sentí feliz.","affinity_delta":2,'
        '"affinity_event":"me hizo un detalle sincero"}'
    )
    out = bot.parse_model_output(raw)
    assert out.reply == "hola"
    assert out.gif == "none"
    assert out.memory == "none"
    assert out.diary == "Me sentí feliz."
    assert out.affinity_delta == 2
    # Sin campos de cita, los valores por defecto son neutros.
    assert out.date_decision == "continue"
    assert out.date_reason == "none"
    assert out.last_chance_result == "none"
    assert out.actions == []


def test_parse_model_output_gates_affinity_without_event():
    # Delta positivo pero sin motivo -> se ignora.
    raw = '{"reply":"hola","gif":"none","memory":"none","affinity_delta":3}'
    out = bot.parse_model_output(raw)
    assert out.affinity_delta == 0


def test_parse_model_output_gates_affinity_event_none():
    raw = (
        '{"reply":"hola","gif":"none","memory":"none",'
        '"affinity_delta":-4,"affinity_event":"none"}'
    )
    out = bot.parse_model_output(raw)
    assert out.affinity_delta == 0


def test_parse_model_output_applies_affinity_with_event():
    raw = (
        '{"reply":"hola","gif":"none","memory":"none",'
        '"affinity_delta":4,"affinity_event":"me apoyó en un mal día"}'
    )
    out = bot.parse_model_output(raw)
    assert out.affinity_delta == 4


def test_parse_model_output_reads_date_fields():
    raw = (
        '{"reply":"hola","gif":"none","memory":"none","diary":"none",'
        '"affinity_delta":-3,"affinity_event":"me incomodó",'
        '"date_decision":"crisis","date_reason":"se pasó de la raya",'
        '"last_chance_result":"none"}'
    )
    out = bot.parse_model_output(raw)
    assert out.date_decision == "crisis"
    assert out.date_reason == "se pasó de la raya"
    assert out.last_chance_result == "none"


def test_parse_model_output_normalizes_bad_date_fields():
    raw = (
        '{"reply":"hola","gif":"none","memory":"none","affinity_delta":0,'
        '"date_decision":"banana","date_reason":"","last_chance_result":"quizá"}'
    )
    out = bot.parse_model_output(raw)
    assert out.date_decision == "continue"
    assert out.date_reason == "none"
    assert out.last_chance_result == "none"


def test_parse_model_output_diary_defaults_to_none():
    raw = '{"reply":"hola","gif":"none","memory":"none","affinity_delta":0}'
    out = bot.parse_model_output(raw)
    assert out.diary == "none"


def test_parse_model_output_parses_actions_and_clamps():
    raw = (
        '{"reply":"bien","gif":"none","memory":"none","affinity_delta":0,'
        '"actions":[{"label":"Darle un abrazo","action":"Le doy un abrazo cálido"},'
        '{"label":"Invitarla a bailar","action":"La invito a bailar"}]}'
    )
    out = bot.parse_model_output(raw)
    assert out.actions == [
        {"label": "Darle un abrazo", "action": "Le doy un abrazo cálido"},
        {"label": "Invitarla a bailar", "action": "La invito a bailar"},
    ]


def test_parse_model_output_clamps_action_count_and_label():
    raw = (
        '{"reply":"bien","gif":"none","memory":"none","affinity_delta":0,'
        '"actions":['
        '{"label":"a","action":"a1"},'
        '{"label":"b","action":"b1"},'
        '{"label":"c","action":"c1"},'
        '{"label":"d","action":"d1"},'
        '{"label":"e","action":"e1"}'
        ']}'
    )
    out = bot.parse_model_output(raw)
    assert len(out.actions) == bot.DATE_ACTION_MAX
    # label truncado si muy largo
    long_label = "x" * 100
    raw_long = (
        '{"reply":"bien","gif":"none","memory":"none","affinity_delta":0,'
        f'"actions":[{{"label":"{long_label}","action":"hago algo"}}]'
        '}'
    )
    out_long = bot.parse_model_output(raw_long)
    assert len(out_long.actions) == 1
    assert len(out_long.actions[0]["label"]) == bot.DATE_ACTION_LABEL_MAX


def test_parse_model_output_actions_skip_invalid_entries():
    raw = (
        '{"reply":"bien","gif":"none","memory":"none","affinity_delta":0,'
        '"actions":[{"label":"ok","action":""}, {"label":5,"action":""}]}'
    )
    out = bot.parse_model_output(raw)
    assert out.actions == []


def test_propose_scenes_fallback(monkeypatch):
    async def fake_request(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(bot, "request_llama", fake_request)

    async def run():
        import aiohttp

        async with aiohttp.ClientSession() as session:
            scenes = await bot.propose_scenes(session, user=None)
            assert scenes

    import asyncio

    asyncio.run(run())


def test_judge_gift_uses_model_decision(monkeypatch):
    async def fake_request_llama(session, payload):
        return {
            "choices": [{
                "message": {
                    "content": (
                        '{"reply":"Gracias, me encanta","affinity_delta":3,'
                        '"affinity_event":"me ha traído mis flores favoritas"}'
                    )
                }
            }]
        }

    monkeypatch.setattr(bot, "request_llama", fake_request_llama)
    bot.world_data = game.default_world()
    bot.affinity_data = {"1": game.default_entry()}
    bot.users_data = {"1": {"name": "Ana"}}

    reply, delta, event = asyncio.run(
        bot.judge_gift(None, "rosas", FakeUser(1, "Ana"), [])
    )
    assert reply == "Gracias, me encanta"
    assert delta == 3
    assert "favoritas" in event


def test_judge_gift_gates_without_event(monkeypatch):
    async def fake_request_llama(session, payload):
        return {
            "choices": [{
                "message": {
                    "content": (
                        '{"reply":"Gracias","affinity_delta":2,'
                        '"affinity_event":"none"}'
                    )
                }
            }]
        }

    monkeypatch.setattr(bot, "request_llama", fake_request_llama)
    bot.world_data = game.default_world()
    bot.affinity_data = {"1": game.default_entry()}
    bot.users_data = {"1": {"name": "Ana"}}

    _reply, delta, _event = asyncio.run(
        bot.judge_gift(None, "cafe", FakeUser(1, "Ana"), [])
    )
    assert delta == 0


def test_judge_gift_returns_none_on_failure(monkeypatch):
    async def fake_request_llama(session, payload):
        raise RuntimeError("boom")

    monkeypatch.setattr(bot, "request_llama", fake_request_llama)
    bot.world_data = game.default_world()
    bot.affinity_data = {"1": game.default_entry()}
    bot.users_data = {"1": {"name": "Ana"}}

    assert asyncio.run(bot.judge_gift(None, "cafe", FakeUser(1, "Ana"), [])) is None


def test_log_diary_event_appends(monkeypatch):
    monkeypatch.setattr(bot, "save_diary", lambda: None)
    bot.diary_data = []
    bot.world_data = game.default_world()
    bot.users_data = {}
    assert bot.log_diary_event("meet", "123", "Hola") is True
    assert len(bot.diary_data) == 1
    assert bot.diary_data[0]["kind"] == "meet"
    assert bot.diary_data[0]["text"] == "Hola"


def test_add_diary_reflection_dedup(monkeypatch):
    monkeypatch.setattr(bot, "save_diary", lambda: None)
    bot.diary_data = []
    bot.world_data = game.default_world()
    bot.users_data = {"123": {"name": "Ana"}}
    assert bot.add_diary_reflection("123", "Me gustó.", now=1000.0) is True
    assert bot.add_diary_reflection("123", "Me gustó.", now=1001.0) is False


def test_diary_prompt_section_lists_entries():
    bot.diary_data = [
        game.new_diary_entry("gift", "111", "Ana", "Ana me regaló flores.", 100.0)
    ]
    section = bot.diary_prompt_section(FakeUser(111, "Ana"))
    assert "me regaló flores" in section


def test_known_users_prompt_includes_impression():
    bot.world_data = game.default_world()
    bot.users_data = {
        "222": {"name": "Beto", "last_seen": 1.0, "interactions": 3},
    }
    bot.diary_data = [
        game.new_diary_entry("reflection", "222", "Beto", "Beto me hizo reír.", 100.0)
    ]
    section = bot.known_users_prompt_section(FakeUser(111, "Ana"))
    assert "Beto" in section
    assert "me hizo reír" in section


def test_known_users_monogamy_after_winner():
    bot.world_data = game.default_world()
    bot.world_data["winner_id"] = "222"
    bot.users_data = {
        "222": {"name": "Beto", "last_seen": 2.0, "interactions": 3},
        "333": {"name": "Caro", "last_seen": 3.0, "interactions": 9},
    }
    bot.diary_data = []
    section = bot.known_users_prompt_section(FakeUser(111, "Ana"))
    assert "Beto" in section
    assert "Caro" not in section


def test_settle_relationship_logs_confession_diary(monkeypatch):
    monkeypatch.setattr(bot, "save_world", lambda: None)
    monkeypatch.setattr(bot, "save_affinity", lambda: None)
    monkeypatch.setattr(bot, "save_diary", lambda: None)
    bot.world_data = game.default_world()
    bot.affinity_data = {"222": game.default_entry()}
    bot.affinity_data["222"]["points"] = game.CONFESS_THRESHOLD
    bot.users_data = {"222": {"name": "Beto"}}
    bot.diary_data = []

    channel = FakeChannel()
    winner = asyncio.run(bot.settle_relationship(channel, now=1000.0))

    assert winner == "222"
    assert any(e.get("kind") == "confession" for e in bot.diary_data)


# ============================================================
# CITAS: process_date_turn / _finish_date
# ============================================================


def _date_test_setup(monkeypatch, affinity_start=40):
    """Prepara bot para probar la cita sin tocar disco ni red."""
    applied = []
    diary = []
    saved = {"n": 0}

    monkeypatch.setattr(
        bot, "apply_affinity_change",
        lambda uid, delta, now=None, delta_max=None: applied.append((str(uid), delta)),
    )
    monkeypatch.setattr(bot, "save_dates", lambda: saved.__setitem__("n", saved["n"] + 1))
    monkeypatch.setattr(bot, "log_diary_event", lambda kind, user, text: diary.append((kind, text)))

    bot.world_data = game.default_world()
    bot.users_data = {"1": {"name": "Ana"}}
    bot.diary_data = []
    bot.active_dates = {}
    session = game.new_date_session("un paseo por el parque", affinity_start, now=1000.0)
    bot.active_dates["1"] = session
    return session, applied, diary, saved


def test_process_date_turn_continue(monkeypatch):
    session, applied, diary, saved = _date_test_setup(monkeypatch)
    channel = FakeChannel()
    event = asyncio.run(
        bot.process_date_turn(
            channel, FakeUser(1, "Ana"), session,
            text="hola", delta=2, points=42,
            date_decision="continue", date_reason="none",
            last_chance_result="none", now=1001.0,
        )
    )
    assert event == "continue"
    assert channel.sent == []
    assert saved["n"] >= 1


def test_process_date_turn_crisis(monkeypatch):
    session, applied, diary, saved = _date_test_setup(monkeypatch)
    session["turns"] = game.DATE_CRISIS_MIN_TURNS
    channel = FakeChannel()
    event = asyncio.run(
        bot.process_date_turn(
            channel, FakeUser(1, "Ana"), session,
            text="...", delta=-3, points=35,
            date_decision="crisis", date_reason="se pasó de la raya",
            last_chance_result="none", now=1001.0,
        )
    )
    assert event == "crisis"
    assert session["state"] == "last_chance"
    assert any("última" in (m or "").lower() or "razón" in (m or "").lower() for m in channel.sent)


def test_process_date_turn_ending_logs_and_closes(monkeypatch):
    session, applied, diary, saved = _date_test_setup(monkeypatch)
    channel = FakeChannel()
    event = asyncio.run(
        bot.process_date_turn(
            channel, FakeUser(1, "Ana"), session,
            text="adiós", delta=1, points=41,
            date_decision="end", date_reason="todo dicho",
            last_chance_result="none", now=1001.0,
        )
    )
    assert event == "ending"
    assert "1" not in bot.active_dates
    assert any(kind == "date" for kind, _ in diary)
    assert any("fin" in (m or "").lower() for m in channel.sent)


def test_process_date_turn_recovered_applies_recovery(monkeypatch):
    session, applied, diary, saved = _date_test_setup(monkeypatch, affinity_start=40)
    session["turns"] = game.DATE_CRISIS_MIN_TURNS
    # Entramos en crisis con la afinidad en 34.
    asyncio.run(
        bot.process_date_turn(
            FakeChannel(), FakeUser(1, "Ana"), session,
            text="...", delta=-6, points=34,
            date_decision="crisis", date_reason="mal", last_chance_result="none",
            now=1000.0,
        )
    )
    channel = FakeChannel()
    event = asyncio.run(
        bot.process_date_turn(
            channel, FakeUser(1, "Ana"), session,
            text="lo siento de verdad", delta=2, points=36,
            date_decision="continue", date_reason="none",
            last_chance_result="success", now=1001.0,
        )
    )
    assert event == "recovered"
    # Recovery = min(12, 40-36=4) = 4.
    assert ("1", 4) in applied
    assert any("date" == kind for kind, _ in diary)


def test_process_date_turn_failed_last_chance(monkeypatch):
    session, applied, diary, saved = _date_test_setup(monkeypatch)
    session["turns"] = game.DATE_CRISIS_MIN_TURNS
    session["state"] = "last_chance"
    session["last_chance_used"] = True
    channel = FakeChannel()
    event = asyncio.run(
        bot.process_date_turn(
            channel, FakeUser(1, "Ana"), session,
            text="da igual", delta=-1, points=30,
            date_decision="continue", date_reason="none",
            last_chance_result="fail", now=1001.0,
        )
    )
    assert event == "failed_last_chance"
    assert "1" not in bot.active_dates
    assert any(kind == "date" for kind, _ in diary)


def test_finish_date_removes_and_saves(monkeypatch):
    monkeypatch.setattr(bot, "save_dates", lambda: None)
    diary = []
    monkeypatch.setattr(bot, "log_diary_event", lambda kind, user, text: diary.append((kind, text)))
    bot.world_data = game.default_world()
    bot.users_data = {"1": {"name": "Ana"}}
    bot.diary_data = []
    bot.active_dates = {}
    session = game.new_date_session("la playa", 40, now=0.0)
    bot.active_dates["1"] = session

    bot._finish_date(1, session, "ending", now=1000.0)

    assert "1" not in bot.active_dates
    assert session["state"] == "closed"
    assert diary and diary[0][0] == "date"


def test_date_context_section_states():
    bot.active_dates = {}
    assert bot.date_context_section(1) == ""
    session = game.new_date_session("la playa", 40, now=0.0)
    bot.active_dates["1"] = session
    section = bot.date_context_section(1)
    assert "CITA EN CURSO" in section
    assert "date_decision" in section
    session["state"] = "last_chance"
    session["turns"] = 3
    section = bot.date_context_section(1)
    assert "ÚLTIMA OPORTUNIDAD" in section
    assert "last_chance_result" in section


# ============================================================
# CITAS EXCLUSIVAS: AVISOS Y EXPIRACIÓN
# ============================================================


def _busy_setup(monkeypatch):
    """Prepara bot para probar el bloqueo por cita activa, sin disco."""
    monkeypatch.setattr(bot, "save_dates", lambda: None)
    monkeypatch.setattr(bot, "save_diary", lambda: None)
    monkeypatch.setattr(bot, "log_diary_event", lambda kind, user, text: None)
    bot.world_data = game.default_world()
    bot.users_data = {"1": {"name": "Ana"}, "2": {"name": "Beto"}}
    bot.diary_data = []
    bot.active_dates = {}
    bot._busy_notice_at = {}


def test_busy_date_owner_empty(monkeypatch):
    _busy_setup(monkeypatch)
    assert bot.busy_date_owner(exclude_id=1) == (None, None)


def test_busy_date_owner_detects_other(monkeypatch):
    _busy_setup(monkeypatch)
    session = game.new_date_session("la playa", 40, now=time.time())
    bot.active_dates["2"] = session
    owner_id, owner_session = bot.busy_date_owner(exclude_id=1)
    assert owner_id == "2"
    assert owner_session is session


def test_busy_date_owner_excludes_self(monkeypatch):
    _busy_setup(monkeypatch)
    bot.active_dates["1"] = game.new_date_session("la playa", 40, now=time.time())
    assert bot.busy_date_owner(exclude_id=1) == (None, None)


def test_busy_date_owner_expires_stale(monkeypatch):
    _busy_setup(monkeypatch)
    session = game.new_date_session("la playa", 40, now=0.0)  # caducada (epoch)
    bot.active_dates["2"] = session
    assert bot.busy_date_owner(exclude_id=1) == (None, None)
    assert "2" not in bot.active_dates
    assert session["state"] == "closed"


def test_expire_stale_dates_returns_uids(monkeypatch):
    _busy_setup(monkeypatch)
    bot.active_dates["2"] = game.new_date_session("la playa", 40, now=0.0)
    bot.active_dates["3"] = game.new_date_session("la playa", 40, now=time.time())
    expired = bot.expire_stale_dates()
    assert expired == ["2"]
    assert "3" in bot.active_dates


def test_date_busy_text_mentions_name_and_time(monkeypatch):
    _busy_setup(monkeypatch)
    session = game.new_date_session("la playa", 40, now=0.0)
    text = bot.date_busy_text("2", session, now=0.0)
    assert "Beto" in text
    assert "min" in text


def test_notify_busy_respects_cooldown(monkeypatch):
    _busy_setup(monkeypatch)
    now = time.time()
    bot.active_dates["2"] = game.new_date_session("la playa", 40, now=now)
    channel = FakeChannel()
    asyncio.run(bot.notify_busy(channel, FakeUser(1, "Ana"), now=now))
    asyncio.run(bot.notify_busy(channel, FakeUser(1, "Ana"), now=now + 5))
    assert len(channel.sent) == 1
    later = now + bot.DATE_BUSY_NOTICE_COOLDOWN + 1
    asyncio.run(bot.notify_busy(channel, FakeUser(1, "Ana"), now=later))
    assert len(channel.sent) == 2


def test_notify_busy_silent_when_free(monkeypatch):
    _busy_setup(monkeypatch)
    channel = FakeChannel()
    asyncio.run(bot.notify_busy(channel, FakeUser(1, "Ana")))
    assert channel.sent == []
