from aiogram.fsm.state import State, StatesGroup


class RechargeStates(StatesGroup):
    waiting_amount = State()
    waiting_for_receipt = State()


class AdminPriceStates(StatesGroup):
    waiting_for_category_selection = State()
    waiting_for_price = State()


class AdminStates(StatesGroup):
    waiting_for_broadcast_message = State()
    waiting_for_card_number = State()
    waiting_for_card_holder_name = State()
    waiting_recharge_search_user_id = State()
    waiting_recharge_search_username = State()
    waiting_for_add_config_category = State()
    waiting_for_config_list = State()


class AdminServiceStates(StatesGroup):
    adding_config_field = State()
    editing_config_field = State()
    confirming_delete = State()
