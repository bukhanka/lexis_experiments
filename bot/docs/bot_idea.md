create telegram bot that to experiment with llm behavior on a current prompt

functionalities to implement:

✅ user should have ability to set and see system prompt that will be passed as system prompt to llm 
✅ user have ability to communicate with llm and have button to end dialog
✅ after the dialog user should be able to rate the dialog was it successful or not
✅ when system prompt is set it should be saved and unchanged until user changes it
✅ add check system prompt button
✅ add voice input with whisper api (works in chat mode, converts voice to text and then LLM responds)

ideas, dont implement yet:

✅ we should save logs of the dialog to the csv file with status (success or failed), also dialog itself + system prompt
✅ each user should have unique id and we should save logs to the csv file with user id/ so each system prompt should only apply to a specific user

after chat is ended llm to rate the chat how natural it was (use gpt-4o) and return it to the user -create comprehensive prompt for that - it should rate both llm and user