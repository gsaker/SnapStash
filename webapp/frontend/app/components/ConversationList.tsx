'use client';

import { useState, useEffect } from 'react';
import { Users, MessageCircle, Search, ChevronLeft, Sun, Moon, Settings } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Conversation, ConversationsResponse } from '../types/api';
import { api } from '../utils/api';
import { formatTimestamp, getInitials, truncateText } from '../utils/helpers';
import { useTheme } from '../contexts/ThemeContext';
import Avatar from './Avatar';

interface ConversationListProps {
  selectedConversationId: string | null;
  onConversationSelect: (conversation: Conversation) => void;
  isMobile: boolean;
  showList: boolean;
  onBack?: () => void;
}

export default function ConversationList({
  selectedConversationId,
  onConversationSelect,
  isMobile,
  showList,
  onBack
}: ConversationListProps) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const { theme, toggleTheme } = useTheme();
  const router = useRouter();

  useEffect(() => {
    fetchConversations();
  }, []);

  const fetchConversations = async () => {
    try {
      setLoading(true);
      const response = await api.getConversations(100, 0, true) as ConversationsResponse; // true = exclude ads
      setConversations(response.conversations || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  };

  const filteredConversations = conversations.filter(conv =>
    conv.group_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    conv.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getConversationIcon = (conversation: Conversation) => {
    if (conversation.is_group_chat) {
      return <Users className="w-5 h-5" />;
    }
    return <MessageCircle className="w-5 h-5" />;
  };

  const getConversationAvatar = (conversation: Conversation) => {
    // For group chats with participant avatars
    if (conversation.is_group_chat && conversation.avatar?.participants) {
      return (
        <Avatar
          isGroupChat={true}
          groupParticipants={conversation.avatar.participants}
          name={conversation.group_name}
          size="lg"
        />
      );
    }

    // For DMs with avatar info, use the other person's Bitmoji
    if (!conversation.is_group_chat && conversation.avatar) {
      return (
        <Avatar
          user={{
            id: conversation.avatar.user_id || '',
            username: '',
            display_name: conversation.avatar.display_name || '',
            bitmoji_avatar_id: null,
            bitmoji_selfie_id: null,
            bitmoji_url: conversation.avatar.bitmoji_url,
            created_at: '',
            updated_at: ''
          }}
          size="lg"
        />
      );
    }

    // Fallback to initials
    const initials = getInitials(conversation.group_name || 'Unknown');
    const bgColor = conversation.is_group_chat
      ? 'bg-blue-500'
      : 'bg-green-500';

    return (
      <div className={`w-12 h-12 rounded-full ${bgColor} flex items-center justify-center text-white font-semibold text-sm`}>
        {initials}
      </div>
    );
  };

  if (!showList && isMobile) {
    return null;
  }

  return (
    <div className={`${isMobile ? 'fixed inset-0 z-50 bg-white dark:bg-gray-900' : 'w-80'} flex flex-col border-r border-gray-200 dark:border-gray-700 h-full overflow-hidden`}>
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            {isMobile && (
              <button
                onClick={onBack}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              >
                <ChevronLeft className="w-5 h-5 text-gray-900 dark:text-gray-100" />
              </button>
            )}
            <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
              {isMobile ? 'Chats' : 'Conversations'}
            </h1>
          </div>
          <div className="flex items-center space-x-1">
            <button
              onClick={() => router.push('/settings')}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              title="Settings"
            >
              <Settings className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
            <button
              onClick={toggleTheme}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg transition-colors"
              title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            >
              {theme === 'light' ? (
                <Sun className="w-5 h-5 text-yellow-500" />
              ) : (
                <Moon className="w-5 h-5 text-blue-400" />
              )}
            </button>
          </div>
        </div>
        
        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 dark:text-gray-500 w-4 h-4" />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-yellow-500 focus:border-transparent outline-none bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400"
          />
        </div>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden bg-white dark:bg-gray-900">
        {loading && (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-500"></div>
          </div>
        )}

        {error && (
          <div className="p-4 text-center text-red-600 dark:text-red-400">
            <p>{error}</p>
            <button
              onClick={fetchConversations}
              className="mt-2 text-yellow-600 dark:text-yellow-400 hover:text-yellow-700 dark:hover:text-yellow-300 font-medium"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !error && filteredConversations.length === 0 && (
          <div className="p-4 text-center text-gray-500 dark:text-gray-400">
            {searchTerm ? 'No conversations found' : 'No conversations yet'}
          </div>
        )}
        
        {!loading && !error && filteredConversations.map((conversation) => (
          <button
            key={conversation.id}
            onClick={() => onConversationSelect(conversation)}
            className={`w-full p-4 border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors text-left ${
              selectedConversationId === conversation.id
                ? 'bg-yellow-50 dark:bg-yellow-900/20 border-r-4 border-r-yellow-500'
                : ''
            }`}
          >
            <div className="flex items-start space-x-3">
              {getConversationAvatar(conversation)}

              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center space-x-2">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {conversation.group_name || 'Unknown'}
                    </h3>
                    <span className="text-gray-500 dark:text-gray-400">
                      {getConversationIcon(conversation)}
                    </span>
                  </div>
                  <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
                    {formatTimestamp(conversation.last_message_at)}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {conversation.is_group_chat
                      ? `${conversation.participant_count || 0} participants`
                      : 'Direct message'
                    }
                  </p>
                </div>
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
