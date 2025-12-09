export interface User {
  id: string;
  username: string;
  display_name: string;
  created_at: string;
  updated_at: string;
}

export interface Conversation {
  id: string;
  group_name: string;
  is_group_chat: boolean;
  participant_count: number | null;
  last_message_at: string;
  created_at: string;
  updated_at: string;
}

export interface MediaAsset {
  id: number;
  original_filename: string | null;
  file_path: string;
  file_hash: string;
  file_size: number;
  file_type: string;
  mime_type: string;
  cache_key: string;
  cache_id: string;
  category: string;
  timestamp_source: string;
  mapping_method: string | null;
  file_timestamp: string;
  sender_id: string;
  created_at: string;
  updated_at: string;
  sender: User | null;
}

export interface Message {
  id: number;
  text: string | null;
  content_type: number;
  cache_id: string | null;
  creation_timestamp: number;
  read_timestamp: number | null;
  parsing_successful: boolean;
  sender_id: string;
  conversation_id: string;
  server_message_id: string | null;
  client_message_id: string | null;
  media_asset_id: number | null;
  created_at: string;
  updated_at: string;
  sender: User | null;
  media_asset: MediaAsset | null;
}

export interface ConversationWithMessages extends Conversation {
  recent_messages?: Message[];
  statistics?: {
    total_messages: number;
    text_messages: number;
    media_messages: number;
    messages_with_media: number;
  };
}

export interface PaginationInfo {
  total: number;
  limit: number;
  offset: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ConversationsResponse {
  conversations: Conversation[];
  pagination: PaginationInfo;
}

export interface MessagesResponse {
  messages: Message[];
  pagination: PaginationInfo;
}

export interface MediaResponse {
  media: MediaAsset[];
  pagination: PaginationInfo;
}
