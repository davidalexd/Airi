"""Textos narrativos puros de Airi (citas, confesión, regalos)."""

from __future__ import annotations

from airi.domain.config import DATE_MAX_TURNS

DATE_END_KEYWORDS = ("fin", "adios", "adiós", "hasta luego", "se acabo", "se acabó")

def confession_text(name):
    return (
        f"*Airi respira hondo, con las mejillas encendidas, y te mira "
        "directamente a los ojos.*\n\n"
        f"«{name}... llevo un tiempo dándome cuenta de algo. Cada vez que hablas "
        "conmigo me late el corazón más deprisa, y cuando no estás te echo de "
        "menos. Ya no puedo seguir llamándote solo mi amigo.»\n\n"
        "*da un paso hacia ti y te ofrece la mano, temblando un poquito.*\n\n"
        f"«{name}, ¿quieres estar conmigo? ¿Quieres ser mi pareja?»\n\n"
        "💗 ¡Airi ha elegido! A partir de ahora **sois novios**. 💗"
    )

def gift_reaction(item, effect):
    if effect > 0:
        return (
            f"*Airi abre los ojos con una sonrisa y se sonroja.*\n"
            f"«¡Uh... {item}! Es justo lo que me gusta... ¿cómo lo sabías? "
            "Gracias~»"
        )
    if effect < 0:
        return (
            f"*Airi mira {item}, luego a ti, y arquea una ceja.*\n"
            "«Mmh... no sé si es lo mío, pero... se agradece el detalle.»"
        )
    return (
        f"*Airi observa {item} con una sonrisa leve.*\n"
        "«Gracias... aunque creo que ya tienes algo parecido, ¿no?»"
    )

def date_intro(scene):
    return (
        f"*Airi se ilumina al aceptar.*\n«¿En serio? ¡Vale! Entonces... {scene}. "
        "Qué nervios...»\n\n*(Comienza la cita. Habla con ella y deja que el "
        f"momento fluya: durará unos {DATE_MAX_TURNS} turnos. Si las cosas "
        "se tuercen tendrás una última oportunidad para reconducirlo.)*"
    )

DATE_FINAL_TEXTS = {
    "ending": (
        "*La cita llega a su fin de forma natural.*\n"
        "«Ha sido... un momento muy bonito. *se sonroja* Me gustaría repetirlo "
        "pronto, ¿vale?»"
    ),
    "recovered": (
        "*Airi te mira con los ojos brillantes, como si hubiera pasado un miedo "
        "enorme.*\n«Pensaba que la habíamos estropeado... pero me has demostrado "
        "que te importo. *te aprieta la mano* Gracias por no rendirte conmigo.»"
    ),
    "partial_recovery": (
        "*La cita termina con una sonrisa frágil.*\n«No ha sido perfecto, pero... "
        "me has dado algo en qué pensar. *te mira de reojo* Quizá necesitemos otra "
        "oportunidad, despacio.»"
    ),
    "failed_last_chance": (
        "*Airi aparta la mirada y suspira.*\n«Creo que... hoy no era el día. "
        "Dejémoslo aquí, ¿vale? Necesito pensar.»"
    ),
}


def date_final_text(event):
    return DATE_FINAL_TEXTS.get(event, DATE_FINAL_TEXTS["ending"])


# Texto de la crisis (se envía al entrar en última oportunidad).
DATE_CRISIS_TEXT = (
    "*Algo se tuerce y Airi se queda callada un momento.*\n"
    "«Ehh... espera. No sé si esto está yendo bien. *te mira, seria* "
    "Dame un momento... ¿puedes darme UNA razón para creer que te "
    "importo de verdad?»"
)
