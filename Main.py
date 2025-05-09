import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import sqlite3
import re
import threading
import time
from datetime import datetime, timedelta
import os
import time
import speech_recognition as sr
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]


TOKEN = "7775736653:AAE2wPWW_i_azWNzj-ShBP9F7hDbKdwha-U"
bot = telebot.TeleBot(TOKEN)

# Подключение к БД и создание таблицы, если её нет
def init_db():
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    # Создаём таблицу с нужными колонками сразу
    cur.execute('''
        CREATE TABLE IF NOT EXISTS schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            event_time TEXT NOT NULL,
            event_day TEXT NOT NULL,
            event_location TEXT NOT NULL
        )
    ''')

    conn.commit()
    conn.close()

init_db()

# Дни недели на русском
DAYS_RU = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

# Функция для выхода назад
def go_back(message):
    bot.send_message(message.chat.id, "🔙 Отменено. Возвращаюсь в главное меню.", reply_markup=main_menu())

# Главное меню
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("➕ Добавить расписание"))
    markup.add(KeyboardButton("📅 Посмотреть расписание"))
    markup.add(KeyboardButton("✏️ Редактировать расписание"))
    markup.add(KeyboardButton("🗑 Удалить расписание"))
    return markup

@bot.message_handler(commands=["start"])
def start(message):
    bot.send_message(message.chat.id, "🔑 Введите пароль для входа:")
    bot.register_next_step_handler(message, check_password)

# Проверка пароля
def check_password(message):
    if message.text == "1234":
        bot.send_message(message.chat.id, f"✅ Добро пожаловать, {message.from_user.first_name}!", reply_markup=main_menu())
    else:
        bot.send_message(message.chat.id, "❌ Неверный пароль! Попробуйте снова.")
        bot.register_next_step_handler(message, check_password)

# Добавление события
@bot.message_handler(func=lambda message: message.text == "➕ Добавить расписание")
def add_schedule(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("🔙 Назад"))  #
    bot.send_message(message.chat.id, "📝 Введите название события или нажмите '🔙 Назад':", reply_markup=markup)
    bot.register_next_step_handler(message, get_event_day)


def get_event_day(message):
    if message.text == "🔙 Назад":  # Если пользователь нажал "Назад"
        go_back(message)
        return

    event_name = message.text.strip()
    bot.send_message(message.chat.id, "📅 Введите день недели (например, 'Понедельник'):")
    bot.register_next_step_handler(message, get_event_location, event_name)

def get_event_location(message, event_name):
    if message.text == "🔙 Назад":
        go_back(message)
        return

    event_day = message.text.strip()
    bot.send_message(message.chat.id, "📍 Введите место проведения (например, ГУК 533):")
    bot.register_next_step_handler(message, get_event_time, event_name, event_day)

def get_event_time(message, event_name, event_day):
    if message.text == "🔙 Назад":
        go_back(message)
        return

    event_location = message.text.strip()
    bot.send_message(message.chat.id, "⏰ Введите время события (например, 12:30):")
    bot.register_next_step_handler(message, save_schedule, event_name, event_day, event_location)

def add_to_google_calendar(event_name, day_str, time_str, location):
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)

    # Преобразуем день и время в datetime
    now = datetime.now()
    days_map = {
        "Пн": 0, "Вт": 1, "Ср": 2, "Чт": 3, "Пт": 4, "Сб": 5, "Вс": 6,
        "Понедельник": 0, "Вторник": 1, "Среда": 2, "Четверг": 3, "Пятница": 4, "Суббота": 5, "Воскресенье": 6
    }
    weekday_target = days_map.get(day_str, 0)
    days_ahead = (weekday_target - now.weekday()) % 7
    event_date = now + timedelta(days=days_ahead)

    event_datetime = datetime.strptime(f"{event_date.date()} {time_str}", "%Y-%m-%d %H:%M")
    end_datetime = event_datetime + timedelta(hours=1)

    event = {
        "summary": event_name,
        "location": location,
        "start": {
            "dateTime": event_datetime.isoformat(),
            "timeZone": "Asia/Almaty",  # Заменить при необходимости
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": "Asia/Almaty",
        },
    }

    event = service.events().insert(calendarId="primary", body=event).execute()
    print("🗓 Событие добавлено в Google Календарь:", event.get("htmlLink"))

def save_schedule(message, event_name, event_day, event_location):
    if message.text == "🔙 Назад":
        go_back(message)
        return

    user_id = message.chat.id
    time_str = message.text.strip()

    if not re.match(r"^\d{1,2}:\d{2}$", time_str):
        bot.send_message(user_id, "⚠️ Неверный формат времени! Введите так: '12:30'. Попробуйте снова.")
        bot.register_next_step_handler(message, lambda msg: save_schedule(msg, event_name, event_day, event_location))
        return

    # Проверка диапазона времени
    hours, minutes = map(int, time_str.split(":"))
    if hours > 23 or minutes > 59:
        bot.send_message(user_id, "⚠️ Неверное значение времени! Часы должны быть от 0 до 23, минуты — от 0 до 59.")
        bot.register_next_step_handler(message, lambda msg: save_schedule(msg, event_name, event_day, event_location))
        return

    # ✅ Всё правильно, записываем в БД
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO schedule (user_id, event, event_time, event_day, event_location) VALUES (?, ?, ?, ?, ?)",
                (user_id, event_name, time_str, event_day, event_location))
    conn.commit()
    conn.close()

    bot.send_message(user_id, f"✅ Событие добавлено: {event_name} в {time_str}, {event_day}, {event_location}", reply_markup=main_menu())
    try:
        add_to_google_calendar(event_name, event_day, time_str, event_location)
        bot.send_message(user_id, "🗓 Событие также добавлено в ваш Google Календарь.")
    except Exception as e:
        bot.send_message(user_id, f"⚠️ Не удалось добавить в Google Календарь: {e}")



# Просмотр расписания
@bot.message_handler(func=lambda message: message.text == "📅 Посмотреть расписание")
def view_schedule(message):
    user_id = message.chat.id

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        "SELECT event, event_day, event_time, event_location FROM schedule WHERE user_id = ? ORDER BY event_day, event_time",
        (user_id,))
    events = cur.fetchall()
    conn.close()

    if events:
        response = "📅 Ваше расписание:\n"
        for event, day, time_str, location in events:
            response += f"➡ {event} ({day}) в {time_str}, {location}\n"
    else:
        response = "📭 Ваше расписание пусто."

    bot.send_message(user_id, response, reply_markup=main_menu())

# Удаление события
@bot.message_handler(func=lambda message: message.text == "🗑 Удалить расписание")
def delete_schedule(message):
    user_id = message.chat.id

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, event, event_day, event_time, event_location FROM schedule WHERE user_id = ?", (user_id,))
    events = cur.fetchall()
    conn.close()

    if not events:
        bot.send_message(user_id, "📭 У вас нет событий для удаления.", reply_markup=main_menu())
        return

    response = "🗑 Выберите номер события для удаления или нажмите '🔙 Назад':\n"
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for event in events:
        markup.add(KeyboardButton(str(event[0])))  # Кнопки с номерами
    markup.add(KeyboardButton("🔙 Назад"))
    bot.send_message(user_id, response, reply_markup=markup)
    bot.register_next_step_handler(message, confirm_delete)

def confirm_delete(message):
    if message.text == "🔙 Назад":  # 🛑 Если нажата кнопка "Назад"
        go_back(message)  # 🔙 Возвращаем пользователя в главное меню
        return
    user_id = message.chat.id
    event_id = message.text

    if not event_id.isdigit():
        bot.send_message(user_id, "⚠️ Введите число!", reply_markup=main_menu())

        return

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM schedule WHERE id = ? AND user_id = ?", (event_id, user_id))
    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ Событие удалено!", reply_markup=main_menu())

# Редактирование события
@bot.message_handler(func=lambda message: message.text == "✏️ Редактировать расписание")
def edit_schedule(message):
    user_id = message.chat.id

    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute("SELECT id, event, event_day, event_time, event_location FROM schedule WHERE user_id = ?", (user_id,))
    events = cur.fetchall()
    conn.close()

    if not events:
        bot.send_message(user_id, "📭 У вас нет событий для редактирования.", reply_markup=main_menu())
        return

    response = "✏️ Выберите номер события для редактирования или нажмите '🔙 Назад':\n"
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for event in events:
        markup.add(KeyboardButton(str(event[0])))  # Кнопки с номерами
    markup.add(KeyboardButton("🔙 Назад"))  # 🔥 ДОБАВИЛИ КНОПКУ "НАЗАД"
    bot.send_message(user_id, response, reply_markup=markup)
    bot.register_next_step_handler(message, ask_new_event)

def ask_new_event(message):
    if message.text == "🔙 Назад":
        go_back(message)
        return
    user_id = message.chat.id
    event_id = message.text

    if not event_id.isdigit():
        bot.send_message(user_id, "⚠️ Введите число!", reply_markup=main_menu())
        return

    bot.send_message(user_id, "📝 Введите новое событие в формате:\n'Название День(Пн/Вт/Ср) Время(14:00) Место'\nПример: 'Лекция по NoSQL Ср 15:25 ГУК 535'")
    bot.register_next_step_handler(message, lambda msg: update_schedule(msg, event_id))

def update_schedule(message, event_id):
    user_id = message.chat.id
    text = message.text.strip()

    # Проверяем формат ввода (разрешены полные названия дней недели)
    match = re.match(
        r"(.+?)\s+(Пн|Вт|Ср|Чт|Пт|Сб|Вс|Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье)\s+(\d{1,2}:\d{2})\s+(.+)",
        text)
    if not match:
        bot.send_message(user_id, "⚠️ Некорректный формат! Используйте: 'Название День(Пн/Вт/Ср) Время(14:00) Место'")
        return

    event, day, time_str, location = match.groups()

    # Обновляем запись в БД
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()
    cur.execute(
        "UPDATE schedule SET event = ?, event_day = ?, event_time = ?, event_location = ? WHERE id = ? AND user_id = ?",
        (event, day, time_str, location, event_id, user_id))

    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ Событие обновлено!", reply_markup=main_menu())

# Напоминания
def reminder():
    days_map = {
        "Monday": "Понедельник",
        "Tuesday": "Вторник",
        "Wednesday": "Среда",
        "Thursday": "Четверг",
        "Friday": "Пятница",
        "Saturday": "Суббота",
        "Sunday": "Воскресенье"
    }

    while True:
        now = datetime.now()
        current_day = days_map[now.strftime("%A")]  # Переводим день недели на русский
        reminder_time = (now + timedelta(minutes=15)).strftime("%H:%M")

        conn = sqlite3.connect("database.db")
        cur = conn.cursor()
        cur.execute("SELECT user_id, event, event_location FROM schedule WHERE event_day = ? AND event_time = ?",
                    (current_day, reminder_time))
        events = cur.fetchall()
        conn.close()

        for user_id, event, loc in events:
            bot.send_message(user_id, f"🔔 Напоминание: через 15 минут {event} в {loc}!")

        time.sleep(60)


# Запускаем напоминания в отдельном потоке
threading.Thread(target=reminder, daemon=True).start()



# Запуск бота
if __name__ == "__main__":

    print("✅ Бот запущен!")


    @bot.message_handler(content_types=["voice"])
    def handle_voice(message):
        try:
            # 1. Получаем голосовое сообщение
            file_info = bot.get_file(message.voice.file_id)
            downloaded_file = bot.download_file(file_info.file_path)

            # 2. Сохраняем как OGG
            ogg_filename = f"voice_{message.chat.id}.ogg"
            wav_filename = f"voice_{message.chat.id}.wav"

            with open(ogg_filename, "wb") as f:
                f.write(downloaded_file)

            # 3. Конвертируем OGG в WAV с явным указанием пути к ffmpeg
            os.system(r'"C:\ProgramData\chocolatey\bin\ffmpeg.exe" -i {} {} -y'.format(ogg_filename, wav_filename))

            # 🔹 Пауза 1 секунда, чтобы ffmpeg успел обработать файл
            time.sleep(1)

            # 4. Проверяем, создался ли файл WAV
            if not os.path.exists(wav_filename):
                bot.send_message(message.chat.id, "⚠ Ошибка: не удалось создать аудиофайл. Попробуйте снова.")
                return

            # 5. Распознаём речь
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_filename) as source:
                audio = recognizer.record(source)
                text = recognizer.recognize_google(audio, language="ru-RU")

            # 🔹 Попытка извлечь данные события из текста
            match = re.match(
                r"(.+?)\s+(Пн|Вт|Ср|Чт|Пт|Сб|Вс|Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье)\s+(\d{1,2}:\d{2})\s+(.+)",
                text,
                re.IGNORECASE
            )

            if match:
                event, day, time_str, location = match.groups()
                day = day.capitalize()

                conn = sqlite3.connect("database.db")
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO schedule (user_id, event, event_time, event_day, event_location) VALUES (?, ?, ?, ?, ?)",
                    (message.chat.id, event, time_str, day, location))
                conn.commit()
                conn.close()

                bot.send_message(message.chat.id,
                                 f"✅ Событие добавлено: {event} в {time_str}, {day}, {location}",
                                 reply_markup=main_menu())
            else:
                bot.send_message(message.chat.id,
                                 "⚠️ Неверный формат! Используйте: 'Название День(Пн/Вт/Ср) Время(14:00) Место'")

            # 6. Отправляем текст пользователю
            bot.send_message(message.chat.id, f"🎙 Распознано: {text}")

        except sr.UnknownValueError:
            bot.send_message(message.chat.id, "⚠ Голосовое сообщение не распознано.")
        except Exception as e:
            bot.send_message(message.chat.id, f"⚠ Ошибка обработки голосового сообщения: {e}")

        finally:
            # 7. Удаляем файлы после обработки
            if os.path.exists(ogg_filename):
                os.remove(ogg_filename)
            if os.path.exists(wav_filename):
                os.remove(wav_filename)

    bot.polling(none_stop=True)
