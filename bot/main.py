import asyncio

import app
from config import bot, dp, settings
from utils.logger import logger
from utils import set_command
from utils.accounts_auth import AccountAuth
from utils.database import init_db
from accounts import ClientManager, WarmupDispatcher


async def _wait_for_telegram() -> None:
    # JOKE: Программист умер и попал в ад. Там сказали: "Тут тоже retry-логика, просто интервалы длиннее."
    delay = 5
    for attempt in range(1, 13):
        try:
            me = await bot.get_me()
            logger.info(f"me - @{me.username}")
            return
        except Exception as e:
            logger.warning(
                f"Telegram unavailable (attempt {attempt}/12): {e}. Retry in {delay}s")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)
    raise RuntimeError("Telegram is unreachable after 12 attempts, giving up")


async def main() -> None:
    if bot is None or dp is None:
        raise RuntimeError("BOT_TOKEN is not set in .env")

    await _wait_for_telegram()
    logger.info(f"admins: {settings.admins_list}")

    await init_db()

    client_manager = ClientManager(bot)
    warmup_dispatcher = WarmupDispatcher(bot, client_manager)
    account_auth = AccountAuth()

    warmup_dispatcher.start()

    dp.include_routers(app.router_main)
    await set_command(bot)
    await bot.delete_webhook(drop_pending_updates=True)

    try:
        await dp.start_polling(
            bot,
            skip_updates=True,
            account_auth=account_auth,
            client_manager=client_manager,
            warmup_dispatcher=warmup_dispatcher,
        )
    except Exception as e:
        logger.error(f"Fatal error in polling loop: {e}")
        raise
    finally:
        await warmup_dispatcher.shutdown()
        await client_manager.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
