import re
import time
from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.intent_detector import run_university_chatbot

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    start_time = time.time()

    bot_reply = run_university_chatbot(request.question)
    cleaned_reply = re.sub(r'\n{3,}', '\n\n', bot_reply)

    end_time = time.time()
    response_time = round(end_time - start_time, 2)

    print(f"[INFO] Response Time: {response_time} seconds")

    return ChatResponse(answer=cleaned_reply, is_markdown=True, response_time=response_time)