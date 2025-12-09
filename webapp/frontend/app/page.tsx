'use client';

import { useEffect, useState } from 'react';
import ChatInterface from './components/ChatInterface';
import { api } from './utils/api';

export default function Home() {
  const [isHealthy, setIsHealthy] = useState<boolean | null>(null);
  const [currentUserId, setCurrentUserId] = useState<string>();

  useEffect(() => {
    checkBackendHealth();
  }, []);

  const checkBackendHealth = async () => {
    try {
      await api.getHealth();
      setIsHealthy(true);
      
      // Fetch current user after successful health check
      try {
        const currentUser = await api.getCurrentUser() as { id: string; username: string; display_name: string };
        setCurrentUserId(currentUser.id);
        console.log('Current user:', currentUser);
      } catch (userError) {
        console.warn('Could not fetch current user:', userError);
        // Don't fail the entire app if current user is not available
      }
    } catch (error) {
      setIsHealthy(false);
      console.error('Backend health check failed:', error);
    }
  };

  if (isHealthy === null) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-yellow-500 mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Connecting to backend...</p>
        </div>
      </div>
    );
  }

  if (isHealthy === false) {
    return (
      <div className="h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center mx-auto mb-4">
            <div className="w-8 h-8 bg-red-500 dark:bg-red-600 rounded-full"></div>
          </div>
          <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-2">Backend Unavailable</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            The SnapStash backend service is not responding. Please make sure it's running.
          </p>
          <button
            onClick={checkBackendHealth}
            className="bg-yellow-500 hover:bg-yellow-600 dark:bg-yellow-600 dark:hover:bg-yellow-700 text-white font-medium py-2 px-4 rounded-lg transition-colors"
          >
            Retry Connection
          </button>
        </div>
      </div>
    );
  }

  return <ChatInterface currentUserId={currentUserId} />;
}