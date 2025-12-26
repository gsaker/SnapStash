'use client';

import { useState, useEffect, useRef } from 'react';
import { ArrowLeft, MoreVertical, Users, MessageCircle, RefreshCw, Download, X } from 'lucide-react';
import { Conversation, Message, MessagesResponse, ConversationWithMessages } from '../types/api';
import { api } from '../utils/api';
import { getInitials, formatTimestamp } from '../utils/helpers';
import MessageBubble from './MessageBubble';
import Avatar from './Avatar';

interface ChatViewProps {
  conversation: Conversation | null;
  onBack: () => void;
  currentUserId?: string;
  isMobile: boolean;
}

export default function ChatView({ conversation, onBack, currentUserId, isMobile }: ChatViewProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationDetails, setConversationDetails] = useState<ConversationWithMessages | null>(null);
  const [hasMoreMessages, setHasMoreMessages] = useState(true);
  const [offset, setOffset] = useState(0);
  const [showExportModal, setShowExportModal] = useState(false);
  const [exportStartDate, setExportStartDate] = useState('');
  const [exportEndDate, setExportEndDate] = useState('');
  const [includeMedia, setIncludeMedia] = useState(true);
  const [simplifiedFormat, setSimplifiedFormat] = useState(false);
  const [exporting, setExporting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messagesContainerRef = useRef<HTMLDivElement>(null);
  const prevScrollHeightRef = useRef<number>(0);
  const isInitialLoadRef = useRef<boolean>(false);
  const currentConversationIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (conversation) {
      // Store the current conversation ID for race condition prevention
      currentConversationIdRef.current = conversation.id;

      // Reset state when conversation changes
      setMessages([]);
      setOffset(0);
      setHasMoreMessages(true);
      setLoading(false);
      setLoadingMore(false);
      isInitialLoadRef.current = true;
      fetchConversationData(true);
    }
  }, [conversation?.id]);

  useEffect(() => {
    // Set up scroll listener for pagination
    const container = messagesContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      // Check if scrolled to top
      if (container.scrollTop === 0 && !loadingMore && hasMoreMessages) {
        loadMoreMessages();
      }
    };

    container.addEventListener('scroll', handleScroll);
    return () => container.removeEventListener('scroll', handleScroll);
  }, [loadingMore, hasMoreMessages, offset]);

  const scrollToBottom = (smooth: boolean = true) => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
    }
  };

  // Handle image load events to scroll after images load (only on initial load)
  useEffect(() => {
    if (messages.length === 0 || loading || loadingMore || !isInitialLoadRef.current) return;

    const container = messagesContainerRef.current;
    if (!container) return;

    // Find all images in the container
    const images = container.querySelectorAll('img');
    let loadedCount = 0;
    const totalImages = images.length;

    if (totalImages === 0) {
      // No images, just scroll
      scrollToBottom(true);
      isInitialLoadRef.current = false; // Reset after scrolling
      return;
    }

    const handleImageLoad = () => {
      loadedCount++;
      if (loadedCount === totalImages) {
        // All images loaded, scroll to bottom
        scrollToBottom(false); // Use instant scroll since images just loaded
        isInitialLoadRef.current = false; // Reset after scrolling
      }
    };

    images.forEach((img) => {
      if (img.complete) {
        // Image already loaded
        handleImageLoad();
      } else {
        // Wait for image to load
        img.addEventListener('load', handleImageLoad);
        img.addEventListener('error', handleImageLoad); // Count errors too
      }
    });

    // Cleanup
    return () => {
      images.forEach((img) => {
        img.removeEventListener('load', handleImageLoad);
        img.removeEventListener('error', handleImageLoad);
      });
    };
  }, [messages, loading, loadingMore]);

  const fetchConversationData = async (isInitialLoad: boolean = false) => {
    if (!conversation) return;

    const conversationId = conversation.id;

    try {
      setLoading(true);
      setError(null);

      // Fetch conversation details and initial messages (most recent 100)
      const [detailsResponse, messagesResponse] = await Promise.all([
        api.getConversation(conversationId, true, 100),
        api.getMessages({ conversation_id: conversationId, limit: 100, offset: 0 })
      ]) as [ConversationWithMessages, MessagesResponse];

      // Check if the conversation changed while we were fetching
      if (currentConversationIdRef.current !== conversationId) {
        console.log('Conversation changed during fetch, ignoring results');
        return;
      }

      setConversationDetails(detailsResponse);
      // Messages come in newest-first order, so reverse them for display (oldest to newest)
      const reversedMessages = [...(messagesResponse.messages || [])].reverse();

      // Debug: Check for duplicates in API response
      const messageIds = reversedMessages.map(m => m.id);
      const uniqueIds = new Set(messageIds);
      if (messageIds.length !== uniqueIds.size) {
        console.warn('Duplicate messages detected in API response!', {
          total: messageIds.length,
          unique: uniqueIds.size,
          conversationId
        });
      }

      setMessages(reversedMessages);
      setOffset(messagesResponse.messages?.length || 0);
      setHasMoreMessages(messagesResponse.messages?.length === 100);

      // Immediately try to scroll to bottom after setting messages
      setTimeout(() => {
        scrollToBottom(false);
      }, 100);
    } catch (err) {
      // Only set error if still on the same conversation
      if (currentConversationIdRef.current === conversationId) {
        setError(err instanceof Error ? err.message : 'Failed to load conversation');
      }
    } finally {
      // Only update loading state if still on the same conversation
      if (currentConversationIdRef.current === conversationId) {
        setLoading(false);
      }
    }
  };

  const loadMoreMessages = async () => {
    if (!conversation || loadingMore || !hasMoreMessages) return;

    const conversationId = conversation.id;

    try {
      setLoadingMore(true);
      const container = messagesContainerRef.current;
      if (container) {
        prevScrollHeightRef.current = container.scrollHeight;
      }

      const messagesResponse = await api.getMessages({
        conversation_id: conversationId,
        limit: 100,
        offset: offset
      }) as MessagesResponse;

      // Check if the conversation changed while we were fetching
      if (currentConversationIdRef.current !== conversationId) {
        console.log('Conversation changed during load more, ignoring results');
        return;
      }

      if (messagesResponse.messages && messagesResponse.messages.length > 0) {
        // Reverse new messages and prepend to existing messages
        const reversedNewMessages = [...messagesResponse.messages].reverse();
        setMessages(prev => [...reversedNewMessages, ...prev]);
        setOffset(prev => prev + messagesResponse.messages.length);
        setHasMoreMessages(messagesResponse.messages.length === 100);

        // Maintain scroll position after adding messages
        setTimeout(() => {
          if (container) {
            const newScrollHeight = container.scrollHeight;
            container.scrollTop = newScrollHeight - prevScrollHeightRef.current;
          }
        }, 0);
      } else {
        setHasMoreMessages(false);
      }
    } catch (err) {
      console.error('Failed to load more messages:', err);
    } finally {
      // Only update loading state if still on the same conversation
      if (currentConversationIdRef.current === conversationId) {
        setLoadingMore(false);
      }
    }
  };

  const handleRefresh = () => {
    setMessages([]);
    setOffset(0);
    setHasMoreMessages(true);
    isInitialLoadRef.current = true;
    fetchConversationData(true);
  };

  const handleExport = async () => {
    if (!conversation) return;

    try {
      setExporting(true);

      // Build query parameters
      const params = new URLSearchParams();
      if (exportStartDate) {
        params.append('since', new Date(exportStartDate).toISOString());
      }
      if (exportEndDate) {
        params.append('until', new Date(exportEndDate).toISOString());
      }
      if (!simplifiedFormat) {
        params.append('include_media', includeMedia.toString());
      }
      params.append('simplified', simplifiedFormat.toString());

      // Fetch the export data
      const response = await fetch(`/api/messages/export/${conversation.id}?${params.toString()}`);

      if (!response.ok) {
        throw new Error('Failed to export conversation');
      }

      // Get the JSON data
      const data = await response.json();

      // Create a blob and download it
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;

      // Generate filename
      const dateSuffix = exportStartDate || exportEndDate
        ? `_${exportStartDate || 'beginning'}_to_${exportEndDate || 'now'}`
        : '';
      a.download = `chat_export_${conversation.id}${dateSuffix}.json`;

      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      // Close modal and reset
      setShowExportModal(false);
      setExportStartDate('');
      setExportEndDate('');
      setIncludeMedia(true);
      setSimplifiedFormat(false);
    } catch (err) {
      console.error('Export failed:', err);
      alert('Failed to export conversation. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  if (!conversation) {
    return (
      <div className="flex-1 flex items-center justify-center bg-gray-50 dark:bg-gray-800">
        <div className="text-center">
          <MessageCircle className="w-16 h-16 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">Select a conversation</h3>
          <p className="text-gray-500 dark:text-gray-400">Choose a conversation from the list to start viewing messages</p>
        </div>
      </div>
    );
  }

  const getConversationAvatar = () => {
    // For group chats with participant avatars
    if (conversation.is_group_chat && conversation.avatar?.participants) {
      return (
        <Avatar
          isGroupChat={true}
          groupParticipants={conversation.avatar.participants}
          name={conversation.group_name}
          size="md"
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
          size="md"
        />
      );
    }

    // Fallback to initials
    const initials = getInitials(conversation.group_name || 'Unknown');
    const bgColor = conversation.is_group_chat
      ? 'bg-blue-500'
      : 'bg-green-500';

    return (
      <div className={`w-10 h-10 rounded-full ${bgColor} flex items-center justify-center text-white font-semibold text-sm flex-shrink-0`}>
        {initials}
      </div>
    );
  };

  const getConversationInfo = () => {
    if (conversationDetails?.statistics) {
      const stats = conversationDetails.statistics;
      return `${stats.total_messages} messages • ${stats.text_messages} text • ${stats.media_messages} media`;
    }
    return conversation.is_group_chat 
      ? `${conversation.participant_count || 0} participants`
      : 'Direct message';
  };

  // Group messages by date
  const groupMessagesByDate = (messages: Message[]) => {
    const groups: { [date: string]: Message[] } = {};

    // Deduplicate messages by ID first
    const uniqueMessages = messages.reduce((acc, message) => {
      if (!acc.find(m => m.id === message.id)) {
        acc.push(message);
      }
      return acc;
    }, [] as Message[]);

    uniqueMessages.forEach(message => {
      const date = new Date(message.creation_timestamp).toDateString();
      if (!groups[date]) {
        groups[date] = [];
      }
      groups[date].push(message);
    });

    return Object.entries(groups).sort(([a], [b]) =>
      new Date(a).getTime() - new Date(b).getTime()
    );
  };

  // Group consecutive messages from same sender with same time
  const groupConsecutiveMessages = (messages: Message[]) => {
    const groups: Array<{
      messages: Message[];
      senderId: string;
      timestamp: string;
      isOwn: boolean;
    }> = [];

    messages.forEach((message) => {
      const messageTime = formatTimestamp(message.creation_timestamp);
      const isOwn = currentUserId ? message.sender_id === currentUserId : false;
      const lastGroup = groups[groups.length - 1];

      // Check if we can add to the existing group
      if (
        lastGroup &&
        lastGroup.senderId === message.sender_id &&
        lastGroup.timestamp === messageTime
      ) {
        lastGroup.messages.push(message);
      } else {
        // Create a new group
        groups.push({
          messages: [message],
          senderId: message.sender_id,
          timestamp: messageTime,
          isOwn,
        });
      }
    });

    return groups;
  };

  const groupedMessages = groupMessagesByDate(messages);

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-800">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <div className="flex items-center space-x-3">
          {isMobile && (
            <button
              onClick={onBack}
              className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg -ml-2"
            >
              <ArrowLeft className="w-5 h-5 text-gray-900 dark:text-gray-100" />
            </button>
          )}

          {getConversationAvatar()}

          <div className="flex-1 min-w-0">
            <div className="flex items-center space-x-2">
              <h2 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                {conversation.group_name || 'Unknown'}
              </h2>
              {conversation.is_group_chat ? (
                <Users className="w-4 h-4 text-gray-400 dark:text-gray-500" />
              ) : (
                <MessageCircle className="w-4 h-4 text-gray-400 dark:text-gray-500" />
              )}
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
              {getConversationInfo()}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowExportModal(true)}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
            title="Export conversation"
          >
            <Download className="w-5 h-5 text-gray-900 dark:text-gray-100" />
          </button>

          <button
            onClick={handleRefresh}
            disabled={loading}
            className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50"
            title="Refresh messages"
          >
            <RefreshCw className={`w-5 h-5 text-gray-900 dark:text-gray-100 ${loading ? 'animate-spin' : ''}`} />
          </button>

          <button className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
            <MoreVertical className="w-5 h-5 text-gray-900 dark:text-gray-100" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div ref={messagesContainerRef} className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50 dark:bg-gray-900">
        {loading && messages.length === 0 && (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-500"></div>
          </div>
        )}

        {error && (
          <div className="text-center text-red-600 dark:text-red-400 py-8">
            <p>{error}</p>
            <button
              onClick={handleRefresh}
              className="mt-2 text-yellow-600 dark:text-yellow-400 hover:text-yellow-700 dark:hover:text-yellow-300 font-medium"
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !error && messages.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 py-8">
            <MessageCircle className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-4" />
            <p>No messages in this conversation yet</p>
          </div>
        )}

        {/* Loading more indicator at top */}
        {loadingMore && (
          <div className="flex items-center justify-center py-4">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-yellow-500"></div>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">Loading older messages...</span>
          </div>
        )}

        {/* Show "no more messages" indicator when at the end */}
        {!loading && !loadingMore && !hasMoreMessages && messages.length > 0 && (
          <div className="flex items-center justify-center py-4">
            <span className="text-xs text-gray-400 dark:text-gray-500">No more messages</span>
          </div>
        )}
        
        {groupedMessages.map(([date, dateMessages]) => (
          <div key={date}>
            {/* Date separator */}
            <div className="flex items-center justify-center py-4">
              <div className="bg-gray-100 dark:bg-gray-800 rounded-full px-3 py-1">
                <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                  {new Date(date).toLocaleDateString(undefined, {
                    weekday: 'long',
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                  })}
                </span>
              </div>
            </div>
            
            {/* Messages for this date */}
            {groupConsecutiveMessages(dateMessages).map((group, groupIndex) => {
              const showSender = conversation.is_group_chat && !group.isOwn;

              return (
                <MessageBubble
                  key={`${group.senderId}-${group.timestamp}-${groupIndex}`}
                  messages={group.messages}
                  isOwn={group.isOwn}
                  showSender={showSender}
                  currentUserId={currentUserId}
                />
              );
            })}
          </div>
        ))}
        
        <div ref={messagesEndRef} />
      </div>
      
      {/* Input area (placeholder) */}
      <div className="border-t border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800">
        <div className="bg-white dark:bg-gray-900 rounded-lg border border-gray-300 dark:border-gray-600 px-4 py-3">
          <p className="text-gray-500 dark:text-gray-400 text-sm">
            This is a read-only view of extracted Snapchat messages
          </p>
        </div>
      </div>

      {/* Export Modal */}
      {showExportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Export Conversation
              </h3>
              <button
                onClick={() => setShowExportModal(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              >
                <X className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-4">
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Export all messages from this conversation as a JSON file.
              </p>

              {/* Date Range Section */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Date Range (Optional)
                </label>

                <div>
                  <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={exportStartDate}
                    onChange={(e) => setExportStartDate(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                  />
                </div>

                <div>
                  <label className="block text-xs text-gray-600 dark:text-gray-400 mb-1">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={exportEndDate}
                    onChange={(e) => setExportEndDate(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-yellow-500"
                  />
                </div>

                {exportStartDate || exportEndDate ? (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    {exportStartDate && exportEndDate
                      ? `Exporting messages from ${exportStartDate} to ${exportEndDate}`
                      : exportStartDate
                      ? `Exporting messages from ${exportStartDate} onwards`
                      : `Exporting messages up to ${exportEndDate}`}
                  </p>
                ) : (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    Leave empty to export all messages
                  </p>
                )}
              </div>

              {/* Export Format Options */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                  Export Format
                </label>

                {/* Simplified Format Radio */}
                <div className="flex items-start">
                  <input
                    type="radio"
                    id="simplifiedFormat"
                    name="exportFormat"
                    checked={simplifiedFormat}
                    onChange={() => setSimplifiedFormat(true)}
                    className="mt-1 h-4 w-4 text-yellow-500 focus:ring-yellow-500 border-gray-300 dark:border-gray-600"
                  />
                  <label htmlFor="simplifiedFormat" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
                    Simplified (Compact)
                    <span className="block text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Only text, timestamps, and sender IDs. Participant info listed once at the top.
                    </span>
                  </label>
                </div>

                {/* Full Format Radio */}
                <div className="flex items-start">
                  <input
                    type="radio"
                    id="fullFormat"
                    name="exportFormat"
                    checked={!simplifiedFormat}
                    onChange={() => setSimplifiedFormat(false)}
                    className="mt-1 h-4 w-4 text-yellow-500 focus:ring-yellow-500 border-gray-300 dark:border-gray-600"
                  />
                  <label htmlFor="fullFormat" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
                    Full (Complete)
                    <span className="block text-xs text-gray-500 dark:text-gray-400 mt-1">
                      All message metadata, IDs, parsing info, and sender details on each message.
                    </span>
                  </label>
                </div>
              </div>

              {/* Include Media Checkbox - Only show for full format */}
              {!simplifiedFormat && (
                <div className="flex items-start">
                  <input
                    type="checkbox"
                    id="includeMedia"
                    checked={includeMedia}
                    onChange={(e) => setIncludeMedia(e.target.checked)}
                    className="mt-1 h-4 w-4 text-yellow-500 focus:ring-yellow-500 border-gray-300 dark:border-gray-600 rounded"
                  />
                  <label htmlFor="includeMedia" className="ml-2 block text-sm text-gray-700 dark:text-gray-300">
                    Include media asset details
                    <span className="block text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Include file paths, hashes, and metadata for images, videos, and audio
                    </span>
                  </label>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end space-x-3 p-6 border-t border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setShowExportModal(false)}
                disabled={exporting}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleExport}
                disabled={exporting}
                className="px-4 py-2 text-sm font-medium text-white bg-yellow-500 hover:bg-yellow-600 rounded-lg disabled:opacity-50 flex items-center space-x-2"
              >
                {exporting ? (
                  <>
                    <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                    <span>Exporting...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    <span>Export</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
