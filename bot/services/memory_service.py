from typing import List
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage

class TelegramChatMemory:
    """Service for managing Telegram chat memory and conversation state"""
    
    def __init__(self, user_id: int, system_prompt: str = None):
        self.user_id = user_id
        self.messages: List[BaseMessage] = []
        
        if system_prompt:
            self.add_system_message(system_prompt)
    
    def add_user_message(self, message: str) -> None:
        """Add a user message to the conversation history"""
        self.messages.append(HumanMessage(content=message))
    
    def add_ai_message(self, message: str) -> None:
        """Add an AI message to the conversation history"""
        self.messages.append(AIMessage(content=message))
    
    def add_system_message(self, message: str) -> None:
        """Add or update the system message"""
        # Remove any existing system messages first
        self.messages = [msg for msg in self.messages if not isinstance(msg, SystemMessage)]
        self.messages.insert(0, SystemMessage(content=message))
    
    def get_messages(self) -> List[BaseMessage]:
        """Get all messages in the conversation history"""
        return self.messages
    
    def clear(self) -> None:
        """Clear all messages except system message"""
        system_messages = [msg for msg in self.messages if isinstance(msg, SystemMessage)]
        self.messages = system_messages
    
    def format_conversation_log(self) -> str:
        """Format the conversation history for logging"""
        return "\n".join([
            f"{msg.type.upper()}: {msg.content}" 
            for msg in self.messages
        ]) 