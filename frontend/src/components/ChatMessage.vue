<template>
  <div class="message" :class="message.role">
    <div class="message-avatar">
      {{ message.role === 'user' ? 'U' : 'AI' }}
    </div>
    <hds-card class="message-content" :variant="message.role === 'user' ? 'primary' : 'default'">
      <div class="message-text" v-html="formatMessage(message.content)"></div>
      <div v-if="message.sources && message.sources.length > 0" class="message-sources">
        <div class="sources-title">📚 Sources:</div>
        <div
          v-for="(source, idx) in message.sources"
          :key="idx"
          class="source-item"
        >
          • {{ source }}
        </div>
      </div>
    </hds-card>
  </div>
</template>

<script setup>
defineProps({
  message: {
    type: Object,
    required: true
  }
})

const formatMessage = (text) => {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>')
    .replace(/\n/g, '<br>')
}
</script>

<style scoped>
.message {
  display: flex;
  gap: 12px;
  animation: slideIn 0.3s ease-out;
  max-width: 80%;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}

.message.assistant {
  align-self: flex-start;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 16px;
  flex-shrink: 0;
  color: white;
}

.message.user .message-avatar {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.message.assistant .message-avatar {
  background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
}

.message-content {
  background: white;
  padding: 12px 18px;
  border-radius: 18px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  line-height: 1.5;
  word-wrap: break-word;
}

.message.user .message-content {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 4px;
}

.message.assistant .message-content {
  background: white;
  color: #333;
  border-bottom-left-radius: 4px;
}

.message-text {
  line-height: 1.6;
}

.message-sources {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.1);
  font-size: 12px;
  color: #666;
}

.message.user .message-sources {
  border-top-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
}

.sources-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.source-item {
  padding: 2px 0;
}
</style>
