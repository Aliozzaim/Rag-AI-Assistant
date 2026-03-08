<template>
  <div class="chat-app">
    <div class="chat-container">
      <!-- Header -->
      <div class="chat-header">
        <h1>
          <span class="header-icon">🤖</span>
          AI Assistant
        </h1>
        <div class="status">
          <span class="status-dot" :class="{ online: isOnline }"></span>
          <span>{{ isOnline ? "Online" : "Offline" }}</span>
        </div>
      </div>

      <!-- Messages Area -->
      <div class="chat-messages" ref="messagesContainer">
        <div v-if="messages.length === 0" class="welcome-message">
          <h2>👋 Welcome!</h2>
          <p>Ask me anything about your project, APIs, or documentation.</p>
          <p class="subtitle">
            I remember our conversation, so feel free to ask follow-up
            questions!
          </p>
        </div>

        <ChatMessage
          v-for="(message, index) in messages"
          :key="index"
          :message="message"
        />

        <div v-if="isLoading" class="message assistant loading">
          <div class="message-avatar">AI</div>
          <div class="message-content">
            <hds-spinner size="small"></hds-spinner>
          </div>
        </div>
      </div>

      <!-- Input Area -->
      <div class="chat-input-area">
        <div class="input-wrapper">
          <hds-textarea
            :value="inputMessage"
            @textarea-value="updateInputMessage"
            type="text"
            name="chat-input"
            @keydown.enter.exact.prevent="sendMessage"
            @keydown.shift.enter.exact="handleShiftEnter"
            placeholder="Type your message here..."
            class="chat-input"
            :disabled="isLoading"
            ref="inputRef"
          ></hds-textarea>
          <hds-button
            @click="sendMessage"
            :disabled="isButtonDisabled"
            variant="primary"
            class="send-button"
            type="button"
          >
            <template v-if="!isLoading">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                ></path>
              </svg>
            </template>
            <hds-spinner v-else size="small"></hds-spinner>
          </hds-button>
        </div>
        <hds-section-message v-if="error" variant="error" class="error-banner">
          {{ error }}
        </hds-section-message>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from "vue";
import { chatService } from "./services/api.js";
import ChatMessage from "./components/ChatMessage.vue";

const messages = ref([]);
const inputMessage = ref("");
const isLoading = ref(false);
const error = ref(null);
const isOnline = ref(true);
const messagesContainer = ref(null);
const inputRef = ref(null);
const conversationId = ref(`chat_${Date.now()}`);

// Computed property for button disabled state
const isButtonDisabled = computed(() => {
  const hasText = inputMessage.value && inputMessage.value.trim().length > 0;
  return !hasText || isLoading.value;
});

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
    }
  });
};

const handleShiftEnter = () => {
  // Allow new line with Shift+Enter
};

const updateInputMessage = (value) => {
  // HDS textarea emits 'textareaValue' event with the value directly
  inputMessage.value = value || "";

  // Auto-resize textarea after input
  nextTick(() => {
    if (inputRef.value) {
      // Find the actual textarea element inside HDS component
      const textarea =
        inputRef.value.$el?.querySelector("textarea") ||
        inputRef.value.querySelector?.("textarea");
      if (textarea && textarea.tagName === "TEXTAREA") {
        textarea.style.height = "auto";
        textarea.style.height =
          Math.min(textarea.scrollHeight || 48, 120) + "px";
      }
    }
  });
};

const focusInput = () => {
  nextTick(() => {
    if (inputRef.value) {
      // HDS components might expose focus method or need to find internal textarea
      if (typeof inputRef.value.focus === "function") {
        inputRef.value.focus();
      } else {
        // Try to find and focus the actual textarea element
        const textarea =
          inputRef.value.$el?.querySelector("textarea") ||
          inputRef.value.querySelector?.("textarea");
        if (textarea && typeof textarea.focus === "function") {
          textarea.focus();
        }
      }
    }
  });
};

const sendMessage = async () => {
  const message = inputMessage.value.trim();
  if (!message || isLoading.value) return;

  // Add user message
  messages.value.push({
    role: "user",
    content: message,
    sources: [],
  });

  // Clear input
  inputMessage.value = "";
  error.value = null;
  isLoading.value = true;
  scrollToBottom();

  const result = await chatService.askQuestion(message, conversationId.value);

  if (result.success) {
    // Add assistant response
    messages.value.push({
      role: "assistant",
      content: result.data.answer,
      sources: result.data.sources || [],
    });
    isOnline.value = true;
  } else {
    error.value = result.error;
    isOnline.value = false;
    console.error("Error:", result.error);
  }

  isLoading.value = false;
  scrollToBottom();
  focusInput();
};

onMounted(() => {
  focusInput();
});
</script>

<style scoped>
.chat-app {
  width: 100%;
  max-width: 900px;
  height: 90vh;
}

.chat-container {
  background: white;
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.chat-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 20px 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
}

.chat-header h1 {
  font-size: 24px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  font-size: 28px;
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #ef4444;
  transition: background 0.3s;
}

.status-dot.online {
  background: #4ade80;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 30px;
  background: #f8f9fa;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.chat-messages::-webkit-scrollbar {
  width: 6px;
}

.chat-messages::-webkit-scrollbar-track {
  background: #f1f1f1;
}

.chat-messages::-webkit-scrollbar-thumb {
  background: #888;
  border-radius: 3px;
}

.chat-messages::-webkit-scrollbar-thumb:hover {
  background: #555;
}

.welcome-message {
  text-align: center;
  color: #6b7280;
  padding: 40px 20px;
}

.welcome-message h2 {
  color: #667eea;
  margin-bottom: 10px;
  font-size: 28px;
}

.welcome-message p {
  margin-top: 8px;
  font-size: 15px;
}

.welcome-message .subtitle {
  font-size: 13px;
  color: #9ca3af;
}

.loading .message-content {
  padding: 12px 18px;
}

.loading-dots {
  display: flex;
  gap: 6px;
}

.loading-dots span {
  width: 8px;
  height: 8px;
  background: #667eea;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.loading-dots span:nth-child(1) {
  animation-delay: -0.32s;
}
.loading-dots span:nth-child(2) {
  animation-delay: -0.16s;
}

@keyframes bounce {
  0%,
  80%,
  100% {
    transform: scale(0);
  }
  40% {
    transform: scale(1);
  }
}

.chat-input-area {
  padding: 20px 30px;
  background: white;
  border-top: 1px solid #e5e7eb;
  width: 100%;
}

.input-wrapper {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  width: 100%;
}

.chat-input {
  flex: 1;
  width: 100%;
  resize: none;
  max-height: 120px;
  min-width: 0; /* Allow flex item to shrink */
}

/* Make HDS textarea and its internal elements full width */
.chat-input :deep(textarea),
.chat-input :deep(.hds-textarea),
.chat-input :deep(.hds-textarea textarea),
.chat-input :deep(.hds-textarea-wrapper),
.chat-input :deep(.hds-textarea-wrapper textarea) {
  width: 100% !important;
  min-width: 0;
  box-sizing: border-box;
}

.send-button {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  min-width: 48px;
}

.send-button:hover:not(:disabled) {
  transform: scale(1.05);
}

.send-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-banner {
  margin-top: 12px;
}
</style>
