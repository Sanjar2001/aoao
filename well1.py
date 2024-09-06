from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio
from openai import OpenAI
import csv
import os
import tiktoken
from aiogram.methods import DeleteWebhook

# Установите свой API-ключ OpenAI
client = OpenAI(api_key='')

# Инициализация бота и диспетчера
TOKEN = ""
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()

# Определение состояний
class UserStates(StatesGroup):
    chat = State()
    register = State()

# Функция для подсчета токенов
def num_tokens_from_string(string: str, model_name: str) -> int:
    encoding = tiktoken.encoding_for_model(model_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

# Функция для проверки регистрации пользователя
def is_user_registered(user_id):
    with open('users.csv', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0] == str(user_id):
                return True
    return False

# Функция для регистрации пользователя
def register_user(user_id):
    with open('users.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([user_id, 500, 500, 0])  # user_id, token_capacity, context_capacity, used_tokens

# Функция для получения данных пользователя
def get_user_data(user_id):
    with open('users.csv', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0] == str(user_id):
                return row
    return None

# Функция для обновления данных пользователя
def update_user_data(user_id, token_capacity, context_capacity, used_tokens):
    rows = []
    with open('users.csv', 'r') as f:
        reader = csv.reader(f)
        for row in reader:
            if row[0] == str(user_id):
                row = [user_id, token_capacity, context_capacity, used_tokens]
            rows.append(row)
    
    with open('users.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)

# Функция для получения ответа от GPT-4
def get_chatgpt_response(messages):
    response = client.chat.completions.create(
        model="gpt-4",
        messages=messages
    )
    return response.choices[0].message.content

# Обработчик команды /start
@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.set_state(UserStates.register)
    await message.answer("Для регистрации введите 'register':")

# Обработчик регистрации
@router.message(UserStates.register)
async def register_handler(message: Message, state: FSMContext) -> None:
    if message.text.lower() == 'register':
        if not is_user_registered(message.from_user.id):
            register_user(message.from_user.id)
            await state.set_state(UserStates.chat)
            await state.update_data(messages=[{"role": "system", "content": "Ты - пиратский помощник. Отвечай как настоящий пират!"}])
            await message.answer("Вы успешно зарегистрированы! Начните общение с ChatGPT (введите 'exit', чтобы выйти):")
        else:
            await message.answer("Вы уже зарегистрированы. Начните общение с ChatGPT (введите 'exit', чтобы выйти):")
            await state.set_state(UserStates.chat)
    else:
        await message.answer("Для регистрации введите 'register':")

# Обработчик сообщений
@router.message(UserStates.chat)
async def chat_handler(message: Message, state: FSMContext) -> None:
    if not is_user_registered(message.from_user.id):
        await message.answer("Вы не зарегистрированы. Введите /start для регистрации.")
        return

    if message.text.lower() == 'exit':
        await state.clear()
        await message.answer("Чат завершен.")
        return

    if message.text.lower() == 'tokens':
        await get_tokens(message)
        return

    if message.text.lower() == 'clean':
        await clean_context(message, state)
        return

    user_data = get_user_data(message.from_user.id)
    token_capacity = int(user_data[1])
    context_capacity = int(user_data[2])
    used_tokens = int(user_data[3])

    if len(message.text) > context_capacity:
        await message.answer(f"Ваше сообщение превышает лимит в {context_capacity} символов.")
        return

    data = await state.get_data()
    messages = data.get("messages", [{"role": "system", "content": "Ты - пиратский помощник. Отвечай как настоящий пират!"}])

    new_tokens = num_tokens_from_string(message.text, "gpt-4")
    if used_tokens + new_tokens > token_capacity:
        await message.answer(f"У вас закончился лимит токенов. Используйте команду 'tokens' для сброса.")
        return

    messages.append({"role": "user", "content": message.text})
    response = get_chatgpt_response(messages)
    messages.append({"role": "assistant", "content": response})

    used_tokens += new_tokens + num_tokens_from_string(response, "gpt-4")
    update_user_data(message.from_user.id, token_capacity, context_capacity, used_tokens)

    await state.update_data(messages=messages)
    await message.answer(response)

# Функция для обнуления счетчика токенов
async def get_tokens(message: Message):
    user_data = get_user_data(message.from_user.id)
    update_user_data(message.from_user.id, user_data[1], user_data[2], 0)
    await message.answer("Счетчик токенов обнулен.")

# Функция для очистки контекста беседы
async def clean_context(message: Message, state: FSMContext):
    await state.update_data(messages=[{"role": "system", "content": "Ты - пиратский помощник. Отвечай как настоящий пират!"}])
    await message.answer("Контекст беседы очищен.")

# Запуск поллинга
async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())