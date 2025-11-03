# This is a projects for TJU Materials-AI

## Step1: 技术选型 - 简单高效起步
对于第一个界面，我推荐：

* 前端框架: Vue 3 + Vite (简单易学，开发体验好)
* UI组件库: Element Plus (组件丰富，文档完善)
* HTTP客户端: Axios (处理API请求)
* 后端: Python FastAPI (异步支持好，与AI生态兼容性强)
* 大模型API: 从DeepSeek API开始 (性价比高，文档清晰)

## Step2: 环境准备
```
# 创建项目目录
mkdir Materials-AI
cd Materials-AI

# 前端项目
npm create vue@latest frontend
# 选择: TypeScript, JSX, Vue Router, Pinia, ESLint

# 后端项目
mkdir backend
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install fastapi uvicorn python-dotenv openai

```

## Step3: 编写第一个界面-聊天窗口

前端代码（Vue 3） 
```
-- src/App.vue -- 
主界面 ./frontend/src/App.vue
```
后端代码（Fast API）
```
backend/main.py --后端API服务
```

backend/.env - 环境配置文件

```
# DeepSeek API配置
DEEPSEEK_API_KEY=your_actual_deepseek_api_key_here

# 服务配置
HOST=0.0.0.0
PORT=8000
```

## Step4: 安装依赖并运行

前端依赖安装
```
cd frontend
npm install axios element-plus @element-plus/icons-vue
npm run dev
```