from aiogram import Router

from .handlers import router_handlers
from utils import CommandPriorityMiddleware


router_main = Router()
router_main.message.middleware(CommandPriorityMiddleware())
router_main.include_routers(router_handlers)
