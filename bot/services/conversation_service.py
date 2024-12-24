import uuid
from typing import Dict, Any, Optional
from .memory_service import TelegramChatMemory
from .llm_service import LLMService

class ConversationService:
    """Service for managing user conversations"""
    
    def __init__(self, llm_service: LLMService, default_system_prompt: str):
        self.llm_service = llm_service
        self.default_system_prompt = default_system_prompt
        self.conversations: Dict[int, Dict[str, Any]] = {}
    
    def create_conversation(self, user_id: int, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Create a new conversation for a user"""
        # Use existing system prompt if available, otherwise use default
        prompt_to_use = system_prompt or self.get_user_prompt(user_id) or self.default_system_prompt
        
        conversation = {
            'user_uuid': str(uuid.uuid4()),
            'memory': TelegramChatMemory(user_id, prompt_to_use),
            'chain': self.llm_service.create_chat_chain(prompt_to_use),
            'active': True,
            'rating': None,
            'naturalness_rating': None,
            'system_prompt': prompt_to_use
        }
        
        self.conversations[user_id] = conversation
        return conversation
    
    def get_conversation(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get an existing conversation"""
        return self.conversations.get(user_id)
    
    def get_user_prompt(self, user_id: int) -> Optional[str]:
        """Get user's current system prompt"""
        conversation = self.get_conversation(user_id)
        return conversation.get('system_prompt') if conversation else None
    
    def update_system_prompt(self, user_id: int, new_prompt: str) -> None:
        """Update system prompt for a user"""
        conversation = self.get_conversation(user_id)
        if not conversation:
            self.create_conversation(user_id, new_prompt)
            return
        
        conversation['system_prompt'] = new_prompt
        conversation['memory'] = TelegramChatMemory(user_id, new_prompt)
        conversation['chain'] = self.llm_service.create_chat_chain(new_prompt)
    
    def end_conversation(self, user_id: int) -> None:
        """End an active conversation"""
        conversation = self.get_conversation(user_id)
        if conversation:
            conversation['active'] = False
    
    def set_rating(self, user_id: int, rating: bool) -> None:
        """Set success/failure rating for a conversation"""
        conversation = self.get_conversation(user_id)
        if conversation:
            conversation['rating'] = rating
    
    def set_naturalness_rating(self, user_id: int, rating: int) -> None:
        """Set naturalness rating for a conversation"""
        conversation = self.get_conversation(user_id)
        if conversation:
            conversation['naturalness_rating'] = rating
    
    def is_conversation_active(self, user_id: int) -> bool:
        """Check if user has an active conversation"""
        conversation = self.get_conversation(user_id)
        return bool(conversation and conversation.get('active')) 