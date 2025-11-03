<template>
  <div id="app" class="chat-container">
    <header class="chat-header">
      <h1>🤖 天津大学材料学科教育大模型</h1>
      <div class="header-controls">
        <el-button 
          v-if="loading" 
          type="warning" 
          size="small" 
          @click="stopGeneration"
          class="stop-button"
        >
          ⏹️ 停止生成
        </el-button>
        <el-button 
          type="success" 
          size="small" 
          @click="saveChatHistory"
          :disabled="messages.length <= 1"
        >
          💾 保存对话
        </el-button>
        <el-button 
          type="info" 
          size="small" 
          @click="loadChatHistory"
        >
          📂 加载历史
        </el-button>
        <el-button 
          type="danger" 
          size="small" 
          @click="clearChatHistory"
          :disabled="messages.length <= 1"
        >
          🗑️ 清空对话
        </el-button>
      </div>
      <p v-if="connectionStatus" :class="['status', connectionStatus]">
        {{ connectionStatus === 'connected' ? '✅ 已连接到服务器' : '❌ 服务器连接失败' }}
      </p>
    </header>

    <main class="chat-main">
      <!-- 消息显示区域 -->
      <div class="messages-container" ref="messagesContainer">
        <div 
          v-for="(message, index) in messages" 
          :key="index"
          :class="['message', message.role]"
        >
          <div class="avatar">
            {{ message.role === 'user' ? '👤' : '🤖' }}
          </div>
          <div class="content">
            <!-- 用户消息直接显示文本 -->
            <div v-if="message.role === 'user'" class="text">
              {{ message.content }}
            </div>
            <!-- AI消息渲染Markdown -->
            <div 
              v-else 
              class="markdown-content"
              v-html="renderMarkdown(message.content)"
            ></div>
            <div class="time">{{ message.timestamp }}</div>
            
            <!-- 错误消息的重试按钮 -->
            <div v-if="message.isError" class="error-actions">
              <el-button 
                type="primary" 
                size="small" 
                @click="retryMessage(index)"
                class="retry-button"
              >
                🔄 重新发送
              </el-button>
              <el-button 
                type="text" 
                size="small" 
                @click="editAndResend(index)"
              >
                ✏️ 编辑后发送
              </el-button>
            </div>
          </div>
        </div>
        
        <div v-if="loading" class="message assistant">
          <div class="avatar">🤖</div>
          <div class="content">
            <div class="typing-indicator">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div class="stop-hint">
              <el-button 
                type="warning" 
                size="mini" 
                @click="stopGeneration"
                class="stop-mini-button"
              >
                停止生成
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 输入区域 -->
      <div class="input-container">
        <div class="input-wrapper">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="3"
            placeholder="输入您的问题... (支持Markdown格式)"
            @keydown="handleKeydown"
            :disabled="loading || connectionStatus !== 'connected'"
            ref="messageInput"
          />
          <div class="button-group">
            <el-button 
              type="primary" 
              @click="sendMessage"
              :loading="loading"
              class="send-button"
              :disabled="!inputMessage.trim() || connectionStatus !== 'connected'"
            >
              {{ loading ? '思考中...' : '发送' }}
            </el-button>
            <el-button 
              v-if="lastUserMessageIndex !== -1"
              type="text" 
              @click="editLastMessage"
              class="edit-button"
            >
              📝 编辑上条
            </el-button>
          </div>
        </div>
        <div class="tips">
          {{ getConnectionTips() }}
        </div>
      </div>
    </main>

    <!-- 编辑消息对话框 -->
    <el-dialog
      v-model="editDialogVisible"
      title="编辑消息"
      width="600px"
      :before-close="handleEditDialogClose"
    >
      <el-input
        v-model="editingMessage"
        type="textarea"
        :rows="6"
        placeholder="编辑您的消息..."
      />
      <template #footer>
        <el-button @click="cancelEdit">取消</el-button>
        <el-button type="primary" @click="confirmEdit">确认发送</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { marked } from 'marked' 
import DOMPurify from 'dompurify'

// 配置marked选项
marked.setOptions({
  breaks: true,
  gfm: true,
  highlight: function (code: string) {
    return code
  }
})

// 扩展消息接口
interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
  isError?: boolean
  id?: string
}

// 响应数据
const messages = ref<ChatMessage[]>([
  {
    role: 'assistant',
    content: '你好！我是天津大学材料学科专用AI助手，请问有什么可以帮助您的？',
    timestamp: getCurrentTime(),
    id: generateId()
  }
])
const inputMessage = ref('')
const loading = ref(false)
const messagesContainer = ref<HTMLElement>()
const connectionStatus = ref<'connected' | 'disconnected' | 'checking'>('checking')
const messageInput = ref()
const cancelTokenSource = ref<axios.CancelTokenSource | null>(null)

// 编辑相关状态
const editDialogVisible = ref(false)
const editingMessage = ref('')
const editingIndex = ref(-1)

// 创建axios实例
const api = axios.create({
  baseURL: 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 计算属性：最后一条用户消息的索引
const lastUserMessageIndex = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      return i
    }
  }
  return -1
})

// 生成唯一ID
function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2)
}

// Markdown渲染函数
function renderMarkdown(content: string): string {
  try {
    return DOMPurify.sanitize(marked.parse(content) as string)
  } catch (error) {
    console.error('Markdown渲染错误:', error)
    return DOMPurify.sanitize(`<div class="markdown-error">${content}</div>`)
  }
}

// 获取当前时间
function getCurrentTime(): string {
  return new Date().toLocaleTimeString('zh-CN', { 
    hour: '2-digit', 
    minute: '2-digit' 
  })
}

// 检查后端连接状态
async function checkConnection() {
  try {
    connectionStatus.value = 'checking'
    const response = await api.get('/')
    if (response.status === 200) {
      connectionStatus.value = 'connected'
      return true
    }
  } catch (error) {
    console.error('后端连接失败:', error)
    connectionStatus.value = 'disconnected'
    return false
  }
}

// 获取连接提示信息
function getConnectionTips() {
  switch (connectionStatus.value) {
    case 'connected':
      return '提示: 按 Enter 发送，Shift + Enter 换行 | 支持停止生成和错误重试'
    case 'disconnected':
      return '❌ 无法连接到后端服务，请检查后端是否运行在 http://localhost:8000'
    case 'checking':
      return '🔄 检查服务器连接中...'
    default:
      return '正在连接服务器...'
  }
}

// 键盘事件处理
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

// 停止生成
function stopGeneration() {
  if (cancelTokenSource.value) {
    cancelTokenSource.value.cancel('用户停止生成')
    ElMessage.info('已停止生成')
  }
  loading.value = false
}

// 发送消息
async function sendMessage() {
  const message = inputMessage.value.trim()
  if (!message || loading.value || connectionStatus.value !== 'connected') {
    return
  }

  const userMessage: ChatMessage = {
    role: 'user',
    content: message,
    timestamp: getCurrentTime(),
    id: generateId()
  }

  messages.value.push(userMessage)
  inputMessage.value = ''
  loading.value = true

  scrollToBottom()

  try {
    // 创建取消令牌
    cancelTokenSource.value = axios.CancelToken.source()
    
    const response = await api.post('/api/chat', {
      message: message,
      history: messages.value.slice(0, -1)
    }, {
      cancelToken: cancelTokenSource.value.token
    })

    const assistantMessage: ChatMessage = {
      role: 'assistant',
      content: response.data.response,
      timestamp: getCurrentTime(),
      id: generateId()
    }

    messages.value.push(assistantMessage)
    ElMessage.success('消息发送成功！')
    
    // 自动保存对话历史
    autoSaveChatHistory()
    
  } catch (error: any) {
    if (axios.isCancel(error)) {
      console.log('请求已被取消:', error.message)
      return
    }
    
    console.error('API调用失败:', error)
    
    let errorMessage = '发送失败'
    
    if (error.code === 'ECONNREFUSED') {
      errorMessage = '无法连接到后端服务'
      connectionStatus.value = 'disconnected'
    } else if (error.response) {
      errorMessage = `服务器错误: ${error.response.status}`
    } else if (error.request) {
      errorMessage = '网络请求超时'
      connectionStatus.value = 'disconnected'
    } else {
      errorMessage = `请求错误: ${error.message}`
    }
    
    // 标记错误消息
    const errorResponse: ChatMessage = {
      role: 'assistant',
      content: `## ❌ 请求失败\n\n**错误信息**: ${errorMessage}\n\n请检查网络连接或稍后重试。`,
      timestamp: getCurrentTime(),
      isError: true,
      id: generateId()
    }
    messages.value.push(errorResponse)
    
    ElMessage.error(errorMessage)
  } finally {
    loading.value = false
    cancelTokenSource.value = null
    scrollToBottom()
  }
}

// 重试消息
function retryMessage(index: number) {
  const errorMessage = messages.value[index]
  if (errorMessage && errorMessage.isError) {
    // 移除错误消息
    messages.value.splice(index, 1)
    // 重新发送上一条用户消息
    const lastUserMsg = messages.value[messages.value.length - 1]
    if (lastUserMsg && lastUserMsg.role === 'user') {
      inputMessage.value = lastUserMsg.content
      nextTick(() => {
        sendMessage()
      })
    }
  }
}

// 编辑并重新发送
function editAndResend(index: number) {
  const errorMessage = messages.value[index]
  if (errorMessage && errorMessage.isError) {
    // 找到上一条用户消息
    const lastUserMsgIndex = lastUserMessageIndex.value
    if (lastUserMsgIndex !== -1) {
      editingIndex.value = lastUserMsgIndex
      editingMessage.value = messages.value[lastUserMsgIndex].content
      editDialogVisible.value = true
    }
  }
}

// 编辑上一条消息
function editLastMessage() {
  if (lastUserMessageIndex.value !== -1) {
    editingIndex.value = lastUserMessageIndex.value
    editingMessage.value = messages.value[lastUserMessageIndex.value].content
    editDialogVisible.value = true
  }
}

// 确认编辑
function confirmEdit() {
  if (editingIndex.value !== -1 && editingMessage.value.trim()) {
    // 移除编辑位置之后的所有消息
    messages.value.splice(editingIndex.value + 1)
    
    // 更新用户消息
    messages.value[editingIndex.value].content = editingMessage.value.trim()
    messages.value[editingIndex.value].timestamp = getCurrentTime()
    
    editDialogVisible.value = false
    editingMessage.value = ''
    
    // 重新发送
    inputMessage.value = messages.value[editingIndex.value].content
    nextTick(() => {
      sendMessage()
    })
  }
}

// 取消编辑
function cancelEdit() {
  editDialogVisible.value = false
  editingMessage.value = ''
  editingIndex.value = -1
}

// 处理编辑对话框关闭
function handleEditDialogClose(done: () => void) {
  if (editingMessage.value.trim() && editingMessage.value !== messages.value[editingIndex.value]?.content) {
    ElMessageBox.confirm('是否保存编辑的内容？', '提示', {
      confirmButtonText: '保存',
      cancelButtonText: '不保存',
      type: 'warning'
    }).then(() => {
      confirmEdit()
      done()
    }).catch(() => {
      cancelEdit()
      done()
    })
  } else {
    cancelEdit()
    done()
  }
}

// 保存对话历史
function saveChatHistory() {
  try {
    const chatData = {
      messages: messages.value,
      savedAt: new Date().toISOString(),
      title: `天津大学材料学科对话 - ${new Date().toLocaleString()}`
    }
    
    const blob = new Blob([JSON.stringify(chatData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `tju-material-chat-${new Date().getTime()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    
    ElMessage.success('对话历史已保存')
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error('保存失败')
  }
}

// 自动保存对话历史
function autoSaveChatHistory() {
  try {
    const chatData = {
      messages: messages.value,
      savedAt: new Date().toISOString(),
      autoSave: true
    }
    localStorage.setItem('tju-material-chat-autosave', JSON.stringify(chatData))
  } catch (error) {
    console.error('自动保存失败:', error)
  }
}

// 加载对话历史
function loadChatHistory() {
  ElMessageBox.confirm('这将替换当前对话，是否继续？', '加载历史对话', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    try {
      const saved = localStorage.getItem('tju-material-chat-autosave')
      if (saved) {
        const chatData = JSON.parse(saved)
        messages.value = chatData.messages
        ElMessage.success('历史对话已加载')
        scrollToBottom()
      } else {
        ElMessage.info('没有找到自动保存的对话历史')
      }
    } catch (error) {
      console.error('加载失败:', error)
      ElMessage.error('加载失败')
    }
  }).catch(() => {
    // 用户取消
  })
}

// 清空对话历史
function clearChatHistory() {
  ElMessageBox.confirm('确定要清空当前对话吗？', '清空对话', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    messages.value = [{
      role: 'assistant',
      content: '对话已清空，我是天津大学材料学科专用AI助手，请问有什么可以帮助您的？',
      timestamp: getCurrentTime(),
      id: generateId()
    }]
    ElMessage.success('对话已清空')
    localStorage.removeItem('tju-material-chat-autosave')
  }).catch(() => {
    // 用户取消
  })
}

// 滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

// 组件挂载时检查连接和加载自动保存
onMounted(async () => {
  scrollToBottom()
  await checkConnection()
  
  // 尝试加载自动保存的对话
  try {
    const saved = localStorage.getItem('tju-material-chat-autosave')
    if (saved) {
      const chatData = JSON.parse(saved)
      if (chatData.messages && chatData.messages.length > 1) {
        ElMessage.info('检测到自动保存的对话历史，可使用"加载历史"按钮恢复')
      }
    }
  } catch (error) {
    console.error('加载自动保存失败:', error)
  }
  
  setInterval(checkConnection, 30000)
})
</script>

<style scoped>
.chat-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.chat-header {
  text-align: center;
  padding: 20px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  color: white;
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
}

.chat-header h1 {
  margin: 0 0 15px 0;
  font-size: 1.8rem;
  font-weight: 600;
}

.header-controls {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.header-controls .el-button {
  margin: 2px;
}

.stop-button {
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.7; }
  100% { opacity: 1; }
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 900px;
  margin: 0 auto;
  width: 100%;
  padding: 20px;
  box-sizing: border-box;
  gap: 20px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 15px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.message {
  display: flex;
  margin-bottom: 24px;
  animation: fadeIn 0.3s ease-in;
}

.message.user {
  flex-direction: row-reverse;
}

.message.user .content {
  background: linear-gradient(135deg, #007bff, #0056b3);
  color: white;
  margin-left: 0;
  margin-right: 12px;
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.3rem;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  flex-shrink: 0;
}

.content {
  max-width: 70%;
  background: #f8f9fa;
  padding: 16px 20px;
  border-radius: 18px;
  margin-left: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  position: relative;
}

.message.user .content {
  background: linear-gradient(135deg, #007bff, #0056b3);
  color: white;
}

.text {
  word-wrap: break-word;
  line-height: 1.5;
  font-size: 0.95rem;
}

.markdown-content {
  word-wrap: break-word;
  line-height: 1.6;
}

.time {
  font-size: 0.75rem;
  opacity: 0.6;
  margin-top: 8px;
  text-align: right;
}

/* 错误消息样式 */
.error-actions {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #ffcdd2;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.retry-button {
  background: linear-gradient(135deg, #4caf50, #45a049);
  border: none;
}

.stop-hint {
  margin-top: 12px;
  text-align: center;
}

.stop-mini-button {
  animation: pulse 1.5s infinite;
}

.status {
  margin: 5px 0 0 0;
  font-size: 0.9rem;
  padding: 4px 12px;
  border-radius: 12px;
  display: inline-block;
}

.status.connected {
  background: rgba(76, 175, 80, 0.2);
  color: #4caf50;
}

.status.disconnected {
  background: rgba(244, 67, 54, 0.2);
  color: #f44336;
}

.status.checking {
  background: rgba(255, 193, 7, 0.2);
  color: #ffc107;
}

.input-container {
  background: rgba(255, 255, 255, 0.95);
  padding: 24px;
  border-radius: 15px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
}

.input-wrapper {
  display: flex;
  gap: 16px;
  align-items: flex-end;
}

.button-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.edit-button {
  font-size: 0.8rem;
  padding: 8px 12px;
}

.send-button {
  height: fit-content;
  padding: 14px 28px;
  border-radius: 10px;
  font-weight: 500;
}

.tips {
  text-align: center;
  margin-top: 12px;
  font-size: 0.85rem;
  color: #666;
}

.typing-indicator {
  display: flex;
  align-items: center;
  height: 24px;
  padding: 8px 0;
}

.typing-indicator span {
  height: 10px;
  width: 10px;
  background: #999;
  border-radius: 50%;
  display: inline-block;
  margin: 0 3px;
  animation: typing 1.2s infinite ease-in-out;
}

.typing-indicator span:nth-child(1) { animation-delay: 0.2s; }
.typing-indicator span:nth-child(2) { animation-delay: 0.4s; }
.typing-indicator span:nth-child(3) { animation-delay: 0.6s; }

@keyframes typing {
  0%, 60%, 100% { 
    transform: translateY(0); 
    opacity: 0.6;
  }
  30% { 
    transform: translateY(-8px); 
    opacity: 1;
  }
}

@keyframes fadeIn {
  from { 
    opacity: 0; 
    transform: translateY(10px); 
  }
  to { 
    opacity: 1; 
    transform: translateY(0); 
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .content {
    max-width: 85%;
  }
  
  .header-controls {
    flex-direction: column;
    align-items: center;
  }
  
  .input-wrapper {
    flex-direction: column;
  }
  
  .button-group {
    flex-direction: row;
    justify-content: space-between;
    width: 100%;
  }
}
</style>

<style>
/* 全局Markdown样式 */
.markdown-content h1,
.markdown-content h2,
.markdown-content h3,
.markdown-content h4,
.markdown-content h5,
.markdown-content h6 {
  margin: 16px 0 8px 0;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-content h1 {
  font-size: 1.5em;
  border-bottom: 1px solid #eaecef;
  padding-bottom: 8px;
}

.markdown-content h2 {
  font-size: 1.3em;
}

.markdown-content h3 {
  font-size: 1.1em;
}

.markdown-content p {
  margin: 8px 0;
  line-height: 1.6;
}

.markdown-content ul,
.markdown-content ol {
  padding-left: 24px;
  margin: 8px 0;
}

.markdown-content li {
  margin: 4px 0;
}

.markdown-content blockquote {
  margin: 16px 0;
  padding: 8px 16px;
  background: #f8f9fa;
  border-left: 4px solid #007bff;
  border-radius: 4px;
}

.markdown-content code {
  background: #f1f3f4;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 0.9em;
}

.markdown-content pre {
  background: #f8f9fa;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 16px 0;
  border: 1px solid #e9ecef;
}

.markdown-content pre code {
  background: none;
  padding: 0;
}

.markdown-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0;
}

.markdown-content th,
.markdown-content td {
  padding: 8px 12px;
  border: 1px solid #dee2e6;
}

.markdown-content th {
  background: #f8f9fa;
  font-weight: 600;
}

.markdown-content tr:nth-child(even) {
  background: #f8f9fa;
}

.markdown-content a {
  color: #007bff;
  text-decoration: none;
}

.markdown-content a:hover {
  text-decoration: underline;
}

.markdown-content strong {
  font-weight: 600;
}

.markdown-content em {
  font-style: italic;
}
</style>