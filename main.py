import os
import datetime
import telebot
from telebot import types
import firebase_admin
from firebase_admin import db
from typing import Optional
import re
from data import *
from routine import generate_message_about_duty_list
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

bot_token = BOT_TOKEN
if bot_token is None:
    raise ValueError("The TELEGRAM_BOT_TOKEN environment variable is not set.")

bot = telebot.TeleBot(bot_token)

if not firebase_admin._apps:
    firebase_admin.initialize_app(firebase_admin.credentials.Certificate("firebase-credentials.json"), {
        'databaseURL': "https://blockdata-571c1-default-rtdb.firebaseio.com/"
    })

floor_to_id = {
    2: -1002147892404,
    5: -1002172860504,
    6: -1002179413916,
    7: -1002227237407,
    8: -1002160562240,
    9: -1002156565372,
    10: -1002249105748,
    11: -1002154655921,
    12: -1002245502557,
}

def get_floor_by_chat_id(chat_id: int) -> Optional[int]:
    for floor, id in floor_to_id.items():
        if id == chat_id:
            return floor
    return None

def format_date(date: datetime.date) -> str:
    return date.strftime("%d_%m_%Y")

def get_duty_room(floor: int, date: str) -> Optional[str]:
    ref = db.reference(f"{floor} этаж/{date}")
    duty_room = ref.get()
    return duty_room

def get_schedule(floor: int) -> Optional[dict]:
    ref = db.reference(f"{floor} этаж")
    schedule = ref.get()
    return schedule

def generate_main_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("Список дежурств", callback_data="schedule"))
    keyboard.add(InlineKeyboardButton("Дежурные на сегодня", callback_data="today"))
    keyboard.add(InlineKeyboardButton("Пред. дежурные", callback_data="yesterday"))
    keyboard.add(InlineKeyboardButton("След. дежурные", callback_data="tomorrow"))
    return keyboard

@bot.message_handler(commands=['start', 'bot'])
def send_welcome(message):
    floor = get_floor_by_chat_id(message.chat.id)
    if floor == 11:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Список дежурств", callback_data="see_all_details"))
        markup.add(InlineKeyboardButton("Дежурные на сегодня", callback_data="see_today_details"))
        markup.add(InlineKeyboardButton("Пред. дежурные", callback_data="see_prev_details"))
        markup.add(InlineKeyboardButton("След. дежурные", callback_data="see_next_details"))
        bot.send_message(message.chat.id, "Выберите задачу:", reply_markup=markup)

    else:
        bot.reply_to(message, "Выберите задачу:", reply_markup=generate_main_menu())
        print(message.chat.id)

# Handler for button presses
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    floor = get_floor_by_chat_id(chat_id)
    username = call.from_user.username or call.from_user.first_name

    if floor is None:
        bot.send_message(chat_id, "Эта группа не поддерживается для дежурного бота.")
        return

    if floor == 11:
        if call.data == "see_all_details":
            send_full_schedule(call.message)
        elif call.data == "see_today_details":
            generate_message_about_duty_list(arg=username, delta_day=0, send_to=call.message.chat.id)
        elif call.data == "see_prev_details":
            generate_message_about_duty_list(arg=username, delta_day=-1, send_to=call.message.chat.id)
        elif call.data == "see_next_details":
            generate_message_about_duty_list(arg=username, delta_day=1, send_to=call.message.chat.id)
        else:
            if re.match(r"see_room_details_\d{4}", call.data):
                room_number = int(call.data.split('_')[-1])
                answer, markup = generate_answer(room_number, is_nested=True)
                bot.send_message(call.message.chat.id, f"@{username}\n" + answer, reply_markup=markup)

    else:
        if call.data == "schedule":
            send_schedule(call.message, floor, username)
        elif call.data == "today":
            send_today_duty(call.message, floor, username)
        elif call.data == "yesterday":
            send_yesterday_duty(call.message, floor, username)
        elif call.data == "tomorrow":
            send_tomorrow_duty(call.message, floor, username)

def send_full_schedule(message):
    today_str = datetime.date.today().strftime("%d.%m")
    sorted_schedule = sorted(date_room_mapping.items(), key=lambda x: datetime.datetime.strptime(x[0], "%d.%m"))
    answer = ""
    for date_str, rooms in sorted_schedule:
        today_marker = " ❗️(сегодня)" if date_str == today_str else ""
        if isinstance(rooms, int):
            answer += f"{date_str}{today_marker}: {rooms} ({len(detailed_data_about_rooms[rooms]['do_use'])})\n"
        elif isinstance(rooms, list):
            count_array = [len(detailed_data_about_rooms[room]['do_use']) for room in rooms]
            answer += f"{date_str}{today_marker}: {list_to_str(rooms)} ({list_to_str(count_array, symbol='+')})\n"
    bot.send_message(message.chat.id, answer)

def generate_answer(room_number, is_nested=False):
    data_to_proceed = detailed_data_about_rooms[int(room_number)]
    do_use = data_to_proceed['do_use']
    do_not_use = data_to_proceed['do_not_use']
    duty_date = ''
    duty_helpers = []

    for key in date_room_mapping.keys():
        if date_room_mapping[key] == room_number:
            duty_date = key
        elif isinstance(date_room_mapping[key], list) and room_number in date_room_mapping[key]:
            duty_date = key
            duty_helpers = [room for room in date_room_mapping[key] if room != room_number]
            duty_date += f"\nСовместно с {list_to_str(duty_helpers)}"

    answer = f"Информация по комнате {room_number}:\n" \
             f"Список всех жителей: {list_to_str(do_use + do_not_use)}\n" \
             f"Используют кухню: {list_to_str(do_use)}\n" \
             f"Не используют кухню: {list_to_str(do_not_use)}\n\n" \
             f"День уборки: {duty_date}"

    if duty_helpers and not is_nested:
        markup = InlineKeyboardMarkup()
        for room in duty_helpers:
            markup.add(InlineKeyboardButton(text=f"Подробности о {room}", callback_data=f"see_room_details_{room}"))
        return answer, markup

    return answer, None

# Functions for other floors (general logic)
def send_today_duty(message, floor, username):
    today = datetime.date.today()
    formatted_date = format_date(today)
    duty_room = get_duty_room(floor, formatted_date)
    if duty_room:
        bot.send_message(message.chat.id, f"Requested by @{username}\n❗ Дежурная комната на сегодня ({today.strftime('%d.%m')}): {duty_room} ❗")
    else:
        bot.send_message(message.chat.id, f"Requested by @{username}\nСегодня нет информации о дежурных комнатах.")

def send_tomorrow_duty(message, floor, username):
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    formatted_date = format_date(tomorrow)
    duty_room = get_duty_room(floor, formatted_date)
    if duty_room:
        bot.send_message(message.chat.id, f"Requested by @{username}\nДежурная комната на завтра ({tomorrow.strftime('%d.%m')}): {duty_room}")
    else:
        bot.send_message(message.chat.id, f"Requested by @{username}\nЗавтра нет информации о дежурных комнатах.")

def send_yesterday_duty(message, floor, username):
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    formatted_date = format_date(yesterday)
    duty_room = get_duty_room(floor, formatted_date)
    if duty_room:
        bot.send_message(message.chat.id, f"Requested by @{username}\nДежурная комната на вчера ({yesterday.strftime('%d.%m')}): {duty_room}")
    else:
        bot.send_message(message.chat.id, f"Requested by @{username}\nВчера не было информации о дежурных комнатах.")

def send_schedule(message, floor, username):
    today_str = datetime.date.today().strftime("%d_%m_%Y")
    schedule = get_schedule(floor)
    if schedule:
        sorted_schedule = sorted(schedule.items(), key=lambda x: datetime.datetime.strptime(x[0], "%d_%m_%Y"))
        message_text = f"Requested by @{username}\nГрафик дежурств для {floor} этажа:\n"
        for date, room in sorted_schedule:
            formatted_date = datetime.datetime.strptime(date, "%d_%m_%Y").strftime("%d.%m")
            today_marker = " ❗️(сегодня)" if date == today_str else ""
            message_text += f"{formatted_date}{today_marker}: Комната {room}\n"
        bot.send_message(message.chat.id, message_text)
    else:
        bot.send_message(message.chat.id, f"Requested by @{username}\nГрафик дежурств не найден для этого этажа.")
@bot.message_handler(func=lambda message: re.match(r"\d{4}",message.text ))
def handle_room_number(message):
    room_number = message.text
    username = message.from_user.username or message.from_user.first_name

    if room_number.isdigit() and int(room_number) in range(1101, 1129):
        answer, markup = generate_answer(int(room_number))
        bot.send_message(message.chat.id, answer, reply_markup=markup)
# Start the bot
if __name__ == "__main__":
    print("Bot is running...")
    bot.polling()
