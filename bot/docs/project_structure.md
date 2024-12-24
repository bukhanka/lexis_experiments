bot/
├── services/
│   ├── __init__.py
│   ├── llm_service.py      # LLM operations
│   ├── stt_service.py      # Speech-to-text operations
│   ├── memory_service.py   # Chat memory management
│   ├── conversation_service.py  # User conversation state
│   ├── logging_service.py  # Conversation logging
│   └── keyboard_service.py # Telegram keyboard creation
├── tg_bot.py              # Main bot file
└── config.yaml            # Configuration