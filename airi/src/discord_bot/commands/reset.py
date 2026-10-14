"""Comando !reset (reinicia la conversación de ese usuario)."""


async def handle(ctx, message):
    ctx.reset_conversation(message.channel.id, message.author.id)
    await message.reply(
        "¡Listo! He reiniciado nuestra conversación. ¡Empezamos de nuevo!",
        mention_author=False,
    )
