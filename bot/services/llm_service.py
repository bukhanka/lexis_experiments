import os
import logging
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

class LLMService:
    """Service for handling LLM operations"""
    
    def __init__(self, llm_provider: str = "gpt"):
        self.llm_provider = llm_provider
    
    def create_llm(self, temperature: float = 0.7) -> Optional[ChatOpenAI | ChatGoogleGenerativeAI]:
        """Create LLM instance based on provider"""
        try:
            if self.llm_provider == "gemini":
                try:
                    return ChatGoogleGenerativeAI(
                        model="gemini-pro",
                        temperature=temperature,
                        google_api_key=os.getenv('GOOGLE_API_KEY')
                    )
                except Exception as gemini_error:
                    logging.warning(f"Gemini initialization failed: {gemini_error}")
                    return self._create_openai_llm(temperature)
            elif self.llm_provider == "gpt":
                return self._create_openai_llm(temperature)
            else:
                logging.error(f"Unknown LLM provider: {self.llm_provider}")
                return self._create_openai_llm(temperature)
        except Exception as e:
            logging.error(f"Error creating LLM: {e}")
            return None

    def _create_openai_llm(self, temperature: float) -> ChatOpenAI:
        """Create OpenAI LLM instance"""
        return ChatOpenAI(
            model="gpt-4o",
            temperature=temperature,
            openai_api_key=os.getenv('OPENAI_API_KEY')
        )

    def create_chat_chain(self, system_prompt: str):
        """Create a LangChain chat chain with system prompt"""
        llm = self.create_llm()
        if not llm:
            return None
        
        try:
            prompt = ChatPromptTemplate.from_messages([
                SystemMessage(content=system_prompt),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}")
            ])
            
            return prompt | llm
        except Exception as e:
            logging.error(f"Error creating chat chain: {e}")
            return None

    def analyze_conversation(self, conversation_log: str, system_prompt: str, analysis_prompt: str) -> str:
        """Analyze conversation naturalness"""
        try:
            # Use lower temperature for analysis
            llm = self.create_llm(temperature=0.2)
            if not llm:
                return "Unable to analyze conversation"
            
            formatted_prompt = analysis_prompt.format(
                conversation_log=conversation_log,
                system_prompt=system_prompt
            )
            
            response = llm.invoke(formatted_prompt)
            return response.content
        except Exception as e:
            logging.error(f"Error analyzing conversation: {e}")
            return "Unable to analyze conversation" 