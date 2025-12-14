// API requests use relative URLs and are proxied through Next.js to the backend
// This allows the backend to be internal-only while the frontend handles all external traffic
const getApiBaseUrl = (): string => {
  // Always use relative URLs - Next.js rewrites will proxy to the backend
  return '';
};

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

async function apiRequest<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const apiBaseUrl = getApiBaseUrl(); // Get URL dynamically on each request
  const url = `${apiBaseUrl}${endpoint}`;

  try {
    const response = await fetch(url, {
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
      ...options,
    });

    if (!response.ok) {
      throw new APIError(response.status, `API request failed: ${response.statusText}`);
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }
    throw new APIError(0, `Network error: ${error instanceof Error ? error.message : 'Unknown error'}`);
  }
}

export const api = {
  // Conversations
  getConversations: async (limit = 50, offset = 0, excludeAds = false) => {
    return apiRequest(`/api/conversations?limit=${limit}&offset=${offset}&exclude_ads=${excludeAds}`);
  },

  getConversation: async (conversationId: string, includeMessages = true, messageLimit = 50) => {
    return apiRequest(`/api/conversations/${conversationId}?include_messages=${includeMessages}&message_limit=${messageLimit}`);
  },

  // Messages
  getMessages: async (params: {
    conversation_id?: string;
    sender_id?: string;
    since?: string;
    until?: string;
    content_type?: number;
    has_media?: boolean;
    limit?: number;
    offset?: number;
  } = {}) => {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        searchParams.append(key, value.toString());
      }
    });
    
    return apiRequest(`/api/messages?${searchParams.toString()}`);
  },

  getMessage: async (messageId: number) => {
    return apiRequest(`/api/messages/${messageId}`);
  },

  // Media
  getMediaUrl: (mediaId: number) => {
    return `${getApiBaseUrl()}/api/media/${mediaId}/file`;
  },

  getMediaByCache: async (cacheId: string) => {
    return apiRequest(`/api/media/by-cache/${cacheId}`);
  },

  // Users
  getUsers: async (search?: string, limit = 50, offset = 0) => {
    const params = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
    if (search) params.append('search', search);
    return apiRequest(`/api/users?${params.toString()}`);
  },

  getUser: async (userId: string) => {
    return apiRequest(`/api/users/${userId}`);
  },

  getCurrentUser: async () => {
    return apiRequest(`/api/users/current`);
  },

  // Health check
  getHealth: async () => {
    return apiRequest('/api/health');
  },

  // Settings
  getSettings: async () => {
    return apiRequest('/api/settings/');
  },

  updateSettings: async (settings: {
    ssh_host?: string;
    ssh_port?: number;
    ssh_user?: string;
    ssh_key_path?: string;
    extract_media?: boolean;
    ingest_timeout_seconds?: number;
    ingest_mode?: string;
    ingest_delay_seconds?: number;
    dm_exclude_name?: string;
    ntfy_enabled?: boolean;
    ntfy_server_url?: string;
    ntfy_media_topic?: string;
    ntfy_text_topic?: string;
    ntfy_username?: string;
    ntfy_password?: string;
    ntfy_auth_token?: string;
    ntfy_priority?: string;
    ntfy_attach_media?: boolean;
    apns_enabled?: boolean;
    apns_key_id?: string;
    apns_team_id?: string;
    apns_bundle_id?: string;
    apns_key_filename?: string;
    apns_use_sandbox?: boolean;
  }) => {
    return apiRequest('/api/settings/', {
      method: 'PUT',
      body: JSON.stringify({ settings }),
    });
  },

  initializeSettings: async () => {
    return apiRequest('/api/settings/initialize', {
      method: 'POST',
    });
  },

  getRawSettings: async (category?: string) => {
    const params = category ? `?category=${category}` : '';
    return apiRequest(`/api/settings/raw${params}`);
  },

  // SSH Key Management
  uploadSshKey: async (file: File) => {
    const apiBaseUrl = getApiBaseUrl();
    const url = `${apiBaseUrl}/api/settings/ssh-key/upload`;

    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch(url, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new APIError(response.status, errorData.detail || 'Upload failed');
    }

    return await response.json();
  },

  getSshKeyInfo: async () => {
    return apiRequest('/api/settings/ssh-key/info');
  },

  deleteSshKey: async () => {
    return apiRequest('/api/settings/ssh-key', {
      method: 'DELETE',
    });
  },
};

export { APIError };
