from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import os
from openai import OpenAI
import logging
from dotenv import load_dotenv
import uvicorn

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI智能体平台API", version="1.0.0")

# CORS配置 - 允许前端访问
app.add_middleware(
    CORSMiddleware,
    # allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]

class ChatResponse(BaseModel):
    response: str
    status: str = "success"

# 初始化OpenAI客户端（使用DeepSeek API）
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-a9d055eed098404bb606349d3c83ff83"),
    base_url="https://api.deepseek.com/v1",
    timeout=60.0,  # 增加超时时间
)

@app.get("/")
async def root():
    return {"message": "材料智思体平台API服务运行中", "status": "success"}

@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    try:
        logger.info(f"收到用户消息: {request.message}")
        
        # 构建对话历史
        messages = []
        
        # 添加系统提示词 - 定义AI的角色和行为
        system_prompt = """你是一个有帮助的材料AI助手。请用友好、专业的语气回答用户的问题。
        如果用户的问题需要特定的专业知识，请尽可能提供准确、详细的信息。
        如果遇到你不知道答案的问题，诚实地告知用户，并提供可能的解决方案方向。"""
        
        messages.append({"role": "system", "content": system_prompt})
        
        # 添加历史对话（限制长度以避免token超限）
        for msg in request.history[-6:]:  # 最近6轮对话
            messages.append({"role": msg.role, "content": msg.content})
        
        # 添加当前用户消息
        messages.append({"role": "user", "content": request.message})
        
        # 调用大模型API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=2000,
            temperature=0.7,
            stream=False
        )
        
        ai_response = response.choices[0].message.content
        
        logger.info(f"AI回复生成长度: {len(ai_response)} 字符")
        
        return ChatResponse(response=ai_response)
        
    except Exception as e:
        logger.error(f"API调用错误: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"AI服务暂时不可用: {str(e)}"
        )

@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "service": "AI Agent Platform API"}

if __name__ == "__main__":
    # uvicorn.run(app, host="0.0.0.0", port=8000)
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)