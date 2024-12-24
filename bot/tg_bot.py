import os
import logging
import yaml
import tempfile

import telebot
from dotenv import load_dotenv

# Import services
from services.llm_service import LLMService
from services.stt_service import STTService
from services.conversation_service import ConversationService
from services.keyboard_service import KeyboardService
from services.logging_service import LoggingService

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class TelegramBot:
    """Main Telegram bot class"""
    
    def __init__(self):
        # Load configuration
        self.config = self._load_config()
        
        # Initialize services
        self.llm_service = LLMService(self.config['llm_provider'])
        self.stt_service = STTService()
        self.conversation_service = ConversationService(
            self.llm_service,
            self.config['default_system_prompt']
        )
        self.keyboard_service = KeyboardService()
        self.logging_service = LoggingService(self.llm_service)
        
        # Initialize bot
        self.bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))
        self._setup_handlers()
    
    def _load_config(self) -> dict:
        """Load configuration from YAML file"""
        with open('config.yaml', 'r', encoding='utf-8') as config_file:
            return yaml.safe_load(config_file)
    
    def _setup_handlers(self) -> None:
        """Set up all message handlers"""
        # Command handlers
        self.bot.message_handler(commands=['start'])(self.handle_start)
        self.bot.message_handler(commands=['check_prompt'])(self.handle_check_prompt)
        self.bot.message_handler(commands=['voice_input'])(self.handle_voice_input)
        self.bot.message_handler(commands=['set_prompt'])(self.handle_set_prompt)
        self.bot.message_handler(commands=['start_chat'])(self.handle_start_chat)
        self.bot.message_handler(commands=['end_chat'])(self.handle_end_chat)
        
        # Button handlers
        self.bot.message_handler(func=lambda m: m.text == "▶️ Начать диалог")(self.handle_start_chat)
        self.bot.message_handler(func=lambda m: m.text == "⏹ Завершить диалог")(self.handle_end_chat)
        self.bot.message_handler(func=lambda m: m.text == "🎯 Установить промпт")(self.handle_set_prompt)
        
        # Callback handlers
        self.bot.callback_query_handler(func=lambda c: c.data.startswith('rating_'))(self.handle_rating)
        self.bot.callback_query_handler(func=lambda c: c.data.startswith('naturalness_rating_'))(self.handle_naturalness_rating)
        
        # Content type handlers
        self.bot.message_handler(content_types=['voice'])(self.handle_voice_message)
        self.bot.message_handler(func=lambda m: True)(self.handle_text_message)
    
    def handle_start(self, message):
        """Handle /start command"""
        self.conversation_service.create_conversation(message.from_user.id)
        self.bot.reply_to(
            message,
            self.config['welcome_message'],
            reply_markup=self.keyboard_service.create_main_keyboard()
        )
    
    def handle_check_prompt(self, message):
        """Handle /check_prompt command"""
        user_id = message.from_user.id
        current_prompt = self.conversation_service.get_user_prompt(user_id)
        
        if current_prompt:
            self.bot.reply_to(message, f"Текущий системный промпт:\n{current_prompt}")
        else:
            self.bot.reply_to(message, self.config['prompt_not_set_message'])
    
    def handle_voice_input(self, message):
        """Handle /voice_input command"""
        self.bot.reply_to(message, self.config['voice_input_coming_soon'])
    
    def handle_set_prompt(self, message):
        """Handle /set_prompt command"""
        user_id = message.from_user.id
        current_prompt = self.conversation_service.get_user_prompt(user_id) or self.config['default_system_prompt']
        
        prompt_message = f"Текущий системный промпт:\n{current_prompt}\n\nХотите изменить системный промпт? Отправьте новый промпт или нажмите /cancel для отмены."
        
        # Split long messages if needed
        chunks = [prompt_message[i:i + 4000] for i in range(0, len(prompt_message), 4000)]
        for i, chunk in enumerate(chunks):
            if i == 0:
                self.bot.reply_to(message, chunk)
            else:
                self.bot.send_message(message.chat.id, chunk)
        
        self.bot.register_next_step_handler(message, self.save_system_prompt)
    
    def save_system_prompt(self, message):
        """Save new system prompt"""
        if message.text.startswith('/'):
            self.bot.reply_to(message, "❌ Изменение промпта отменено.")
            return
        
        self.conversation_service.update_system_prompt(message.from_user.id, message.text)
        self.bot.reply_to(message, f"Системный промпт обновлен:\n{message.text}")
    
    def handle_start_chat(self, message):
        """Handle chat start command/button"""
        user_id = message.from_user.id
        self.conversation_service.create_conversation(user_id)
        self.bot.reply_to(message, self.config['chat_started_message'])
        self.bot.send_message(user_id, "Алло, здравствуйте")
    
    def handle_end_chat(self, message):
        """Handle chat end command/button"""
        user_id = message.from_user.id
        
        if self.conversation_service.is_conversation_active(user_id):
            self.conversation_service.end_conversation(user_id)
            self.bot.reply_to(
                message,
                self.config['chat_ended_message'],
                reply_markup=self.keyboard_service.create_naturalness_rating_keyboard()
            )
        else:
            self.bot.reply_to(message, self.config['no_active_chat_message'])
    
    def handle_rating(self, call):
        """Handle conversation rating callback"""
        user_id = call.from_user.id
        conversation = self.conversation_service.get_conversation(user_id)
        
        if conversation:
            is_successful = call.data == 'rating_successful'
            self.conversation_service.set_rating(user_id, is_successful)
            
            response_text = "Спасибо! Разговор отмечен как успешный. 👍\n" if is_successful else "Спасибо за ваш отзыв. Разговор отмечен как неуспешный. 👎\n"
            
            # Log conversation and get analysis
            analysis_result = self.logging_service.log_conversation(
                user_id,
                conversation,
                self.config['conversation_analysis_prompt']
            )
            
            response_text += f"Результат анализа:\n{analysis_result}"
            
            self.bot.answer_callback_query(call.id)
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=response_text
            )
    
    def handle_naturalness_rating(self, call):
        """Handle naturalness rating callback"""
        user_id = call.from_user.id
        conversation = self.conversation_service.get_conversation(user_id)
        
        if conversation:
            rating = int(call.data.split('_')[-1])
            self.conversation_service.set_naturalness_rating(user_id, rating)
            
            # Log conversation and get analysis
            analysis_result = self.logging_service.log_conversation(
                user_id,
                conversation,
                self.config['conversation_analysis_prompt']
            )
            
            response_text = f"Спасибо за оценку! Вы оценили естественность диалога на {rating} из 5.\n"
            response_text += f"Результат анализа:\n{analysis_result}"
            
            self.bot.answer_callback_query(call.id)
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=response_text
            )
    
    def handle_voice_message(self, message):
        """Handle voice messages"""
        user_id = message.from_user.id
        
        if not self.conversation_service.is_conversation_active(user_id):
            self.bot.reply_to(message, "Пожалуйста, начните чат, используя /start_chat")
            return
        
        conversation = self.conversation_service.get_conversation(user_id)
        memory = conversation['memory']
        chain = conversation['chain']
        
        try:
            # Download and save voice file
            voice_info = self.bot.get_file(message.voice.file_id)
            downloaded_file = self.bot.download_file(voice_info.file_path)
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_voice:
                temp_voice.write(downloaded_file)
                temp_voice_path = temp_voice.name
            
            # Transcribe voice message
            transcribed_text = self.stt_service.transcribe_voice(temp_voice_path)
            os.unlink(temp_voice_path)
            
            if not transcribed_text:
                self.bot.reply_to(message, "Извините, не удалось расшифровать голосовое сообщение.")
                return
            
            # Send transcription to user
            self.bot.reply_to(message, f"Расшифрованный текст: {transcribed_text}")
            
            # Process message
            memory.add_user_message(transcribed_text)
            response = chain.invoke({
                "input": transcribed_text,
                "chat_history": memory.get_messages()
            })
            
            # Handle response
            ai_response = response.content
            memory.add_ai_message(ai_response)
            self.bot.reply_to(message, ai_response)
            
        except Exception as e:
            logging.error(f"Error processing voice message: {e}")
            self.bot.reply_to(message, "Извините, произошла ошибка при обработке вашего голосового сообщения.")
    
    def handle_text_message(self, message):
        """Handle text messages"""
        user_id = message.from_user.id
        
        if not self.conversation_service.is_conversation_active(user_id):
            self.bot.reply_to(
                message,
                "Пожалуйста, начните чат, используя /start_chat или кнопку '▶️ Начать диалог'"
            )
            return
        
        conversation = self.conversation_service.get_conversation(user_id)
        memory = conversation['memory']
        chain = conversation['chain']
        
        try:
            # Process message
            memory.add_user_message(message.text)
            response = chain.invoke({
                "input": message.text,
                "chat_history": memory.get_messages()
            })
            
            # Handle response
            ai_response = response.content
            memory.add_ai_message(ai_response)
            self.bot.reply_to(message, ai_response)
            
        except Exception as e:
            logging.error(f"Error processing message: {e}")
            self.bot.reply_to(message, "Извините, произошла ошибка при обработке вашего сообщения.")
    
    def run(self):
        """Start the bot"""
        logging.info("LLM Experiment Telegram Bot started...")
        self.bot.polling(none_stop=True)

def main():
    """Main entry point"""
    bot = TelegramBot()
    bot.run()

if __name__ == '__main__':
    main()
