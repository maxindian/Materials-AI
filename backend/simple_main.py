from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Generator
import os
from openai import OpenAI
import logging
from dotenv import load_dotenv
import uvicorn
import json
import time

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="天津大学材料学科教育大模型API", version="1.0.0")

# CORS配置 - 允许前端访问
app.add_middleware(
    CORSMiddleware,
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
    stream: Optional[bool] = False  # 新增流式传输选项

class ChatResponse(BaseModel):
    response: str
    status: str = "success"
    token_usage: Optional[dict] = None  # 新增token使用情况

# 初始化OpenAI客户端（使用DeepSeek API）
client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "sk-a9d055eed098404bb606349d3c83ff83"),
    base_url="https://api.deepseek.com/v1",
    timeout=30.0,  # 增加超时时间
    max_retries=2  # 增加重试次数
)

# 材料学科专用系统提示词
MATERIALS_SCIENCE_SYSTEM_PROMPT = """你是天津大学材料学科教育大模型助手，专门为材料科学与工程领域提供专业支持。

## 你的专业背景
- 机构：天津大学材料科学与工程学院
- 专业领域：材料科学、材料工程、纳米材料、金属材料、高分子材料、复合材料等
- 能力范围：材料设计、制备工艺、性能表征、应用开发等
"""

# ## 回答原则
# 1. **专业性**：提供准确的材料科学知识，引用权威概念和理论
# 2. **教育性**：用易于理解的方式解释复杂概念，适合不同层次学习者
# 3. **实用性**：结合工程实际应用，提供可操作的建议
# 4. **安全性**：强调实验安全和材料处理规范
# 5. **创新性**：关注材料科学前沿发展和新技术

# ## 回答格式
# - 使用Markdown格式组织内容
# - 重要的专业术语使用**粗体**强调
# - 复杂概念提供具体示例
# - 涉及数据时尽量提供具体数值范围
# - 对于实验操作，强调安全注意事项

# 请以友好、专业的语气回答用户问题，体现天津大学材料学科的专业水准。

def generate_stream_response(text: str) -> Generator[str, None, None]:
    """生成流式响应"""
    words = text.split()
    for i, word in enumerate(words):
        yield f"data: {json.dumps({'content': word + ' ', 'finished': False})}\n\n"
        time.sleep(0.05)  # 模拟流式输出效果
    
    yield f"data: {json.dumps({'content': '', 'finished': True})}\n\n"

@app.get("/")
async def root():
    return {
        "message": "天津大学材料学科教育大模型API服务运行中", 
        "status": "success",
        "version": "1.0.0",
        "service": "材料智思体平台"
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    try:
        logger.info(f"收到用户消息: {request.message}")
        logger.info(f"历史消息数量: {len(request.history)}")
        
        # 构建对话历史
        messages = []
        
        # 添加材料学科专用系统提示词
        messages.append({"role": "system", "content": MATERIALS_SCIENCE_SYSTEM_PROMPT})
        
        # 添加历史对话（限制长度以避免token超限）
        for msg in request.history[-8:]:  # 增加到最近8轮对话
            # 过滤掉系统消息和错误消息
            if msg.role in ['user', 'assistant'] and not getattr(msg, 'isError', False):
                messages.append({"role": msg.role, "content": msg.content})
        
        # 添加当前用户消息
        messages.append({"role": "user", "content": request.message})
        
        logger.info(f"发送给API的消息数量: {len(messages)}")
        
        # 调用大模型API
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            max_tokens=4000,  # 增加token限制以适应更专业的回答
            temperature=0.7,
            stream=request.stream  # 支持流式传输
        )
        
        if request.stream:
            # 流式响应处理
            def generate():
                full_content = ""
                for chunk in response:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        full_content += content
                        yield f"data: {json.dumps({'content': content, 'finished': False})}\n\n"
                
                yield f"data: {json.dumps({'content': '', 'finished': True, 'full_content': full_content})}\n\n"
            
            return StreamingResponse(
                generate(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
            )
        else:
            # 非流式响应
            ai_response = response.choices[0].message.content
            
            # 记录token使用情况（如果API返回）
            token_usage = {}
            if hasattr(response, 'usage'):
                token_usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            
            logger.info(f"AI回复生成长度: {len(ai_response)} 字符")
            if token_usage:
                logger.info(f"Token使用情况: {token_usage}")
            
            return ChatResponse(
                response=ai_response,
                token_usage=token_usage
            )
        
    except Exception as e:
        logger.error(f"API调用错误: {str(e)}", exc_info=True)
        
        # 提供更友好的错误信息
        error_detail = f"AI服务暂时不可用: {str(e)}"
        if "rate limit" in str(e).lower():
            error_detail = "API调用频率超限，请稍后重试"
        elif "authentication" in str(e).lower():
            error_detail = "API认证失败，请检查API密钥配置"
        elif "timeout" in str(e).lower():
            error_detail = "请求超时，请检查网络连接"
        
        raise HTTPException(
            status_code=500, 
            detail=error_detail
        )

@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    try:
        # 简单测试API连接
        test_response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": "Say 'healthy'"}],
            max_tokens=10
        )
        api_status = "healthy" if test_response.choices else "degraded"
    except Exception as e:
        logger.warning(f"健康检查API测试失败: {e}")
        api_status = "unhealthy"
    
    return {
        "status": "healthy", 
        "service": "天津大学材料学科教育大模型API",
        "api_status": api_status,
        "timestamp": time.time()
    }

@app.get("/api/info")
async def api_info():
    """API信息端点"""
    return {
        "name": "天津大学材料学科教育大模型",
        "version": "1.0.0",
        "description": "专门为材料科学与工程领域设计的智能对话系统",
        "features": [
            "材料科学专业问答",
            "教育辅助功能",
            "Markdown格式响应",
            "流式传输支持",
            "对话历史管理"
        ],
        "supported_models": ["deepseek-chat"],
        "max_history_length": 8,
        "max_tokens": 4000
    }

@app.post("/api/chat/stream")
async def chat_with_ai_stream(request: ChatRequest):
    """专门的流式聊天端点"""
    request.stream = True
    return await chat_with_ai(request)

# 错误处理
@app.exception_handler(500)
async def internal_server_error_handler(request, exc):
    logger.error(f"服务器内部错误: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"}
    )

@app.exception_handler(429)
async def rate_limit_handler(request, exc):
    logger.warning("请求频率超限")
    return JSONResponse(
        status_code=429,
        content={"detail": "请求过于频繁，请稍后重试"}
    )

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000, 
        reload=True,
        timeout_keep_alive=300  # 增加超时时间以适应长对话
    )