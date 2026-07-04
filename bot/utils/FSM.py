from aiogram.fsm.state import StatesGroup, State


class AddAccount(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()


class AddWarmup(StatesGroup):
    waiting_name = State()
    waiting_accounts = State()
    waiting_start_date = State()
    waiting_end_date = State()
    waiting_proxy = State()
    waiting_confirm = State()
    waiting_edit = State()
    waiting_edit_start_date = State()
    waiting_edit_end_date = State()
    waiting_edit_days = State()
    waiting_extend_days = State()



class AddProxy(StatesGroup):
    waiting_proxy_input = State()
