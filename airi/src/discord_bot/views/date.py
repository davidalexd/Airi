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

DATE_EMBED_COLOR = discord.Color(0xFFB6D9)

FREE_TEXT_LABEL = "Responder libremente"


def clamp_label(text, limit=DISCORD_LABEL_MAX):
    """Normaliza una etiqueta a una sola línea y la recorta al límite de Discord."""
    text = " ".join(str(text or "").split())
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def build_date_embed(
    reply,
    *,
    title=None,
    scene=None,
    state="active",
    turns_left=None,
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
    if footer:
        embed.set_footer(text=" · ".join(footer))
    if gif_url:
        embed.set_image(url=gif_url)
    return embed


class _PayloadButton(discord.ui.Button):
    """Botón que reenvía su payload al manejador de su vista."""

    def __init__(self, label, payload, *, style=discord.ButtonStyle.primary):
        super().__init__(label=clamp_label(label), style=style)
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
    """Selector inicial de escena: una opción por escena + "Sorpréndeme"."""

    def __init__(self, owner_id, scenes, on_choice, *, timeout=120):
        super().__init__(owner_id, timeout=timeout)
        self.on_choice = on_choice
        for scene in scenes[: DISCORD_MAX_BUTTONS - 1]:
            self.add_item(_PayloadButton(scene, scene))
        self.add_item(
            _PayloadButton(
                "Sorpréndeme 🎲", None, style=discord.ButtonStyle.success
            )
        )


class DateChoiceView(_OwnerView):
    """Acciones por turno (generadas por la IA) + opción de texto libre."""

    def __init__(self, owner_id, actions, on_choice, *, timeout):
        super().__init__(owner_id, timeout=timeout)
        self.on_choice = on_choice
        for item in actions[:4]:
            label = item.get("label") if isinstance(item, dict) else None
            text = item.get("action") if isinstance(item, dict) else None
            self.add_item(_PayloadButton(label or text, text or label))
        self.add_item(_FreeTextButton())
