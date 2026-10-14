"""Tests de la lógica pura del simulador de citas (game.py)."""

import game

DAY = 86400.0


def test_affinity_level_boundaries():
    assert game.affinity_level(-100)[0] == "Bloqueada"
    assert game.affinity_level(-50)[0] == "Enfadada"
    assert game.affinity_level(-20)[0] == "Molesta"
    assert game.affinity_level(-1)[0] == "Distante"
    assert game.affinity_level(0)[0] == "Desconocida"
    assert game.affinity_level(10)[0] == "Conocida"
    assert game.affinity_level(25)[0] == "Amiga"
    assert game.affinity_level(45)[0] == "Interés"
    assert game.affinity_level(70)[0] == "Enamorada"
    assert game.affinity_level(100)[0] == "Novios"


def test_affinity_level_returns_next_threshold():
    name, current, nxt = game.affinity_level(30)
    assert name == "Amiga"
    assert current == 25
    assert nxt == 45


def test_affinity_level_max_has_no_next():
    name, current, nxt = game.affinity_level(250)
    assert name == "Novios"
    assert nxt is None


def test_affinity_summary_progress_bar():
    points, name, progress = game.affinity_summary(30)
    assert points == 30
    assert name == "Amiga"
    assert "%" in progress


def test_clamp_delta():
    assert game.clamp_delta(99) == game.AFFINITY_DELTA_MAX
    assert game.clamp_delta(-99) == game.AFFINITY_DELTA_MIN
    assert game.clamp_delta(3) == 3
    # Durante una cita el tope sube a 8.
    assert game.clamp_delta(99, delta_max=8) == 8


def test_can_date_requires_amiga():
    assert game.can_date(0) is False
    assert game.can_date(24) is False  # Conocida
    assert game.can_date(25) is True  # Amiga
    assert game.can_date(45) is True  # Interés
    assert game.can_date(120) is True  # Novios


def test_level_rank_ordering():
    assert game.level_rank("Amiga") < game.level_rank("Interés")
    assert game.level_rank("inexistente") == -1


def test_default_entry_shape():
    entry = game.default_entry()
    assert entry["points"] == 0
    assert entry["milestones"] == []


def test_apply_affinity_delta_positive():
    entry = game.default_entry()
    applied = game.apply_affinity_delta(entry, 4, now=1000.0)
    assert applied == 4
    assert entry["points"] == 4
    assert entry["last_interaction"] == 1000.0


def test_apply_affinity_delta_negative_not_capped():
    entry = game.default_entry()
    entry["points"] = 50
    applied = game.apply_affinity_delta(entry, -3, now=1000.0)
    assert applied == -3
    assert entry["points"] == 47


def test_apply_affinity_delta_respects_floor():
    entry = game.default_entry()
    entry["points"] = game.AFFINITY_FLOOR + 2
    game.apply_affinity_delta(entry, -5, now=1000.0)
    assert entry["points"] == game.AFFINITY_FLOOR


def test_apply_affinity_delta_has_no_daily_cap():
    entry = game.default_entry()
    now = 1000.0
    # Sin cupo diario: cada subida de Airi se aplica completa.
    total = 0
    for _ in range(50):
        total += game.apply_affinity_delta(entry, 5, now=now)
    assert total == 250
    assert entry["points"] == 250


def test_decay_reduces_points_after_inactivity():
    entry = game.default_entry()
    entry["points"] = 40
    entry["last_interaction"] = 1000.0
    # 3 días de inactividad -> -3.
    applied = game.apply_affinity_delta(entry, 1, now=1000.0 + 3 * DAY)
    assert entry["points"] == 40 - 3 * game.DECAY_PER_DAY + applied


def test_no_decay_for_legacy_entry_without_timestamp():
    # Entradas antiguas no tienen last_interaction: no deben sufrir decay.
    entry = {"points": 40, "last_gain": 0.0}
    game.apply_affinity_delta(entry, 1, now=10 * DAY)
    assert entry["points"] == 41


def test_maybe_crown_winner_none_below_threshold():
    world = game.default_world()
    data = {"a": {"points": 50}, "b": {"points": 80}}
    assert game.maybe_crown_winner(world, data, now=1.0) is None
    assert world["winner_id"] is None


def test_maybe_crown_winner_picks_highest():
    world = game.default_world()
    data = {"a": {"points": 100}, "b": {"points": 120}}
    winner = game.maybe_crown_winner(world, data, now=1.0)
    assert winner == "b"
    assert world["winner_id"] == "b"
    assert world["relationship_started_at"] == 1.0


def test_maybe_crown_winner_is_idempotent():
    world = game.default_world()
    data = {"a": {"points": 100}}
    assert game.maybe_crown_winner(world, data, now=1.0) == "a"
    # Segunda llamada no cambia nada.
    assert game.maybe_crown_winner(world, data, now=2.0) is None


def test_is_winner():
    world = {"winner_id": "b"}
    assert game.is_winner(world, "b") is True
    assert game.is_winner(world, "a") is False
    assert game.is_winner({}, "a") is False


def test_apply_winner_lock_caps_losers():
    world = {"winner_id": "a"}
    data = {"a": {"points": 100}, "b": {"points": 90}, "c": {"points": 10}}
    game.apply_winner_lock(world, data)
    assert data["a"]["points"] == 100
    assert data["b"]["points"] == game.FRIENDZONE_CAP
    assert data["c"]["points"] == 10


def test_apply_winner_lock_noop_without_winner():
    world = {"winner_id": None}
    data = {"b": {"points": 90}}
    game.apply_winner_lock(world, data)
    assert data["b"]["points"] == 90


def test_ranking_orders_and_flags_winner():
    data = {
        "a": {"points": 10},
        "b": {"points": 90},
        "c": {"points": 40},
        "_skip": {"points": 999},
    }
    users = {"a": {"name": "Ana"}, "b": {"name": "Beto"}, "c": {"name": "Caro"}}
    rows = game.ranking(data, users, winner_id="b")
    assert [r["user_id"] for r in rows] == ["b", "c", "a"]
    assert rows[0]["is_winner"] is True
    assert rows[0]["name"] == "Beto"


def test_gift_effect_loved_tag():
    prefs = {"loves": ["romantico"], "dislikes": ["grosero"]}
    assert game.gift_effect("flores", prefs) > 0


def test_gift_effect_unknown_item():
    prefs = {"loves": [], "dislikes": []}
    assert game.gift_effect("inventado", prefs) == 0


def test_gift_effect_repeat_is_boring():
    prefs = {"loves": ["romantico"], "dislikes": []}
    effect = game.gift_effect("flores", prefs, recent_gifts=["flores"])
    assert effect == 0


def test_gift_effect_clamped():
    prefs = {"loves": ["romantico", "tierno", "caro"], "dislikes": []}
    assert game.gift_effect("collar", prefs) <= game.AFFINITY_DELTA_MAX


def test_json_round_trip(tmp_path):
    path = tmp_path / "x.json"
    game.save_json(str(path), {"hola": 1})
    assert game.load_json(str(path), {}) == {"hola": 1}


def test_load_json_missing_returns_default(tmp_path):
    path = tmp_path / "nope.json"
    assert game.load_json(str(path), {"d": 1}) == {"d": 1}


def test_load_json_corrupt_returns_default(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{no json", encoding="utf-8")
    assert game.load_json(str(path), {"d": 2}) == {"d": 2}


def test_load_json_list_round_trip(tmp_path):
    path = tmp_path / "list.json"
    game.save_json(str(path), [{"a": 1}])
    assert game.load_json_list(str(path)) == [{"a": 1}]


def test_load_json_list_missing_and_corrupt(tmp_path):
    assert game.load_json_list(str(tmp_path / "nope.json")) == []
    bad = tmp_path / "bad.json"
    bad.write_text("{no json", encoding="utf-8")
    assert game.load_json_list(str(bad)) == []


def test_new_diary_entry_shape():
    entry = game.new_diary_entry("gift", "42", "Ana", "me gustó", 1000.0, season=2)
    assert entry["kind"] == "gift"
    assert entry["user_id"] == "42"
    assert entry["user_name"] == "Ana"
    assert entry["text"] == "me gustó"
    assert entry["ts"] == 1000.0
    assert entry["season"] == 2


def test_add_diary_entry_rejects_invalid():
    diary = []
    assert game.add_diary_entry(diary, None) is False
    assert game.add_diary_entry(diary, {"text": ""}) is False
    assert diary == []


def test_add_diary_entry_respects_fifo_cap():
    diary = []
    for i in range(game.DIARY_MAX_ENTRIES + 5):
        game.add_diary_entry(
            diary, game.new_diary_entry("meet", str(i), "X", f"nota {i}", 100.0 + i)
        )
    assert len(diary) == game.DIARY_MAX_ENTRIES
    assert diary[0]["text"] == "nota 5"


def test_diary_for_user_and_recent():
    diary = []
    game.add_diary_entry(diary, game.new_diary_entry("meet", "1", "A", "a1", 1.0))
    game.add_diary_entry(diary, game.new_diary_entry("gift", "2", "B", "b1", 2.0))
    game.add_diary_entry(diary, game.new_diary_entry("level", "1", "A", "a2", 3.0))
    assert [r["text"] for r in game.diary_for_user(diary, "1")] == ["a1", "a2"]
    assert game.diary_for_user(diary, "1", limit=1)[0]["text"] == "a2"
    assert [r["text"] for r in game.recent_diary(diary, limit=2)] == ["b1", "a2"]


def test_purge_user_diary():
    diary = []
    game.add_diary_entry(diary, game.new_diary_entry("meet", "1", "A", "a", 1.0))
    game.add_diary_entry(diary, game.new_diary_entry("meet", "2", "B", "b", 2.0))
    assert game.purge_user_diary(diary, "1") == 1
    assert [e["user_id"] for e in diary] == ["2"]


def test_format_relative_time():
    base = 1_000_000.0
    assert game.format_relative_time(base, base) == "ahora mismo"
    assert game.format_relative_time(base - 3600, base) == "hace 1 h"
    assert game.format_relative_time(base - DAY, base) == "ayer"
    assert "2 días" in game.format_relative_time(base - 2 * DAY - 10, base)


# ============================================================
# MÁQUINA DE ESTADOS DE LAS CITAS
# ============================================================


def test_new_date_session_shape():
    s = game.new_date_session("una cita en la playa", 40, now=1000.0)
    assert s["scene"] == "una cita en la playa"
    assert s["state"] == "active"
    assert s["turns"] == 0
    assert s["affinity_start"] == 40
    assert s["affinity_crisis"] is None
    assert s["crisis_reason"] == "none"
    assert s["last_chance_used"] is False
    assert s["last_chance_result"] == "none"
    assert s["history"] == []
    assert s["started_at"] == 1000.0


def test_new_date_session_coerces_bad_affinity():
    s = game.new_date_session(None, "no-numero", now=0.0)
    assert s["affinity_start"] == 0
    assert s["scene"] == ""


def test_normalize_date_session_fills_and_repairs():
    s = {"scene": "x", "state": "banana", "turns": "3", "history": "nope"}
    out = game.normalize_date_session(s)
    assert out is s
    assert out["state"] == "active"  # estado inválido reparado
    assert out["turns"] == 3
    assert out["history"] == []
    assert out["affinity_start"] == 0
    assert out["last_chance_result"] == "none"


def test_normalize_date_session_non_dict():
    assert game.normalize_date_session(None) is None
    assert game.normalize_date_session("x") is None


def test_crisis_allowed_requires_min_turns():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.crisis_allowed(s) is False
    s["turns"] = game.DATE_CRISIS_MIN_TURNS
    assert game.crisis_allowed(s) is True
    # Ya usada la última oportunidad, no vuelve a haber crisis.
    s["last_chance_used"] = True
    assert game.crisis_allowed(s) is False


def test_end_allowed_requires_min_turns():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.end_allowed(s) is False
    s["turns"] = game.DATE_END_MIN_TURNS
    assert game.end_allowed(s) is True
    s["state"] = "closed"
    assert game.end_allowed(s) is False


def test_step_date_active_continues_early():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.step_date(s, points=41, decision="continue") == ("active", "continue")
    assert s["turns"] == 1


def test_step_date_decision_end_ignored_before_min_turns():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.step_date(s, points=40, decision="end") == ("active", "continue")


def test_step_date_decision_end_after_min_turns():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_END_MIN_TURNS
    assert game.step_date(s, points=40, decision="end") == ("final_scene", "ending")


def test_step_date_end_keyword_closes_immediately():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.step_date(s, points=40, end_keyword=True) == ("final_scene", "ending")


def test_step_date_crisis_by_decision():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_CRISIS_MIN_TURNS
    state, event = game.step_date(s, points=40, decision="crisis", reason="se pasó")
    assert state == "last_chance"
    assert event == "crisis"
    assert s["last_chance_used"] is True
    assert s["crisis_reason"] == "se pasó"


def test_step_date_crisis_by_affinity_drop():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_CRISIS_MIN_TURNS
    # Caída de 4 desde el inicio -> crisis aunque el modelo no la marque.
    state, event = game.step_date(s, points=40 - game.DATE_CRISIS_DROP)
    assert state == "last_chance"
    assert event == "crisis"
    assert s["affinity_crisis"] == 36


def test_step_date_no_crisis_before_min_turns_even_with_drop():
    s = game.new_date_session("x", 40, now=0.0)
    state, event = game.step_date(s, points=10)
    assert (state, event) == ("active", "continue")


def test_step_date_last_chance_success():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_CRISIS_MIN_TURNS
    game.step_date(s, points=34, decision="crisis")
    state, event = game.step_date(s, points=36, last_chance_result="success")
    assert (state, event) == ("final_scene", "recovered")
    assert s["last_chance_result"] == "success"


def test_step_date_last_chance_partial_and_fail():
    for result, event in (("partial", "partial_recovery"), ("fail", "failed_last_chance")):
        s = game.new_date_session("x", 40, now=0.0)
        s["turns"] = game.DATE_CRISIS_MIN_TURNS
        game.step_date(s, points=34, decision="crisis")
        state, got = game.step_date(s, points=34, last_chance_result=result)
        assert (state, got) == ("final_scene", event)
        assert s["last_chance_result"] == result


def test_step_date_last_chance_without_result_continues():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_CRISIS_MIN_TURNS
    game.step_date(s, points=34, decision="crisis")
    assert game.step_date(s, points=35) == ("last_chance", "continue")


def test_step_date_turn_limit_resolves_active():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_MAX_TURNS - 1
    state, event = game.step_date(s, points=40)
    assert (state, event) == ("final_scene", "ending")


def test_step_date_turn_limit_in_last_chance_fails_without_result():
    s = game.new_date_session("x", 40, now=0.0)
    s["turns"] = game.DATE_MAX_TURNS - 1
    s["state"] = "last_chance"
    state, event = game.step_date(s, points=30)
    assert (state, event) == ("final_scene", "failed_last_chance")
    assert s["last_chance_result"] == "fail"


def test_step_date_final_scene_closes():
    s = game.new_date_session("x", 40, now=0.0)
    s["state"] = "final_scene"
    assert game.step_date(s) == ("closed", "closed")
    assert s["state"] == "closed"


def test_step_date_closed_is_terminal():
    s = game.new_date_session("x", 40, now=0.0)
    s["state"] = "closed"
    assert game.step_date(s) == ("closed", "closed")


def test_step_date_non_dict():
    assert game.step_date(None) == ("closed", "closed")


def test_last_chance_recovery_success_capped_by_start():
    s = game.new_date_session("x", 40, now=0.0)
    # Actual 32: techo = 40-32 = 8, aunque el máximo sea 12.
    assert game.last_chance_recovery(s, "success", 32) == 8


def test_last_chance_recovery_success_max_when_far():
    s = game.new_date_session("x", 100, now=0.0)
    assert game.last_chance_recovery(s, "success", 0) == game.DATE_LAST_CHANCE_MAX_RECOVERY


def test_last_chance_recovery_partial_is_half():
    s = game.new_date_session("x", 100, now=0.0)
    assert game.last_chance_recovery(s, "partial", 0) == game.DATE_LAST_CHANCE_MAX_RECOVERY // 2


def test_last_chance_recovery_fail_is_zero():
    s = game.new_date_session("x", 100, now=0.0)
    assert game.last_chance_recovery(s, "fail", 0) == 0
    assert game.last_chance_recovery(s, "none", 0) == 0


def test_last_chance_recovery_never_exceeds_start():
    s = game.new_date_session("x", 40, now=0.0)
    # Ya por encima del inicio: no se recupera nada.
    assert game.last_chance_recovery(s, "success", 45) == 0


def test_resolve_date_at_limit_success():
    s = game.new_date_session("x", 40, now=0.0)
    s["state"] = "last_chance"
    s["last_chance_result"] = "success"
    assert game.resolve_date_at_limit(s) == "recovered"
    assert s["state"] == "final_scene"


def test_resolve_date_at_limit_fail_without_result():
    s = game.new_date_session("x", 40, now=0.0)
    s["state"] = "last_chance"
    assert game.resolve_date_at_limit(s) == "failed_last_chance"
    assert s["last_chance_result"] == "fail"


def test_resolve_date_at_limit_active_ends_normally():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.resolve_date_at_limit(s) == "ending"
    assert s["state"] == "final_scene"


def test_full_date_happy_path():
    s = game.new_date_session("x", 40, now=0.0)
    for _ in range(game.DATE_MAX_TURNS - 1):
        state, event = game.step_date(s, points=40, decision="continue")
        assert (state, event) == ("active", "continue")
    assert game.step_date(s, points=42, decision="end") == ("final_scene", "ending")


def test_date_turns_left():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.date_turns_left(s) == game.DATE_MAX_TURNS
    s["turns"] = 2
    assert game.date_turns_left(s) == game.DATE_MAX_TURNS - 2
    s["turns"] = game.DATE_MAX_TURNS
    assert game.date_turns_left(s) == 0


def test_date_seconds_left_and_expired():
    s = game.new_date_session("x", 40, now=1000.0)
    assert game.date_seconds_left(s, 1000.0) == game.DATE_MAX_SECONDS
    assert not game.date_expired(s, 1000.0 + game.DATE_MAX_SECONDS - 1)
    assert game.date_expired(s, 1000.0 + game.DATE_MAX_SECONDS)


def test_date_seconds_left_never_negative():
    s = game.new_date_session("x", 40, now=0.0)
    assert game.date_seconds_left(s, game.DATE_MAX_SECONDS * 10) == 0


def test_date_expired_false_when_closed():
    s = game.new_date_session("x", 40, now=0.0)
    s["state"] = "closed"
    assert not game.date_expired(s, game.DATE_MAX_SECONDS * 10)
    assert game.date_seconds_left(s, game.DATE_MAX_SECONDS * 10) == 0


def test_date_helpers_tolerate_non_dict():
    assert game.date_turns_left(None) == 0
    assert game.date_seconds_left(None, 0.0) == 0
    assert game.date_expired(None, 999999.0) is False


def test_env_int_default_when_missing(monkeypatch):
    monkeypatch.delenv("AIRI_TEST_INT", raising=False)
    assert game.env_int("AIRI_TEST_INT", 7) == 7


def test_env_int_parses_and_negative(monkeypatch):
    monkeypatch.setenv("AIRI_TEST_INT", "42")
    assert game.env_int("AIRI_TEST_INT", 7) == 42
    monkeypatch.setenv("AIRI_TEST_INT", "-100")
    assert game.env_int("AIRI_TEST_INT", 0) == -100


def test_env_int_empty_or_invalid_uses_default(monkeypatch):
    monkeypatch.setenv("AIRI_TEST_INT", "   ")
    assert game.env_int("AIRI_TEST_INT", 7) == 7
    monkeypatch.setenv("AIRI_TEST_INT", "abc")
    assert game.env_int("AIRI_TEST_INT", 7) == 7


def test_env_float_parses_and_defaults(monkeypatch):
    monkeypatch.setenv("AIRI_TEST_FLOAT", "2.5")
    assert game.env_float("AIRI_TEST_FLOAT", 1.0) == 2.5
    monkeypatch.setenv("AIRI_TEST_FLOAT", "nope")
    assert game.env_float("AIRI_TEST_FLOAT", 1.0) == 1.0
