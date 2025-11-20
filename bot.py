import telebot
from telebot import types

# Initialize the bot with your token
TOKEN = 'YOUR_BOT_TOKEN_HERE'
bot = telebot.TeleBot(TOKEN)

# User handlers
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "Welcome to the Power Point Break Premium Subscription Store! Please select an option:")

@bot.message_handler(commands=['subscribe'])
def subscribe(message):
    bot.reply_to(message, "You have chosen to subscribe!")

# Admin handlers
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if message.from_user.id == YOUR_ADMIN_ID:
        bot.reply_to(message, "Welcome to the admin panel!")
    else:
        bot.reply_to(message, "You do not have permission to access this.")

# Launch the bot
if __name__ == '__main__':
    bot.polling()