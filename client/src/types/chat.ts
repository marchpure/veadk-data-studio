export type ImageMimeType = "image/png" | "image/jpeg" | "image/webp"

export interface MessageAttachment {
  file_name: string
  mime_type: string
  file_data: string
}

export interface ImageAttachment {
  file_name: string
  mime_type: ImageMimeType
  file_data: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  timestamp: Date
  attachments?: MessageAttachment[]
}

export interface QueuedMessage {
  id: string
  content: string
  attachments?: ImageAttachment[]
  timestamp: Date
}