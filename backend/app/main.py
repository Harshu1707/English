import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.routers import admin, admin_progress, auth, media, practice, progress
app=FastAPI(title="Verba API",version="0.1.0",description="REST API for English speaking practice.")
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in settings.cors_origins.split(',')],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])
app.include_router(auth.router)
app.include_router(media.router)
app.include_router(practice.router)
app.include_router(progress.router)
app.include_router(admin.router)
app.include_router(admin_progress.router)
if settings.jwt_secret == "development-only-change-me": logging.getLogger("verba").warning("JWT_SECRET is the built-in development default: anyone can forge tokens. Set a long random JWT_SECRET.")
@app.get("/health",tags=["system"])
def health(): return {"status":"ok"}
@app.get("/lessons",tags=["lessons"])
def lessons(): return []
