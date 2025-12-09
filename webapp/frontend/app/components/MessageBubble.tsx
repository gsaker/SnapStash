'use client';

import { useState } from 'react';
import { Download, Image as ImageIcon, Video, FileText, Eye } from 'lucide-react';
import { Message } from '../types/api';
import { formatTimestamp, formatFileSize, getInitials, decodeHtmlEntities } from '../utils/helpers';
import { api } from '../utils/api';
import { EnhancedAudioPlayer } from './EnhancedAudioPlayer';
import { EnhancedVideoPlayer } from './EnhancedVideoPlayer';

interface MessageBubbleProps {
  messages: Message[];
  isOwn: boolean;
  showSender?: boolean;
  currentUserId?: string;
}

// Separate component for image rendering to maintain independent state per image
function MediaImage({ mediaUrl, fileName, fileSize, mimeType }: {
  mediaUrl: string;
  fileName?: string;
  fileSize?: number;
  mimeType?: string;
}) {
  const [imageError, setImageError] = useState(false);
  const [imageLoading, setImageLoading] = useState(true);

  return (
    <div className="relative max-w-xs">
      {imageLoading && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-100 dark:bg-gray-700 rounded-lg">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-gray-400 dark:border-gray-500"></div>
        </div>
      )}
      {!imageError ? (
        <img
          key={mediaUrl}
          src={mediaUrl}
          alt="Shared image"
          className={`rounded-lg max-w-full h-auto cursor-pointer hover:opacity-90 transition-opacity ${
            imageLoading ? 'opacity-0' : 'opacity-100'
          }`}
          onLoad={() => setImageLoading(false)}
          onError={() => {
            setImageError(true);
            setImageLoading(false);
          }}
          onClick={() => window.open(mediaUrl, '_blank')}
        />
      ) : (
        <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-4 flex items-center space-x-3">
          <ImageIcon className="w-8 h-8 text-gray-400 dark:text-gray-500" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
              {fileName || 'Image'}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {fileSize ? formatFileSize(fileSize) : 'Unknown size'} • {mimeType || 'Unknown type'}
            </p>
          </div>
          <div className="flex space-x-1">
            <button
              onClick={() => window.open(mediaUrl, '_blank')}
              className="p-1 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
              title="View"
            >
              <Eye className="w-4 h-4" />
            </button>
            <a
              href={mediaUrl}
              download
              className="p-1 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
              title="Download"
            >
              <Download className="w-4 h-4" />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

export default function MessageBubble({ messages, isOwn, showSender = true, currentUserId }: MessageBubbleProps) {
  // For backward compatibility, if a single message is passed, wrap it in an array
  const messageArray = Array.isArray(messages) ? messages : [messages];
  const firstMessage = messageArray[0];

  const getMessageContent = (message: Message) => {
    // Text message
    if (message.content_type === 1 && message.text) {
      return (
        <div className="whitespace-pre-wrap break-words">
          {decodeHtmlEntities(message.text)}
        </div>
      );
    }

    // Media message
    if (message.content_type === 0 && message.media_asset) {
      return renderMediaContent(message);
    }

    // Mixed message (text + media)
    if (message.content_type === 2) {
      return (
        <div className="space-y-2">
          {message.text && (
            <div className="whitespace-pre-wrap break-words">
              {decodeHtmlEntities(message.text)}
            </div>
          )}
          {message.media_asset && renderMediaContent(message)}
        </div>
      );
    }

    // Video/Audio message (content type 4)
    if (message.content_type === 4 && message.media_asset) {
      return renderMediaContent(message);
    }

    // Cache ID only (no direct media asset)
    if (message.cache_id) {
      return (
        <div className="flex items-center space-x-2 text-sm">
          <FileText className="w-4 h-4" />
          <span>Media (ID: {message.cache_id})</span>
        </div>
      );
    }

    return (
      <div className="text-sm italic text-gray-500 dark:text-gray-400">
        [Message content not available]
      </div>
    );
  };

  const renderMediaContent = (message: Message) => {
    if (!message.media_asset) return null;

    const { media_asset } = message;
    const mediaUrl = api.getMediaUrl(media_asset.id);

    if (media_asset.file_type === 'image') {
      return (
        <MediaImage
          mediaUrl={mediaUrl}
          fileName={media_asset.original_filename || undefined}
          fileSize={media_asset.file_size}
          mimeType={media_asset.mime_type || undefined}
        />
      );
    }

    if (media_asset.file_type === 'video') {
      // Check if it's actually audio-only content by checking mime type
      // For now, assume MP4 files in content_type 4 are likely audio messages
      if (media_asset.mime_type && (
        media_asset.mime_type.startsWith('audio/') || 
        (media_asset.mime_type === 'video/mp4' && message.content_type === 4)
      )) {
        return (
          <EnhancedAudioPlayer
            src={mediaUrl}
            isOwn={isOwn}
            fileName={media_asset.original_filename || 'Audio Message'}
            fileSize={media_asset.file_size}
            mimeType={media_asset.mime_type}
          />
        );
      }

      // Regular video content
      return (
        <EnhancedVideoPlayer
          src={mediaUrl}
          isOwn={isOwn}
          fileName={media_asset.original_filename || 'Video'}
          fileSize={media_asset.file_size}
          mimeType={media_asset.mime_type}
        />
      );
    }

    if (media_asset.file_type === 'audio') {
      return (
        <EnhancedAudioPlayer
          src={mediaUrl}
          isOwn={isOwn}
          fileName={media_asset.original_filename || 'Audio Message'}
          fileSize={media_asset.file_size}
          mimeType={media_asset.mime_type}
        />
      );
    }

    // Other file types
    return (
      <div className="bg-gray-100 dark:bg-gray-700 rounded-lg p-3 flex items-center space-x-3 max-w-xs">
        <div className="flex-shrink-0">
          {media_asset.file_type === 'video' ? (
            <Video className="w-6 h-6 text-gray-400 dark:text-gray-500" />
          ) : (
            <FileText className="w-6 h-6 text-gray-400 dark:text-gray-500" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {media_asset.original_filename || `${media_asset.file_type} file`}
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {formatFileSize(media_asset.file_size)} • {media_asset.mime_type}
          </p>
        </div>
        <div className="flex space-x-1">
          <button
            onClick={() => window.open(mediaUrl, '_blank')}
            className="p-1 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
            title="View"
          >
            <Eye className="w-4 h-4" />
          </button>
          <a
            href={mediaUrl}
            download
            className="p-1 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
            title="Download"
          >
            <Download className="w-4 h-4" />
          </a>
        </div>
      </div>
    );
  };

  const getSenderInfo = () => {
    if (firstMessage.sender) {
      return {
        name: firstMessage.sender.display_name || firstMessage.sender.username,
        initials: getInitials(firstMessage.sender.display_name || firstMessage.sender.username),
      };
    }
    return {
      name: 'Unknown',
      initials: 'UN',
    };
  };

  const senderInfo = getSenderInfo();
  const messageTime = formatTimestamp(firstMessage.creation_timestamp);

  return (
    <div className={`flex ${isOwn ? 'justify-end' : 'justify-start'} mb-4`}>
      <div className={`flex max-w-xs lg:max-w-md ${isOwn ? 'flex-row-reverse' : 'flex-row'} items-start space-x-2`}>
        {/* Avatar */}
        {showSender && !isOwn && (
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gray-300 dark:bg-gray-600 flex items-center justify-center text-white text-xs font-semibold mt-5">
            {senderInfo.initials}
          </div>
        )}

        {/* Message content */}
        <div className={`flex flex-col ${isOwn ? 'items-end' : 'items-start'}`}>
          {/* Sender name (for group chats) - shown at the top */}
          {showSender && !isOwn && (
            <span className="text-xs text-gray-500 dark:text-gray-400 mb-1 px-1">
              {senderInfo.name}
            </span>
          )}

          {/* Message bubbles - render all messages in the group */}
          <div className={`flex flex-col ${isOwn ? 'items-end' : 'items-start'} space-y-1`}>
            {messageArray.map((message, index) => (
              <div
                key={message.id}
                className={`rounded-2xl px-4 py-2 ${
                  isOwn
                    ? 'bg-yellow-500 dark:bg-yellow-600 text-white rounded-br-md'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 rounded-bl-md'
                }`}
              >
                {getMessageContent(message)}
              </div>
            ))}
          </div>

          {/* Timestamp - shown at the bottom */}
          <span className="text-xs text-gray-400 dark:text-gray-500 mt-1 px-1">
            {messageTime}
            {messageArray.some(msg => !msg.parsing_successful) && (
              <span className="text-red-400 dark:text-red-500 ml-1">⚠️</span>
            )}
          </span>
        </div>

        {/* Spacer for own messages */}
        {showSender && isOwn && (
          <div className="flex-shrink-0 w-8 h-8"></div>
        )}
      </div>
    </div>
  );
}
