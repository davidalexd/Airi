"""Tests de caracterización de `reply_seems_grounded` (filtro anti-alucinación)."""

import bot


def test_no_context_is_grounded():
    assert bot.reply_seems_grounded("cualquier cosa", None) is True
    assert bot.reply_seems_grounded("cualquier cosa", "") is True


def test_year_alone_is_not_suspicious():
    context = "Fuente 1: Noticias\nURL: https://x.test\nResumen: resumen"
    reply = "La película se estrenó en 2026 según he visto."
    assert bot.reply_seems_grounded(reply, context) is True


def test_single_suspicious_date_does_not_reject():
    context = "Fuente 1: Noticias\nURL: https://x.test\nResumen: resumen"
    reply = "Se anunció el 3 de marzo que habría más noticias."
    assert bot.reply_seems_grounded(reply, context) is True


def test_date_present_in_context_is_fine():
    context = "Resumen: el estreno será el 3 de marzo de 2027."
    reply = "El estreno será el 3 de marzo de 2027, prometido."
    assert bot.reply_seems_grounded(reply, context) is True


def test_three_suspicious_dates_reject():
    context = "Resumen: hay noticias genericas sobre la serie."
    reply = (
        "Estrenan el 4 de enero, luego el 5 de febrero y finalmente "
        "el 6 de marzo la tercera parte."
    )
    assert bot.reply_seems_grounded(reply, context) is False


def test_one_suspicious_title_does_not_reject():
    context = "Resumen: la serie continúa esta temporada."
    reply = "Claramente se titula Pelicula Increible el nuevo arco."
    assert bot.reply_seems_grounded(reply, context) is True


def test_title_present_in_context_is_fine():
    context = "Resumen: Demon Slayer Anime Habria Terminado"
    reply = "Dice que Demon Slayer Anime Habría terminado ya."
    assert bot.reply_seems_grounded(reply, context) is True


def test_partial_word_match_counts_as_present():
    # Todas las palabras significativas aparecen en el contexto.
    context = "Resumen: nuevo paseo al atardecer por el parque anunciado"
    reply = "Han anunciado el Nuevo Paseo Atardecer del que hablamos."
    assert bot.reply_seems_grounded(reply, context) is True


def test_three_suspicious_titles_reject():
    context = "Resumen: la serie continúa esta temporada."
    reply = (
        "Los titulos son Rojo Electrico Total, Azul Profundo Absoluto "
        "y Verde Montaña Eterna, según fuentes."
    )
    assert bot.reply_seems_grounded(reply, context) is False
