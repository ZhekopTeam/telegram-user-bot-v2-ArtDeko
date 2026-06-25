from aiogram import Bot
from config import settings
from utils.database import AccountRepository
from utils.logger import logger


async def notify_session_revoked(bot: Bot, tg_id: int, phone: str, reason: str) -> None:
    """Уведомить админа что сессия слетела + пометить revoked в БД."""
    repo = AccountRepository()
    account = await repo.get_by_tg_id(tg_id)
    if account and account.status != "revoked":
        await repo.mark_revoked(tg_id)

    text = (
        "⚠️ <b>Сессия аккаунта слетела</b>\n\n"
        f"📱 {phone}\n"
        f"💬 Причина: <code>{reason}</code>\n\n"
        "Аккаунт больше не участвует в прогреве. "
        "Удалите его и добавьте заново."
    )

    target = account.admin_tg_id if account and account.admin_tg_id else None
    recipients = [target] if target else settings.admins_list

    for admin_id in recipients:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")


async def notify_admins(bot: Bot, text: str) -> None:
    """Отправить сообщение всем админам из .env."""
    for admin_id in settings.admins_list:
        try:
            await bot.send_message(admin_id, text)
        except Exception as e:
            logger.error(f"Error notifying admin {admin_id}: {e}")
