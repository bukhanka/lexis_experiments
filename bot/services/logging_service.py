import os
import csv
from datetime import datetime
from typing import Dict, Any, Optional

from .llm_service import LLMService

class LoggingService:
    """Service for handling conversation logging"""
    
    def __init__(self, llm_service: LLMService, log_dir: str = 'logs/llm_experiments'):
        self.llm_service = llm_service
        self.log_dir = log_dir
        self.csv_path = f'{log_dir}/conversations.csv'
        self._ensure_log_directory()
    
    def _ensure_log_directory(self) -> None:
        """Ensure log directory exists"""
        os.makedirs(self.log_dir, exist_ok=True)
    
    def log_conversation(
        self,
        user_id: int,
        conversation: Dict[str, Any],
        analysis_prompt: str
    ) -> Optional[str]:
        """Log conversation details to CSV and return analysis result"""
        if not conversation:
            return None
        
        # Get conversation log
        conversation_log = conversation['memory'].format_conversation_log()
        
        # Get analysis result
        analysis_result = self.llm_service.analyze_conversation(
            conversation_log=conversation_log,
            system_prompt=conversation['system_prompt'],
            analysis_prompt=analysis_prompt
        )
        
        # Write to CSV
        self._write_to_csv(
            user_id=user_id,
            conversation=conversation,
            conversation_log=conversation_log,
            analysis_result=analysis_result
        )
        
        return analysis_result
    
    def _write_to_csv(
        self,
        user_id: int,
        conversation: Dict[str, Any],
        conversation_log: str,
        analysis_result: str
    ) -> None:
        """Write conversation details to CSV file"""
        csv_exists = os.path.exists(self.csv_path)
        
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as csvfile:
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
    
    def log_conversation_to_file(
        self,
        user_id: int,
        conversation: Dict[str, Any]
    ) -> None:
        """Log conversation details to a text file"""
        if not conversation:
            return
        
        log_filename = f"{self.log_dir}/conversation_{user_id}_{int(datetime.now().timestamp())}.log"
        
        with open(log_filename, 'w', encoding='utf-8') as f:
            f.write(f"User ID: {user_id}\n")
            f.write(f"System Prompt: {conversation['system_prompt']}\n")
            f.write(f"Rating: {'Успешно' if conversation['rating'] else 'Неуспешно'}\n\n")
            f.write("Conversation Log:\n")
            f.write(conversation['memory'].format_conversation_log()) 