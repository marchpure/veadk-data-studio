import type { StateCreator } from 'zustand'
import type { StoreState } from '../useStore'
import type { Message as ChatMessage, QueuedMessage } from '../../types/chat'

export interface Message extends ChatMessage {
  metadata?: Record<string, any>
}

export const MAX_QUEUE_SIZE = 3

export interface ChatSlice {
  // State - per-notebook
  currentMessages: Message[]
  isStreaming: boolean
  streamingMessage: string

  // Per-notebook streaming state
  notebookStreamingState: Record<string, boolean>

  // Message queue state
  messageQueue: QueuedMessage[]

  // Actions
  addMessage: (message: Message) => void
  updateMessage: (messageId: string, content: string) => void
  deleteMessage: (messageId: string) => void
  clearMessages: () => void
  setMessages: (messages: Message[]) => void
  setIsStreaming: (isStreaming: boolean) => void
  setStreamingMessage: (message: string) => void
  appendToStreamingMessage: (chunk: string) => void
  setNotebookStreaming: (notebookId: string, isStreaming: boolean) => void
  getNotebookStreaming: (notebookId: string) => boolean

  // Queue actions
  addToQueue: (message: QueuedMessage) => boolean
  removeFromQueue: (messageId: string) => void
  getNextQueuedMessage: () => QueuedMessage | undefined
  clearQueue: () => void
  isQueueFull: () => boolean
}

export const createChatSlice: StateCreator<
  StoreState,
  [],
  [],
  ChatSlice
> = (set, get) => ({
  // Initial state
  currentMessages: [],
  isStreaming: false,
  streamingMessage: '',
  notebookStreamingState: {},
  messageQueue: [],

  // Actions
  addMessage: (message) =>
    set((state) => ({
      currentMessages: [...state.currentMessages, message],
    })),

  updateMessage: (messageId, content) =>
    set((state) => ({
      currentMessages: state.currentMessages.map((msg) =>
        msg.id === messageId ? { ...msg, content } : msg
      ),
    })),

  deleteMessage: (messageId) =>
    set((state) => ({
      currentMessages: state.currentMessages.filter((msg) => msg.id !== messageId),
    })),

  clearMessages: () =>
    set(() => ({
      currentMessages: [],
      streamingMessage: '',
    })),

  setMessages: (messages) =>
    set(() => ({
      currentMessages: messages,
    })),

  setIsStreaming: (isStreaming) =>
    set(() => ({
      isStreaming,
    })),

  setStreamingMessage: (message) =>
    set(() => ({
      streamingMessage: message,
    })),

  appendToStreamingMessage: (chunk) =>
    set((state) => ({
      streamingMessage: state.streamingMessage + chunk,
    })),

  setNotebookStreaming: (notebookId, isStreaming) =>
    set((state) => ({
      notebookStreamingState: {
        ...state.notebookStreamingState,
        [notebookId]: isStreaming,
      },
    })),

  getNotebookStreaming: (notebookId) => {
    const state = get()
    return state.notebookStreamingState[notebookId] || false
  },

  addToQueue: (message) => {
    const state = get()
    if (state.messageQueue.length >= MAX_QUEUE_SIZE) {
      return false
    }
    set({ messageQueue: [...state.messageQueue, message] })
    return true
  },

  removeFromQueue: (messageId) =>
    set((state) => ({
      messageQueue: state.messageQueue.filter((msg) => msg.id !== messageId),
    })),

  getNextQueuedMessage: () => {
    const state = get()
    return state.messageQueue[0]
  },

  clearQueue: () =>
    set(() => ({
      messageQueue: [],
    })),

  isQueueFull: () => {
    const state = get()
    return state.messageQueue.length >= MAX_QUEUE_SIZE
  },
})