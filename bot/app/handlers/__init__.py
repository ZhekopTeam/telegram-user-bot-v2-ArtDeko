from aiogram import Router
from .accounts_repo import router_repo
from .accounts_auth import router_accounts
from .warmup_menu import router_warmup_menu
from .warmup_perfect_path import router_warmup_perfect
from .warmup_custom_values import router_warmup_custom
from .warmup_exceptions import router_warmup_exceptions
from .proxy_handlers import router_proxy


router_handlers = Router()
router_handlers.include_routers(
    router_repo,
    router_accounts,
    router_warmup_menu,
    router_warmup_perfect,
    router_warmup_custom,
    router_warmup_exceptions,
    router_proxy,
)
