import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const API_KEY = import.meta.env.VITE_API_KEY || 'test'

const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY
  }
})

export const chatService = {
  async askQuestion(question, conversationId) {
    try {
      const response = await apiClient.post('/ask', {
        user: 'User',
        question,
        conversation_id: conversationId
      })
      return {
        success: true,
        data: response.data
      }
    } catch (error) {
      return {
        success: false,
        error: error.response?.data?.detail || error.message || 'Failed to send message'
      }
    }
  }
}
