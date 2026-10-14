"""Taxonomía de GIFs de Airi: tipos permitidos, categorías y títulos."""

ALLOWED_GIF_TYPES = {
    "none", "happy", "shy", "hug", "sad", "surprised", "wink", "wave",
    "laugh", "angry", "dance", "kiss", "pat", "think", "nod",
    "bored", "smug", "sleep", "hungry", "nope",
}

GIF_CATEGORIES = {
    "happy": ["happy", "smile"],
    "shy": ["blush", "pout"],
    "hug": ["hug", "cuddle"],
    "sad": ["cry"],
    "surprised": ["shocked", "confused"],
    "wink": ["wink"],
    "wave": ["wave"],
    "laugh": ["laugh", "teehee"],
    "angry": ["angry"],
    "dance": ["dance", "spin"],
    "kiss": ["kiss", "blowkiss", "peck"],
    "pat": ["pat"],
    "think": ["think", "shrug"],
    "nod": ["nod", "thumbsup"],
    "bored": ["bored", "bleh"],
    "smug": ["smug", "teehee"],
    "sleep": ["sleep", "yawn", "lappillow"],
    "hungry": ["nom", "feed"],
    "nope": ["nope", "facepalm"],
}

# Título del embed asociado a cada emoción elegida por el modelo.
GIF_EMOTION_TITLES = {
    "happy": "Airi está feliz~",
    "shy": "Airi se sonroja...",
    "hug": "Airi quiere un abrazo",
    "sad": "Airi está triste...",
    "surprised": "¡Airi se queda sorprendida!",
    "wink": "Airi te hace un guiño~",
    "wave": "Airi te saluda~",
    "laugh": "Airi se ríe a carcajadas~",
    "angry": "Airi está enfadada (¡un poquito!)",
    "dance": "Airi baila de la alegría~",
    "kiss": "Airi manda un besito...",
    "pat": "Airi acepta unas caricias~",
    "think": "Airi lo está pensando...",
    "nod": "Airi asiente con entusiasmo",
    "bored": "Airi está un poco aburrida...",
    "smug": "Airi pone su cara de saber algo~",
    "sleep": "Airi tiene sueño...",
    "hungry": "Airi tiene hambre~",
    "nope": "Airi dice que no~",
}
