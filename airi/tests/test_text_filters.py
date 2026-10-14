"""Tests de caracterización de los filtros de texto del modelo.

Congelan el comportamiento actual de `strip_repetition_loop` y
`remove_repeated_previous_reply` antes de extraerlos a `airi.domain`.
"""

import bot

# ---------------------------------------------------------------------------
# strip_repetition_loop
# ---------------------------------------------------------------------------


def test_strip_repetition_empty_returns_input():
    assert bot.strip_repetition_loop("") == ""
    assert bot.strip_repetition_loop(None) is None


def test_strip_repetition_short_text_untouched():
    # Menos de 12 palabras: nunca se trunca, aunque repita.
    text_11 = "no no no no no no no no no no no"
    assert len(text_11.split()) == 11
    assert bot.strip_repetition_loop(text_11) == text_11


def test_strip_repetition_exactly_12_words_untouched():
    # 12 palabras exactas: se exige len(words) >= n * THRESHOLD (4*4=16).
    words = ["aa", "bb", "cc", "dd"] + ["repite", "mucho", "esto", "porfa"] * 2
    text = " ".join(words)
    assert len(words) == 12
    assert bot.strip_repetition_loop(text) == text


def test_strip_repetition_detects_four_word_loop():
    # 4 palabras base + 4 repeticiones de una cola de 4 palabras.
    base = "hoy hace un día"
    tail = "genial muy para pasear"
    text = base + " " + " ".join([tail] * 4)
    assert len(text.split()) == 4 + 16
    assert bot.strip_repetition_loop(text) == base


def test_strip_repetition_detects_five_word_loop():
    base = "hoy hace un día"
    tail = "quiero ir a la playa contigo"
    text = base + " " + " ".join([tail] * 4)
    # 4 + 4*5 = 24 palabras; n=4 no cuadra (24 % 4 == 0 pero cola != tail).
    assert bot.strip_repetition_loop(text) == base


def test_strip_repetition_returns_none_when_entire_text_is_loop():
    tail = "esto se repite mucho"
    text = " ".join([tail] * 4)
    assert bot.strip_repetition_loop(text) is None


def test_strip_repetition_no_loop_keeps_text():
    text = "una frase completamente normal sin ninguna clase de bucle final"
    assert bot.strip_repetition_loop(text) == text


def test_strip_repetition_three_repetitions_not_truncated():
    # Por debajo del umbral (4) no se toca.
    base = "hoy hace un día"
    tail = "genial muy para pasear"
    text = base + " " + " ".join([tail] * 3)
    assert bot.strip_repetition_loop(text) == text


# ---------------------------------------------------------------------------
# remove_repeated_previous_reply
# ---------------------------------------------------------------------------


def _history(*assistant_replies, user_msg="hola"):
    items = []
    for reply in assistant_replies:
        items.append({"role": "user", "content": user_msg})
        items.append({"role": "assistant", "content": reply})
    items.append({"role": "user", "content": user_msg})
    return items


def test_remove_repeated_short_history_untouched():
    answer = "algo nuevo"
    assert bot.remove_repeated_previous_reply(answer, []) == answer
    assert bot.remove_repeated_previous_reply(answer, [{"role": "user", "content": "x"}]) == answer


def test_remove_repeated_identical_reply_returns_none():
    history = _history("me aburro muchísimo")
    assert bot.remove_repeated_previous_reply("me aburro muchísimo", history) is None


def test_remove_repeated_prefix_strips_duplicated_prefix():
    history = _history("me aburro muchísimo")
    answer = "me aburro muchísimo y quiero hacer algo"
    assert (
        bot.remove_repeated_previous_reply(answer, history)
        == "y quiero hacer algo"
    )


def test_remove_repeated_different_reply_untouched():
    history = _history("qué ganas de comer")
    answer = "pues hoy apetece pizza"
    assert bot.remove_repeated_previous_reply(answer, history) == answer


def test_remove_repeated_no_previous_assistant_untouched():
    history = [{"role": "user", "content": "hola"}, {"role": "user", "content": "sigue"}]
    answer = "hola, ¿qué tal?"
    assert bot.remove_repeated_previous_reply(answer, history) == answer
