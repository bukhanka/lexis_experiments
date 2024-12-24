import os
import logging
import csv
from typing import Dict, Any
from datetime import datetime
import uuid
import tempfile
import yaml

import telebot
from telebot import types
from dotenv import load_dotenv

# LangChain imports
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

# Whisper API import
import openai

# Load environment variables
load_dotenv()

# Load configuration from YAML file
with open('config.yaml', 'r', encoding='utf-8') as config_file:
    config = yaml.safe_load(config_file)

# Get prompts and messages from config
DEFAULT_SYSTEM_PROMPT = config['default_system_prompt']
CONVERSATION_ANALYSIS_PROMPT = config['conversation_analysis_prompt']
WELCOME_MESSAGE = config['welcome_message']
PROMPT_NOT_SET_MESSAGE = config['prompt_not_set_message']
CHAT_STARTED_MESSAGE = config['chat_started_message']
NO_ACTIVE_CHAT_MESSAGE = config['no_active_chat_message']
CHAT_ENDED_MESSAGE = config['chat_ended_message']
SET_PROMPT_MESSAGE = config['set_prompt_message']
VOICE_INPUT_COMING_SOON = config['voice_input_coming_soon']
ANALYSIS_LLM_PROVIDER = config['analysis_llm_provider']
LLM_PROVIDER = config['llm_provider']

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Initialize Telegram bot
bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))

# Initialize OpenAI client for Whisper
openai_client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Global state to manage user conversations
user_conversations: Dict[int, Dict[str, Any]] = {}

class TelegramChatMemory:
    """Custom chat memory for Telegram conversations"""
    def __init__(self, user_id, system_prompt=None):
        self.user_id = user_id
        self.messages = []
        
        # Add system message at initialization if provided
        if system_prompt:
            self.add_system_message(system_prompt)
    
    def add_user_message(self, message):
        self.messages.append(HumanMessage(content=message))
    
    def add_ai_message(self, message):
        self.messages.append(AIMessage(content=message))
    
    def add_system_message(self, message):
        # Remove any existing system messages first
        self.messages = [msg for msg in self.messages if not isinstance(msg, SystemMessage)]
        self.messages.insert(0, SystemMessage(content=message))
    
    def get_messages(self):
        return self.messages

def create_chat_chain(system_prompt: str = None):
    """Create a LangChain chat chain with configurable system prompt and robust error handling"""
    # Use the provided system prompt, or fall back to DEFAULT_SYSTEM_PROMPT
    prompt_to_use = system_prompt or DEFAULT_SYSTEM_PROMPT
    
    try:
        # Initialize LLM
        if LLM_PROVIDER == "gemini":
            try:
                llm = ChatGoogleGenerativeAI(
                    model="gemini-pro",
                    temperature=0.7,
                    google_api_key=os.getenv('GOOGLE_API_KEY')
                )
            except Exception as gemini_error:
                logging.warning(f"Gemini initialization failed: {gemini_error}")
                llm = ChatOpenAI(
                    model="gpt-4o",
                    temperature=0.7,
                    openai_api_key=os.getenv('OPENAI_API_KEY')
                )
        elif LLM_PROVIDER == "gpt":
            llm = ChatOpenAI(
                model="gpt-4o",
                temperature=0.7,
                openai_api_key=os.getenv('OPENAI_API_KEY')
            )
        else:
            logging.error(f"Неизвестный провайдер LLM: {LLM_PROVIDER}")
            llm = ChatOpenAI(
                model="gpt-4o",
                temperature=0.7,
                openai_api_key=os.getenv('OPENAI_API_KEY')
            )
        
        # Create a function to generate the prompt dynamically
        def create_prompt(system_message):
            return ChatPromptTemplate.from_messages([
                SystemMessage(content=system_message),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}")
            ])
        
        # Create chain with dynamic prompt generation
        chain = create_prompt(prompt_to_use) | llm
        return chain
    
    except Exception as e:
        logging.error(f"Ошибка создания цепочки чата: {e}")
        # Absolute fallback to OpenAI if everything else fails
        try:
            llm = ChatOpenAI(
                model="gpt-4o",
                temperature=0.7,
                openai_api_key=os.getenv('OPENAI_API_KEY')
            )
            
            def create_prompt(system_message):
                return ChatPromptTemplate.from_messages([
                    SystemMessage(content=system_message),
                    MessagesPlaceholder(variable_name="chat_history"),
                    ("human", "{input}")
                ])
            
            chain = create_prompt(prompt_to_use) | llm
            return chain
        except Exception as final_error:
            logging.critical(f"Критическая ошибка создания цепочки чата: {final_error}")
            return None

def reset_user_conversation(user_id: int):
    """Reset user conversation state with unique user tracking"""
    system_prompt = DEFAULT_SYSTEM_PROMPT
    
    if user_id in user_conversations:
        # If user already has a custom system prompt, use that
        system_prompt = user_conversations[user_id].get('system_prompt', DEFAULT_SYSTEM_PROMPT)
    
    user_conversations[user_id] = {
        'user_uuid': str(uuid.uuid4()),  # Add unique user ID
        'memory': TelegramChatMemory(user_id, system_prompt),  # Pass system prompt during initialization
        'chain': create_chat_chain(system_prompt),  # Use the system prompt
        'active': True,
        'rating': None,
        'naturalness_rating': None,
        'system_prompt': system_prompt  # Store the system prompt
    }

def create_main_keyboard():
    """Create main menu keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🎯 Установить промпт")
    markup.row("▶️ Начать диалог", "⏹ Завершить диалог")
    return markup

def create_rating_keyboard():
    """Create inline keyboard for dialog rating"""
    markup = types.InlineKeyboardMarkup()
    successful_btn = types.InlineKeyboardButton("✅ Диалог успешный", callback_data='rating_successful')
    unsuccessful_btn = types.InlineKeyboardButton("❌ Диалог неуспешный", callback_data='rating_unsuccessful')
    markup.row(successful_btn, unsuccessful_btn)
    return markup

def create_naturalness_rating_keyboard():
    """Create inline keyboard for naturalness rating"""
    markup = types.InlineKeyboardMarkup()
    for i in range(1, 6):
        markup.add(types.InlineKeyboardButton(str(i), callback_data=f'naturalness_rating_{i}'))
    return markup

def split_long_message(text, chunk_size=4000):
    """Split a long message into chunks that fit Telegram's limits"""
    return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Handle bot start command"""
    reset_user_conversation(message.from_user.id)
    bot.reply_to(
        message,
        WELCOME_MESSAGE,
        reply_markup=create_main_keyboard()
    )

@bot.message_handler(commands=['check_prompt'])
def check_system_prompt(message):
    """Show current system prompt"""
    user_id = message.from_user.id
    if user_id in user_conversations:
        current_prompt = user_conversations[user_id]['system_prompt']
        bot.reply_to(message, f"Текущий системный промпт:\n{current_prompt}")
    else:
        bot.reply_to(message, PROMPT_NOT_SET_MESSAGE)

@bot.message_handler(commands=['voice_input'])
def voice_input_handler(message):
    """Placeholder for future voice input implementation"""
    bot.reply_to(message, VOICE_INPUT_COMING_SOON)

def rate_conversation_naturalness(conversation_log, system_prompt):
    """Rate conversation naturalness with robust error handling"""
    try:
        # Similar modification as in create_chat_chain
        if ANALYSIS_LLM_PROVIDER == "gemini":
            try:
                llm = ChatGoogleGenerativeAI(
                    model="gemini-pro", 
                    temperature=0.2, 
                    google_api_key=os.getenv('GOOGLE_API_KEY')
                )
            except Exception as gemini_error:
                logging.warning(f"Gemini analysis initialization failed: {gemini_error}")
                llm = ChatOpenAI(
                    model="gpt-4o",
                    temperature=0.2,
                    openai_api_key=os.getenv('OPENAI_API_KEY')
                )
        elif ANALYSIS_LLM_PROVIDER == "gpt":
            llm = ChatOpenAI(
                model="gpt-4o",
                temperature=0.2,
                openai_api_key=os.getenv('OPENAI_API_KEY')
            )
        else:
            logging.error(f"Неизвестный провайдер LLM: {ANALYSIS_LLM_PROVIDER}")
            llm = ChatOpenAI(
                model="gpt-4o",
                temperature=0.2,
                openai_api_key=os.getenv('OPENAI_API_KEY')
            )
        
        # Rest of the function remains the same...
        analysis_prompt = CONVERSATION_ANALYSIS_PROMPT.format(
            conversation_log=conversation_log,
            system_prompt=system_prompt
        )

        response = llm.invoke(analysis_prompt)
        
        # Return the raw response content
        return response.content
    except Exception as e:
        logging.error(f"Ошибка оценки естественности: {e}")
        return "Невозможно оценить естественность разговора"

def log_conversation_to_csv(user_id):
    """Log conversation details to CSV with error handling for naturalness rating"""
    conversation = user_conversations.get(user_id)
    if not conversation:
        return
    
    # Create logs directory
    os.makedirs('logs/llm_experiments', exist_ok=True)
    csv_path = 'logs/llm_experiments/conversations.csv'
    
    # Prepare conversation log for CSV
    conversation_log = "\n".join([
        f"{msg.type.upper()}: {msg.content}" 
        for msg in conversation['memory'].get_messages()
    ])
    
    # Rate conversation naturalness with system prompt
    analysis_result = rate_conversation_naturalness(
        conversation_log,
        conversation['system_prompt']
    )
    
    # CSV headers if file doesn't exist
    csv_exists = os.path.exists(csv_path)
    
    with open(csv_path, 'a', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.writer(csvfile)
        
        if not csv_exists:
            csv_writer.writerow([
                'Timestamp', 'User ID', 'User UUID', 
                'System Prompt', 
                'Naturalness Rating', 'Analysis Result', 'Conversation Log'
            ])
        
        csv_writer.writerow([
            datetime.now().isoformat(),
            user_id,
            conversation['user_uuid'],
            conversation['system_prompt'],
            conversation['naturalness_rating'],
            analysis_result,
            conversation_log
        ])
    
    return analysis_result

@bot.message_handler(commands=['set_prompt'])
def set_system_prompt(message):
    """Allow user to set a custom system prompt"""
    user_id = message.from_user.id
    
    # Get current prompt
    current_prompt = DEFAULT_SYSTEM_PROMPT
    if user_id in user_conversations:
        current_prompt = user_conversations[user_id]['system_prompt']
    
    # Split the message into chunks if needed
    chunks = split_long_message(f"Текущий системный промпт:\n{current_prompt}\n\nХотите изменить системный промпт? Отправьте новый промпт или нажмите /cancel для отмены.")
    
    # Send each chunk
    for i, chunk in enumerate(chunks):
        if i == 0:  # First chunk
            bot.reply_to(message, chunk)
        else:  # Subsequent chunks
            bot.send_message(message.chat.id, chunk)
    
    bot.register_next_step_handler(message, save_system_prompt)

def save_system_prompt(message):
    """Save the user's custom system prompt"""
    user_id = message.from_user.id
    
    # Ensure user has an active conversation state
    if user_id not in user_conversations:
        reset_user_conversation(user_id)
    
    # Check if the message is a command
    if message.text.startswith('/'):
        bot.reply_to(message, "❌ Изменение промпта отменено.")
        return
    
    # Update system prompt
    new_system_prompt = message.text
    user_conversations[user_id]['system_prompt'] = new_system_prompt
    
    # Recreate memory with new system prompt
    user_conversations[user_id]['memory'] = TelegramChatMemory(user_id, new_system_prompt)
    
    # Recreate chain with new system prompt
    user_conversations[user_id]['chain'] = create_chat_chain(new_system_prompt)
    
    # Send confirmation message with the new prompt
    bot.reply_to(message, f"Системный промпт обновлен:\n{new_system_prompt}")

@bot.message_handler(commands=['start_chat'])
def start_chat(message):
    """Initiate a new chat session"""
    user_id = message.from_user.id
    reset_user_conversation(user_id)
    bot.reply_to(message, CHAT_STARTED_MESSAGE)
    # Send default greeting message from the bot
    bot.send_message(user_id, "Алло, здравствуйте")

@bot.message_handler(commands=['end_chat'])
def end_chat(message):
    """End the current chat session and log conversation"""
    user_id = message.from_user.id
    
    if user_id in user_conversations:
        user_conversations[user_id]['active'] = False
        bot.reply_to(
            message, 
            "Чат завершен. Оцените, пожалуйста, естественность диалога по шкале от 1 до 5:",
            reply_markup=create_naturalness_rating_keyboard()
        )
    else:
        bot.reply_to(message, NO_ACTIVE_CHAT_MESSAGE)

@bot.callback_query_handler(func=lambda call: call.data.startswith('rating_'))
def handle_rating(call):
    """Handle conversation rating and log to CSV"""
    user_id = call.from_user.id
    
    if user_id in user_conversations:
        # Set rating based on callback
        if call.data == 'rating_successful':
            user_conversations[user_id]['rating'] = True
            response_text = "Спасибо! Разговор отмечен как успешный. 👍\n"
        else:
            user_conversations[user_id]['rating'] = False
            response_text = "Спасибо за ваш отзыв. Разговор отмечен как неуспешный. 👎\n"
        
        # Log the conversation to CSV and get naturalness rating
        analysis_result = log_conversation_to_csv(user_id)
        
        response_text += f"Результат анализа:\n{analysis_result}"
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            text=response_text
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('naturalness_rating_'))
def handle_naturalness_rating(call):
    """Handle naturalness rating and log to CSV"""
    user_id = call.from_user.id
    
    if user_id in user_conversations:
        rating = int(call.data.split('_')[-1])
        user_conversations[user_id]['naturalness_rating'] = rating
        
        # Log the conversation to CSV and get analysis result
        analysis_result = log_conversation_to_csv(user_id)
        
        response_text = f"Спасибо за оценку! Вы оценили естественность диалога на {rating} из 5.\n"
        response_text += f"Результат анализа:\n{analysis_result}"
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            chat_id=call.message.chat.id, 
            message_id=call.message.message_id, 
            text=response_text
        )

def log_conversation(user_id):
    """Log conversation details"""
    conversation = user_conversations.get(user_id)
    if not conversation:
        return
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs/llm_experiments', exist_ok=True)
    
    # Generate log filename
    log_filename = f"logs/llm_experiments/conversation_{user_id}_{int(datetime.now().timestamp())}.log"
    
    with open(log_filename, 'w', encoding='utf-8') as f:
        f.write(f"User ID: {user_id}\n")
        f.write(f"System Prompt: {conversation['system_prompt']}\n")
        f.write(f"Rating: {'Успешно' if conversation['rating'] else 'Неуспешно'}\n\n")
        f.write("Conversation Log:\n")
        for msg in conversation['memory'].get_messages():
            f.write(f"{msg.type.upper()}: {msg.content}\n")

@bot.message_handler(func=lambda message: message.text == "⏹ Завершить диалог")
def handle_end_chat_button(message):
    """Handle end chat button press"""
    user_id = message.from_user.id
    
    if user_id in user_conversations and user_conversations[user_id]['active']:
        user_conversations[user_id]['active'] = False
        bot.reply_to(
            message, 
            CHAT_ENDED_MESSAGE,
            reply_markup=create_naturalness_rating_keyboard()
        )
    else:
        bot.reply_to(message, NO_ACTIVE_CHAT_MESSAGE)

@bot.message_handler(func=lambda message: message.text == "▶️ Начать диалог")
def handle_start_chat_button(message):
    """Handle start chat button press"""
    user_id = message.from_user.id
    reset_user_conversation(user_id)
    bot.reply_to(message, CHAT_STARTED_MESSAGE)
    # Send default greeting message from the bot
    bot.send_message(user_id, "Алло, здравствуйте")

@bot.message_handler(func=lambda message: message.text == "🎯 Установить промпт")
def handle_set_prompt_button(message):
    """Handle set prompt button press"""
    set_system_prompt(message)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """Handle user messages during an active chat"""
    user_id = message.from_user.id
    
    # Ensure user has an active conversation
    if user_id not in user_conversations or not user_conversations[user_id]['active']:
        bot.reply_to(message, "Пожалуйста, начните чат, используя /start_chat или кнопку '▶️ Начать диалог'")
        return
    
    # Get conversation context
    conversation = user_conversations[user_id]
    memory = conversation['memory']
    chain = conversation['chain']
    
    try:
        # Add user message to memory
        memory.add_user_message(message.text)
        
        # Invoke chain with input and chat history
        response = chain.invoke({
            "input": message.text,
            "chat_history": memory.get_messages()
        })
        
        # Extract AI response
        ai_response = response.content
        
        # Add AI response to memory
        memory.add_ai_message(ai_response)
        
        # Send response to user
        bot.reply_to(message, ai_response)
    
    except Exception as e:
        logging.error(f"Ошибка LLM API: {e}")
        bot.reply_to(message, "Извините, произошла ошибка при обработке вашего сообщения.")

def transcribe_voice_message(voice_file_path):
    """Transcribe voice message using Whisper API"""
    try:
        with open(voice_file_path, "rb") as audio_file:
            transcription = openai_client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file
            )
        return transcription.text
    except Exception as e:
        logging.error(f"Ошибка транскрипции голоса: {e}")
        return None

@bot.message_handler(content_types=['voice'])
def handle_voice_message(message):
    """Handle incoming voice messages"""
    user_id = message.from_user.id
    
    # Ensure user has an active conversation
    if user_id not in user_conversations or not user_conversations[user_id]['active']:
        bot.reply_to(message, "Пожалуйста, начните чат, используя /start_chat")
        return
    
    # Get conversation context
    conversation = user_conversations[user_id]
    memory = conversation['memory']
    chain = conversation['chain']
    
    try:
        # Download voice file
        voice_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(voice_info.file_path)
        
        # Save voice file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_voice:
            temp_voice.write(downloaded_file)
            temp_voice_path = temp_voice.name
        
        # Transcribe voice message
        transcribed_text = transcribe_voice_message(temp_voice_path)
        
        # Clean up temporary file
        os.unlink(temp_voice_path)
        
        if not transcribed_text:
            bot.reply_to(message, "Извините, не удалось расшифровать голосовое сообщение.")
            return
        
        # Send transcription to user
        bot.reply_to(message, f"Расшифрованный текст: {transcribed_text}")
        
        # Add transcribed text as user message
        memory.add_user_message(transcribed_text)
        
        # Invoke chain with input and chat history
        response = chain.invoke({
            "input": transcribed_text,
            "chat_history": memory.get_messages()
        })
        
        # Extract AI response
        ai_response = response.content
        
        # Add AI response to memory
        memory.add_ai_message(ai_response)
        
        # Send response to user
        bot.reply_to(message, ai_response)
    
    except Exception as e:
        logging.error(f"Ошибка обработки голосового сообщения: {e}")
        bot.reply_to(message, "Извините, произошла ошибка при обработке вашего голосового сообщения.")

def main():
    """Main bot polling function"""
    logging.info("LLM Experiment Telegram Bot started...")
    bot.polling(none_stop=True)

if __name__ == '__main__':
    main()
