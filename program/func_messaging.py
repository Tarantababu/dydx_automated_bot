import requests
from decouple import config

# Send Message
def send_message(message):
    bot_token = config("TELEGRAM_TOKEN")
    chat_id = config("TELEGRAM_CHAT_ID")
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text={message}"
    try:
        res = requests.get(url)
        res.raise_for_status()  # Raise an HTTPError for bad responses
        if res.status_code == 200:
            return "sent"
        else:
            print(f"Telegram API responded with status code {res.status_code}")
            return "failed"
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return "failed"
