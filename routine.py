import logging
from datetime import datetime, timedelta
import telebot
import schedule
import time
import firebase_admin
from firebase_admin import credentials, db
import gspread
from google.oauth2.service_account import Credentials
import re
from firebase_admin import db
from data import date_room_mapping, detailed_data_about_rooms, last_day, BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)
database_url ="https://blockdata-571c1-default-rtdb.firebaseio.com/"
sheet_id = "YOUR_GOOGLE_SHEET_ID"
if not firebase_admin._apps:
    firebase_admin.initialize_app(firebase_admin.credentials.Certificate("firebase-credentials.json"), {
        'databaseURL': database_url
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

# floor_to_id = {
#     7: -4587258038,
#     8: -4556356989,
#     9: -4596807609,
#     10: -4568781043,
#     11: -4570610201,
#     12: -4531773164,
# }
# times_to_sent = ["04:00", "13:10", "16:00", "18:00"]
times_to_sent = ["04:00", "16:00"]
time_to_parse = "07:00"
day_index_to_word = {
    -1: "вчера",
    0: "на сегодня",
    1: "на завтра"
}

report_user_id = 6619752978
group_id = -1002154655921
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
def list_to_str(user_list, symbol =', '):
    return symbol.join(map(str, user_list))
def format_date(date) -> str:
    return date.strftime("%d_%m_%Y")

def get_duty_room(floor: int, date: str) -> str:
    ref = db.reference(f"{floor} этаж/{date}")
    duty_room = ref.get()
    return duty_room

def send_reminder(floor: int, reminder_number: int, report: list):
    chat_id = floor_to_id.get(floor)
    if not chat_id:
        report.append(f"Floor {floor}: No chat ID found")
        return

    today = format_date(datetime.today())
    duty_room = get_duty_room(floor, today)

    try:
        if floor == 11:
            generate_message_about_duty_list(arg=reminder_number, delta_day=0, send_to=chat_id)
            report.append(f"Floor {floor}: Special reminder format sent for 11th floor to chat ID {chat_id}")
        elif duty_room:
            reminder_message = (
                # f"❗️ Важное напоминание от Нурдаулет Калдарбек 1221 ❗️\n 🚪Дежурная комната на сегодня: {duty_room}"
                # if reminder_number == 4 else
                f"❗️ Важное напоминание #{reminder_number} ❗️\n 🚪Дежурная комната на сегодня: {duty_room}"
            )
            bot.send_message(chat_id, reminder_message)
            report.append(f"Floor {floor}: Reminder #{reminder_number} sent successfully.")
        else:
            report.append(f"Floor {floor}: No duty room information found for {today}")

    except Exception as e:
        error_message = f"Error sending reminder to floor {floor}: {e}"
        logging.error(error_message)
        report.append(error_message)
        bot.send_message(report_user_id, f"⚠️ {error_message}")

def send_daily_reminders(arg=1):
    floors = [2, 5,6, 7, 8, 9, 10, 11, 12]
    exception_floors = [7]
    # floors = [5]
    report = [f"Report for Reminder #{arg}:\n"]
    for floor in floors:
        if floor in exception_floors and arg != 1:
            pass
        else:
            send_reminder(floor, arg, report)
    return report

def generate_message_about_duty_list(arg, delta_day=0, send_to=group_id):
    date = (datetime.now() + timedelta(days=delta_day)).strftime("%d.%m")
    list_of_rooms_on_duty = date_room_mapping.get(date)

    if delta_day not in [-1, 1]:
        message = '❗ Важное напоминание '
        message += f"от @{arg}❗\n\n" if isinstance(arg, str) else f"#{arg}❗\n\n"

        if date == last_day:
            message = '❗ Последний день ❗\n\n' + message
    else:
        message = ''

    if isinstance(list_of_rooms_on_duty, list):
        message += f"🚪 Дежурные комнаты {day_index_to_word[delta_day]} ({date}): {list_to_str(list_of_rooms_on_duty)}\n"
        for room in list_of_rooms_on_duty:
            message += f"🙍‍♂️ {list_to_str(detailed_data_about_rooms[room]['do_use'])} ({room})\n"
    else:
        room = list_of_rooms_on_duty
        message += f'🚪 Дежурная комната {day_index_to_word[delta_day]} ({date}): {str(room)}\n🙍‍♂️ {list_to_str(detailed_data_about_rooms[room]["do_use"])}'

    bot.send_message(send_to, message)

def schedule_reminders():
    for index, time in enumerate(times_to_sent, start=1):
        schedule.every().day.at(time).do(send_reminders_and_report, index)
    schedule.every().day.at(time_to_parse).do(parse_data_from_sheets_to_firebase)

def send_reminders_and_report(arg):
    report_messages = send_daily_reminders(arg=arg)
    report = "\n>>> ".join(report_messages)
    print(report)
    bot.send_message(report_user_id, report.replace(">>>", ""))

def run_scheduled_tasks():
    while True:
        schedule.run_pending()
        time.sleep(1)
def init_google_sheets():
    google_sheets_creds = Credentials.from_service_account_file("google-credentials.json", scopes=["https://www.googleapis.com/auth/spreadsheets"])
    client = gspread.authorize(google_sheets_creds)
    return client

def init_firebase():
    # firebase_creds = credentials.Certificate("firebase-credentials.json")
    firebase_admin.get_app()
    return db

def is_valid_key(key):
    return bool(key) and not re.search(r'[.$#[\]/]', key)

def parse_sheet_data(sheet):
    data = sheet.get_all_values()[1:]
    floors_data = {}
    
    floor_column_mapping = {
        3: "12 этаж",
        4: "10 этаж",
        5: "9 этаж",
        6: "8 этаж",
        7: "7 этаж",
        9: "6 этаж",
        10: "5 этаж",
        13: "2 этаж",

    }

    for row in data:
        date = row[1].replace('.', '_') 
        if not is_valid_key(date):
            continue 

        for col_idx, room_number in enumerate(row[3:], start=3):
            floor = floor_column_mapping.get(col_idx)
            if floor and is_valid_key(floor) and is_valid_key(room_number):
                if floor not in floors_data:
                    floors_data[floor] = {}
                floors_data[floor][date] = room_number
    
    return floors_data

def upload_to_firebase(db, floors_data):
    if not floors_data:
        print("No data to upload to Firebase.")
        return
    
    ref = db.reference('/')
    ref.set(floors_data)
    print("Data uploaded to Firebase successfully.")
    bot.send_message(report_user_id, "Data has been successfully updated in Firebase")

def parse_data_from_sheets_to_firebase():
    google_client = init_google_sheets()
    db_client = init_firebase()
    spreadsheet = google_client.open_by_key(sheet_id)
    sheet = spreadsheet.worksheet("Sheet6")
    floors_data = parse_sheet_data(sheet)
    upload_to_firebase(db_client, floors_data)

if __name__ == '__main__':
    schedule_reminders()
    print("✔ Tasks are scheduled")
    run_scheduled_tasks()