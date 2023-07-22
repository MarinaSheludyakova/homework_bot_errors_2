import logging
import os
import sys
import time

from dotenv import load_dotenv

import requests

import telegram


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


def set_logging():
    """Настройки логирования."""
    logging.basicConfig(
        level=logging.DEBUG,
        filename='main.log',
        filemode='a',
        format=(
            '%(asctime)s [%(levelname)s] | '
            '(%(filename)s).%(funcName)s:%(lineno)d | %(message)s'
        ),
    )
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    return logger


logger = set_logging()


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


error_state = ''


def send_error_state(error_message):
    """
    Отправляет состояние домашней работы в Telegram чат.

    Перезаписывает предыдущее значение состояния.
    Отправляет новое состояние, если оно отличается от предыдущего.
    """
    global error_state
    if error_message != error_state:
        bot.send_message(TELEGRAM_CHAT_ID, error_message)
        error_state = error_message
        logging.debug(f'Бот отправил сообщение: {error_message}.')


def check_tokens():
    """
    Проверяет доступность переменных окружения.

    Проверяет переменные окружения, необходимые для работы программы.
    Если отсутствует хотя бы одна переменная окружения —
    выбрасывает ошибку SystemExit.
    """
    tokens = {
        PRACTICUM_TOKEN,
        TELEGRAM_TOKEN,
        TELEGRAM_CHAT_ID
    }
    for token in tokens:
        if token is not None and token != '':
            return token
        else:
            message = ('Отсутствует обязательная переменная окружения. '
                       'Программа принудительно остановлена.')
            logg_error_or_critical(logging.critical, message, SystemExit)


def send_message(bot, message):
    """
    Отправляет сообщение в Telegram чат.

    Чат определяется переменной окружения TELEGRAM_CHAT_ID.
    Принимает на вход два параметра:
    экземпляр класса Bot и строку с текстом сообщения.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(f'Бот отправил сообщение: {message}.')
    except Exception as error:
        message = (f'Сбой при отправке сообщения: {error}.')
        logg_error_or_critical(logging.error, message, Exception)


def logg_error_or_critical(level, message, error):
    """
    Обрабатывает ошибки, у которых level равен 'error' или 'critical'.

    Добавляет логи, отправляет сообщения в Telegram чат, выбрасывает ошибку.
    Все данные передаются из функций, вызывающих эту.
    """
    if level == logging.error:
        logging.error(message)
    if level == logging.critical:
        logging.critical(message)
    send_error_state(message)
    raise error


def get_api_answer(timestamp):
    """
    Делает запрос к эндпоинту API-сервиса.

    В качестве параметра в функцию передается временная метка.
    В случае успешного запроса должна возвращает ответ API,
    приведя его из формата JSON к типам данных Python.

    """
    payload = {'from_date': timestamp}
    try:
        homework_statuses = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=payload
        )
        if homework_statuses.status_code != 200:
            message = ('Полученный код статуса при запросе '
                       'к основному API отличается от "200"')
            logg_error_or_critical(logging.error, message, Exception)
        return homework_statuses.json()
    except Exception as error:
        message = (f'Ошибка при запросе к основному API: {error}')
        logg_error_or_critical(logging.error, message, Exception)


def check_response(response):
    """
    Проверяет ответ API на соответствие документации.

    В качестве параметра функция получает ответ API,
    приведенный к типам данных Python.
    """
    if type(response) != dict:
        message = ('Ошибка: Тип полученных данных в ответе '
                   'не соответсвует ожидаемым "dict".')
        logg_error_or_critical(logging.error, message)
        raise TypeError
    if response.get('code') is not None:
        if response.get('code') == 'not_authenticated':
            message = (f'Ошибка 401. Запроса с недействительным '
                       f'или некорректным токеном: '
                       f'{response.get("message")}.')
        if response.get('code') == 'UnknownError':
            message = (f'Ошибка 400 "UnknownError": '
                       f'{response.get("error")}.')
        else:
            message = (f'При запросе к эндпоинту API вернулся ответ '
                       f'с кодом {response.get("code")}.')
        logg_error_or_critical(logging.error, message)
    else:
        if type(response.get('homeworks')) != list:
            message = ('Ошибка: Тип полученных данных "homeworks" '
                       'не соответсвует ожидаемым "list".')
            logg_error_or_critical(logging.error, message)
            raise TypeError
        if len(response) == 2 and response.get('homeworks') is None:
            message = ('Ошибка: Не получен обязательный ключ из ответа: '
                       'homeworks.')
            logg_error_or_critical(logging.error, message, KeyError)
        if len(response) == 2 and response.get('current_date') is None:
            message = ('Ошибка: Не получен обязательный ключ из ответа: '
                       'current_date.')
            logg_error_or_critical(logging.error, message, KeyError)
        else:
            logging.info('Проверка ответа API на соответствие документации '
                         'прошла успешно.')


def parse_status(homework):
    """
    Извлекает из информации о конкретной домашней работе статус этой работы.

    В качестве параметра функция получает только один элемент
    из списка домашних работ. В случае успеха, функция возвращает
    подготовленную для отправки в Telegram строку, содержащую один
    из вердиктов словаря HOMEWORK_VERDICTS.
    """
    homeworks = homework.get('homeworks')
    try:
        if homeworks == []:
            raise TypeError
        homework_the_first = homeworks[0]
        homework_name = homework_the_first.get('homework_name')
        status = homework_the_first.get('status')
        if status is None or status not in HOMEWORK_VERDICTS or status == '':
            raise ValueError
        else:
            verdict = HOMEWORK_VERDICTS[status]
            message = (f'Изменился статус проверки работы "{homework_name}". '
                        f'{verdict}')
            if type(message) != str:
                message = ('Ошибка: тип возвращаемого объекта "message" '
                           'не равен строке.')
                logg_error_or_critical(logging.error, message, TypeError)
            if type(message) == str:
                return message
    except TypeError:
        raise TypeError
    except ValueError:
        message = ('Ошибка: получен недокументированный статус '
                   'домашней работы "{status}".')
        logg_error_or_critical(logging.error, message, ValueError)


def main():
    """Основная логика работы бота."""
    global bot
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    check_tokens()
    timestamp = int(time.time()) - RETRY_PERIOD
    while True:
        try:
            homework = get_api_answer(timestamp)
            check_response(homework)
            message = parse_status(homework)
            send_message(bot, message)
        except IndexError as info:
            message = (f'Не найдено ни одной сданной домашней работы '
                       f'за период проверки: {info}')
            logging.info(message)
        except TypeError:
            pass
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
#            logging.error(message)
#            send_error_state(bot, message)
            return error
        logging.info(f'Выполнение запроса окончено, следующий повтор '
                     f'через {RETRY_PERIOD} секунд.')
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
