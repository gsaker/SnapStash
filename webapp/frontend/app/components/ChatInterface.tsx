'use client';

import { useState, useEffect } from 'react';
import { Conversation } from '../types/api';
import ConversationList from './ConversationList';
import ChatView from './ChatView';

interface ChatInterfaceProps {
  currentUserId?: string;
}

export default function ChatInterface({ currentUserId }: ChatInterfaceProps) {
  const [selectedConversation, setSelectedConversation] = useState<Conversation | null>(null);
  const [isMobile, setIsMobile] = useState(false);
  const [showConversationList, setShowConversationList] = useState(true);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const handleConversationSelect = (conversation: Conversation) => {
    setSelectedConversation(conversation);
    if (isMobile) {
      setShowConversationList(false);
    }
  };

  const handleBack = () => {
    if (isMobile) {
      setShowConversationList(true);
      setSelectedConversation(null);
    }
  };

  const handleBackToList = () => {
    setShowConversationList(true);
  };

  return (
    <div className="h-screen bg-gray-100 dark:bg-gray-900 flex">
      {/* Conversation List */}
      <ConversationList
        selectedConversationId={selectedConversation?.id || null}
        onConversationSelect={handleConversationSelect}
        isMobile={isMobile}
        showList={showConversationList}
        onBack={handleBackToList}
      />

      {/* Chat View */}
      {(!isMobile || !showConversationList) && (
        <div className="flex-1 flex flex-col">
          <ChatView
            conversation={selectedConversation}
            onBack={handleBack}
            currentUserId={currentUserId}
            isMobile={isMobile}
          />
        </div>
      )}

      {/* Desktop placeholder when no conversation selected */}
      {!isMobile && !selectedConversation && (
        <div className="flex-1 flex items-center justify-center bg-gray-50 dark:bg-gray-800">
          <div className="text-center">
            <div className="w-24 h-24 bg-yellow-100 dark:bg-yellow-900/30 rounded-full flex items-center justify-center mx-auto mb-6">
              <div className="w-12 h-12 bg-yellow-500 dark:bg-yellow-600 rounded-full"></div>
            </div>
            <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">SnapStash</h2>
            <p className="text-gray-500 dark:text-gray-400 max-w-sm">
              Select a conversation from the sidebar to view your extracted Snapchat messages
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
