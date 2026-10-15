"""Vistas de Discord para el sistema de citas de Airi.

Este módulo solo sabe de interfaz (embeds y botones). No importa `bot` ni
contiene lógica de juego: los callbacks (`on_scene`, `on_choice`) se inyectan
desde la capa de turno, lo que evita un import circular y mantiene separada la UI.

Regla de oro: la IA decide las situaciones y las opciones; aquí solo se
convierten en botones y se valida que quien pulsa sea el dueño de la cita.
"""

import discord

DISCORD_LABEL_MAX = 80
DISCORD_MAX_BUTTONS = 25

DATE_EMBED_COLOR = discord.Color(0xF472B6)

DATE_SCENE_EMOJIS = ("🕯️", "🍿", "🎡")
DATE_SCENE_LABEL_MAX = 30
DATE_SCENE_STOPWORDS = frozenset(
    {"y", "e", "o", "u", "de", "del", "con", "a", "al", "en",
     "la", "el", "los", "las", "un", "una", "por", "para", "que"}
)

FREE_TEXT_LABEL = "Responder libremente"


def clamp_label(text, limit=DISCORD_LABEL_MAX):
    """Normaliza una etiqueta a una sola línea y la recorta al límite de Discord."""
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def scene_label(scene, limit=DATE_SCENE_LABEL_MAX):
    """Etiqueta de botón a partir de una escena: una línea, con mayúscula inicial y recortada.

    El recorte se hace en frontera de palabra y descarta conectores colgantes al
    final, para que la etiqueta sea legible en móvil.
    """
    text = " ".join(str(scene or "").split())
    if text:
        text = text[:1].upper() + text[1:]
    if len(text) <= limit:
        return text
    head = text[: limit - 1].rstrip()
    if " " in head:
        head = head.rsplit(" ", 1)[0].rstrip()
    while " " in head and head.split()[-1].lower() in DATE_SCENE_STOPWORDS:
        head = head.rsplit(" ", 1)[0].rstrip()
    if not head:
        head = text[: limit - 1].rstrip()
    return head + "…"


def remaining_time_text(seconds_left):
    """Texto compacto del tiempo restante: `<1 min` o `~N min` (redondeo al alza)."""
    try:
        seconds = int(seconds_left)
    except (TypeError, ValueError):
        return None
    if seconds < 60:
        return "<1 min"
    return f"~{(seconds + 59) // 60} min"


def build_date_embed(
    reply,
    *,
    title=None,
    scene=None,
    state="active",
    turns_left=None,
    seconds_left=None,
    gif_url=None,
):
    """Embed que enmarca un turno de cita: respuesta de Airi + estado."""
    embed = discord.Embed(description=reply or "…", color=DATE_EMBED_COLOR)
    if title:
        embed.title = title
    elif scene:
        embed.title = f"🌹 Cita · {scene}"
    footer = []
    if state == "last_chance":
        footer.append("Última oportunidad")
    elif state == "closed":
        footer.append("Cita finalizada")
    if turns_left is not None:
        footer.append(f"Turnos restantes: {turns_left}")
    time_text = remaining_time_text(seconds_left)
    if time_text is not None:
        footer.append(f"⏳ {time_text}")
    if footer:
        embed.set_footer(text=" · ".join(footer))
    if gif_url:
        embed.set_image(url=gif_url)
    return embed


class _PayloadButton(discord.ui.Button):
    """Botón que reenvía su payload al manejador de su vista."""

    def __init__(
        self,
        label,
        payload,
        *,
        style=discord.ButtonStyle.primary,
        emoji=None,
    ):
        super().__init__(label=clamp_label(label), style=style, emoji=emoji)
        self.payload = payload

    async def callback(self, interaction):
        await self.view.handle_choice(interaction, self.payload)


class _FreeTextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label=FREE_TEXT_LABEL, style=discord.ButtonStyle.secondary
        )

    async def callback(self, interaction):
        await interaction.response.send_message(
            "Escribe con tus propias palabras lo que quieras hacer o decirle~",
            ephemeral=True,
        )


class _OwnerView(discord.ui.View):
    """Base: comprueba el dueño y deshabilita los botones al elegir."""

    def __init__(self, owner_id, *, timeout):
        super().__init__(timeout=timeout)
        self.owner_id = owner_id

    def disable_all(self):
        for child in self.children:
            child.disabled = True

    async def handle_choice(self, interaction, payload):
        if interaction.user.id != self.owner_id:
            owner_mention = f"<@{self.owner_id}>"
            await interaction.response.send_message(
                f"Esa cita no es contigo, es de {owner_mention}~",
                ephemeral=True,
            )
            return
        self.disable_all()
        try:
            await interaction.response.edit_message(view=self)
        except discord.HTTPException:
            pass
        await self.on_choice(interaction, payload)

    async def on_choice(self, interaction, payload):  # pragma: no cover - override
        raise NotImplementedError

    async def on_timeout(self):
        self.disable_all()
        message = getattr(self, "message", None)
        if message is None:
            return
        try:
            await message.edit(view=self)
        except discord.HTTPException:
            pass


class SceneSelectView(_OwnerView):
    """Selector inicial: hasta 3 planes (con emoji por posición) + "Sorpréndeme"."""

    def __init__(self, owner_id, scenes, on_choice, *, timeout=120):
        super().__init__(owner_id, timeout=timeout)
        self.on_choice = on_choice

        # Fila 1: opciones de escena
        for scene, emoji in zip(scenes, DATE_SCENE_EMOJIS):
            self.add_item(_PayloadButton(scene_label(scene), scene, emoji=emoji))

        # Fila 2: opción "dejar que el azar decida"
        self.add_item(
            _PayloadButton(
                "Sorpréndeme", None, emoji="🎲", style=discord.ButtonStyle.secondary
            )
        )


class DateChoiceView(_OwnerView):
    """Acciones por turno (generadas por la IA) + opción de texto libre."""

    def __init__(self, owner_id, actions, on_choice, *, timeout):
        super().__init__(owner_id, timeout=timeout)
        self.on_choice = on_choice

        # Fila 1: acciones sugeridas (máximo 4)
        for item in actions[:4]:
            label = item.get("label") if isinstance(item, dict) else None
            text = item.get("action") if isinstance(item, dict) else None
            self.add_item(_PayloadButton(label or text, text or label))

        # Fila 2: respuesta libre
        self.add_item(_FreeTextButton())
