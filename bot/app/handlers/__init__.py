from aiogram import Router
from .accounts_repo import router_repo
from .accounts_auth import router_accounts
from .accounts_warmup_menu import router_warmup_menu
from .accounts_warmup_create import router_warmup_create
from .proxy_handlers import router_proxy


router_handlers = Router()
router_handlers.include_routers(
    router_repo,
    router_accounts,
    router_warmup_menu,
    router_warmup_create,
    router_proxy,
)
