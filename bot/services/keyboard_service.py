from telebot import types

class KeyboardService:
    """Service for creating Telegram keyboards"""
    
    @staticmethod
    def create_main_keyboard() -> types.ReplyKeyboardMarkup:
        """Create main menu keyboard"""
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("🎯 Установить промпт")
        markup.row("▶️ Начать диалог", "⏹ Завершить диалог")
        return markup
    
    @staticmethod
    def create_rating_keyboard() -> types.InlineKeyboardMarkup:
        """Create inline keyboard for dialog rating"""
        markup = types.InlineKeyboardMarkup()
        successful_btn = types.InlineKeyboardButton(
            "✅ Диалог успешный",
            callback_data='rating_successful'
        )
        unsuccessful_btn = types.InlineKeyboardButton(
            "❌ Диалог неуспешный",
            callback_data='rating_unsuccessful'
        )
        markup.row(successful_btn, unsuccessful_btn)
        return markup
    
    @staticmethod
    def create_naturalness_rating_keyboard() -> types.InlineKeyboardMarkup:
        """Create inline keyboard for naturalness rating"""
        markup = types.InlineKeyboardMarkup()
        for i in range(1, 6):
            markup.add(types.InlineKeyboardButton(
                str(i),
                callback_data=f'naturalness_rating_{i}'
            ))
        return markup 