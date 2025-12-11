'use client';

import { useState } from 'react';
import { User, UserAvatar } from '../types/api';

interface AvatarProps {
  user?: User | null;
  name?: string;
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
  isGroupChat?: boolean;
  groupParticipants?: UserAvatar[] | null;
}

const sizeClasses = {
  sm: 'w-8 h-8 text-xs',
  md: 'w-10 h-10 text-sm',
  lg: 'w-12 h-12 text-base',
  xl: 'w-16 h-16 text-lg',
};

// Smaller sizes for stacked group avatars
const stackedSizeClasses = {
  sm: 'w-5 h-5 text-[8px]',
  md: 'w-6 h-6 text-[9px]',
  lg: 'w-7 h-7 text-[10px]',
  xl: 'w-9 h-9 text-xs',
};

function getInitials(name: string | null | undefined): string {
  if (!name) return '?';
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].substring(0, 2).toUpperCase();
  }
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

// Separate component for each participant avatar to ensure proper state isolation
function ParticipantAvatar({
  participant,
  position,
  stackedSize,
  index
}: {
  participant: UserAvatar;
  position: string;
  stackedSize: string;
  index: number;
}) {
  const [imgError, setImgError] = useState(false);
  const bitmojiUrl = participant.bitmoji_url;
  const initials = getInitials(participant.display_name);

  return (
    <div
      className={`absolute ${position} ${stackedSize} rounded-full bg-[#FFFC00] overflow-hidden border border-white dark:border-gray-800 flex items-center justify-center`}
      style={{ zIndex: 3 - index }}
    >
      {bitmojiUrl && !imgError ? (
        <img
          src={bitmojiUrl}
          alt={participant.display_name || ''}
          className="w-full h-full object-cover"
          onError={() => setImgError(true)}
        />
      ) : (
        <span className="font-semibold text-black">{initials}</span>
      )}
    </div>
  );
}

export default function Avatar({
  user,
  name,
  size = 'md',
  className = '',
  isGroupChat = false,
  groupParticipants
}: AvatarProps) {
  const [imageError, setImageError] = useState(false);

  const displayName = user?.display_name || user?.username || name || '';
  const initials = getInitials(displayName);
  const bitmojiUrl = user?.bitmoji_url;

  const bgColor = 'bg-[#FFFC00]';
  const baseClasses = `${sizeClasses[size]} rounded-full flex items-center justify-center font-semibold overflow-hidden ${className}`;

  // Group chat with multiple participant avatars - show stacked
  if (isGroupChat && groupParticipants && groupParticipants.length > 0) {
    const containerSize = sizeClasses[size].split(' ')[0];
    const stackedSize = stackedSizeClasses[size];
    const participantCount = groupParticipants.length;

    const getPositions = (count: number) => {
      if (count === 1) {
        return ['top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2'];
      } else if (count === 2) {
        return [
          'top-0 left-0',
          'bottom-0 right-0',
        ];
      } else {
        return [
          'top-0 left-0',
          'top-0 right-0',
          'bottom-0 left-1/2 -translate-x-1/2',
        ];
      }
    };

    const positions = getPositions(participantCount);

    return (
      <div className={`${containerSize} ${containerSize.replace('w-', 'h-')} relative flex-shrink-0`}>
        {groupParticipants.slice(0, 3).map((participant, index) => (
          <ParticipantAvatar
            key={participant.user_id || `participant-${index}`}
            participant={participant}
            position={positions[index]}
            stackedSize={stackedSize}
            index={index}
          />
        ))}
      </div>
    );
  }

  // If we have a bitmoji URL and no error, show it
  if (bitmojiUrl && !imageError) {
    return (
      <div className={`${baseClasses} ${bgColor}`}>
        <img
          src={bitmojiUrl}
          alt={displayName}
          className="w-full h-full object-cover"
          onError={() => setImageError(true)}
        />
      </div>
    );
  }

  // Default fallback: initials
  return (
    <div className={`${baseClasses} ${bgColor} text-black`}>
      {initials}
    </div>
  );
}
