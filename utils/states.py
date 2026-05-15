from aiogram.fsm.state import State, StatesGroup


class RechargeStates(StatesGroup):
    waiting_for_receipt = State()


class AdminRechargeStates(StatesGroup):
    waiting_for_amount = State()
