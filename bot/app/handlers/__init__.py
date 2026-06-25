from aiogram import Router
from .accounts_repo import router_repo
from .accounts_auth import router_accounts
from .accounts_warmup import router_warmup


router_handlers = Router()
router_handlers.include_routers(
    router_repo,
    router_accounts,
    router_warmup,
)
