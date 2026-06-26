import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as chat_router

app = FastAPI(title="University Chatbot API", version="1.0.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

app.include_router(chat_router)

@app.get("/")
def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/favicon.ico")
def favicon():
    favicon_path = os.path.join(FRONTEND_DIR, "assets", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path)
    return None
