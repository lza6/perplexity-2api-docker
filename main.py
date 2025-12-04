import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, Header, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.core.config import settings
from app.providers.perplexity_provider import PerplexityProvider

# [修改] 设置日志级别为 DEBUG，格式包含文件名和行号
logger.remove()
logger.add(
    sys.stdout, 
    level="DEBUG", 
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
)

provider = PerplexityProvider()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"启动 {settings.APP_NAME} v{settings.APP_VERSION} (Deep Debug Mode)...")
    logger.info("正在初始化 Playwright 浏览器服务...")
    try:
        await provider.solver.initialize_session()
    except Exception as e:
        logger.error(f"初始化失败: {e}")
    yield
    logger.info("服务关闭。")

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

async def verify_key(authorization: str = Header(None)):
    if settings.API_MASTER_KEY != "1":
        if not authorization or authorization.split(" ")[1] != settings.API_MASTER_KEY:
            raise HTTPException(403, "Invalid API Key")

@app.post("/v1/chat/completions", dependencies=[Depends(verify_key)])
async def chat(request: Request):
    try:
        data = await request.json()
        # [新增] 打印客户端原始请求
        logger.debug(f"收到客户端请求: {data}")
        return await provider.chat_completion(data)
    except Exception as e:
        logger.error(f"Request Error: {e}")
        raise HTTPException(500, str(e))

@app.get("/v1/models")
async def models():
    return await provider.get_models()

@app.get("/", response_class=HTMLResponse)
async def ui():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()