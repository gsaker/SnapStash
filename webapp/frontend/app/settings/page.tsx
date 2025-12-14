'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '../utils/api';

interface Settings {
  ssh_host: string;
  ssh_port: number;
  ssh_user: string;
  ssh_key_path: string;
  extract_media: boolean;
  ingest_timeout_seconds: number;
  ingest_mode: string;
  ingest_delay_seconds: number;
  dm_exclude_name: string;
  ntfy_enabled: boolean;
  ntfy_server_url: string;
  ntfy_media_topic: string;
  ntfy_text_topic: string;
  ntfy_username: string;
  ntfy_password: string;
  ntfy_auth_token: string;
  ntfy_priority: string;
  ntfy_attach_media: boolean;
  apns_enabled: boolean;
  apns_key_id: string;
  apns_team_id: string;
  apns_bundle_id: string;
  apns_key_filename: string;
  apns_use_sandbox: boolean;
}

export default function SettingsPage() {
  const router = useRouter();
  const [settings, setSettings] = useState<Settings>({
    ssh_host: '',
    ssh_port: 8022,
    ssh_user: 'root',
    ssh_key_path: '',
    extract_media: true,
    ingest_timeout_seconds: 300,
    ingest_mode: 'continuous',
    ingest_delay_seconds: 0,
    dm_exclude_name: '',
    ntfy_enabled: false,
    ntfy_server_url: 'https://ntfy.sh',
    ntfy_media_topic: '',
    ntfy_text_topic: '',
    ntfy_username: '',
    ntfy_password: '',
    ntfy_auth_token: '',
    ntfy_priority: 'default',
    ntfy_attach_media: true,
    apns_enabled: false,
    apns_key_id: '',
    apns_team_id: '',
    apns_bundle_id: 'com.george.SnapStash',
    apns_key_filename: 'AuthKey.p8',
    apns_use_sandbox: true,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [sshKeyInfo, setSshKeyInfo] = useState<any>(null);
  const [uploadingKey, setUploadingKey] = useState(false);
  const [deletingKey, setDeletingKey] = useState(false);
  const [apnsKeyInfo, setApnsKeyInfo] = useState<any>(null);
  const [uploadingApnsKey, setUploadingApnsKey] = useState(false);
  const [deletingApnsKey, setDeletingApnsKey] = useState(false);

  useEffect(() => {
    loadSettings();
    loadSshKeyInfo();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const data = await api.getSettings();
      setSettings(data as Settings);
      setError(null);
    } catch (err) {
      setError('Failed to load settings. Please try again.');
      console.error('Error loading settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      setSuccessMessage(null);

      await api.updateSettings(settings);

      setSuccessMessage('Settings saved successfully! Please restart the Docker containers for all changes to take full effect.');
      setTimeout(() => setSuccessMessage(null), 10000);
    } catch (err) {
      setError('Failed to save settings. Please try again.');
      console.error('Error saving settings:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field: keyof Settings, value: string | number | boolean) => {
    setSettings(prev => ({
      ...prev,
      [field]: value,
    }));
  };

  const loadSshKeyInfo = async () => {
    try {
      const response = await api.getSshKeyInfo() as any;
      setSshKeyInfo(response.data);
    } catch (err) {
      console.error('Error loading SSH key info:', err);
    }
  };

  const handleSshKeyUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setUploadingKey(true);
      setError(null);
      setSuccessMessage(null);

      await api.uploadSshKey(file);

      setSuccessMessage('SSH key uploaded successfully! Please restart Docker containers.');
      await loadSshKeyInfo();
      await loadSettings();

      // Clear the input
      event.target.value = '';

      setTimeout(() => setSuccessMessage(null), 10000);
    } catch (err: any) {
      setError(err.message || 'Failed to upload SSH key. Please try again.');
      console.error('Error uploading SSH key:', err);
    } finally {
      setUploadingKey(false);
    }
  };

  const handleSshKeyDelete = async () => {
    if (!confirm('Are you sure you want to delete the SSH key?')) {
      return;
    }

    try {
      setDeletingKey(true);
      setError(null);
      setSuccessMessage(null);

      await api.deleteSshKey();

      setSuccessMessage('SSH key deleted successfully!');
      await loadSshKeyInfo();
      await loadSettings();

      setTimeout(() => setSuccessMessage(null), 3067);
    } catch (err: any) {
      setError(err.message || 'Failed to delete SSH key. Please try again.');
      console.error('Error deleting SSH key:', err);
    } finally {
      setDeletingKey(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-yellow-500 mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Loading settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => router.push('/')}
            className="flex items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-4"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Back to Chat
          </button>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Settings</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-2">
            Configure your Snapchat data extraction and ingestion settings
          </p>
        </div>

        {/* Messages */}
        {error && (
          <div className="mb-6 bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-800 rounded-lg p-4">
            <div className="flex items-start">
              <svg className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 mr-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <p className="text-red-800 dark:text-red-300">{error}</p>
            </div>
          </div>
        )}

        {successMessage && (
          <div className="mb-6 bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg p-4">
            <div className="flex items-start">
              <svg className="w-5 h-5 text-green-600 dark:text-green-400 mt-0.5 mr-3" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <p className="text-green-800 dark:text-green-300">{successMessage}</p>
            </div>
          </div>
        )}

        {/* Settings Form */}
        <div className="space-y-6">
          {/* Info Banner */}
          <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <div className="flex items-start">
              <svg className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
              </svg>
              <div className="flex-1">
                <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-1">
                  Restart Required
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-400">
                  After saving settings, restart the Docker containers for changes to take full effect:
                </p>
                <code className="block mt-2 bg-blue-100 dark:bg-blue-950 text-blue-900 dark:text-blue-200 px-3 py-2 rounded text-xs font-mono">
                  docker-compose restart
                </code>
              </div>
            </div>
          </div>

          {/* SSH Configuration */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">SSH Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  SSH Host
                </label>
                <input
                  type="text"
                  value={settings.ssh_host}
                  onChange={(e) => handleChange('ssh_host', e.target.value)}
                  placeholder="192.168.8.65"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    SSH Port
                  </label>
                  <input
                    type="number"
                    value={settings.ssh_port}
                    onChange={(e) => handleChange('ssh_port', parseInt(e.target.value))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    SSH User
                  </label>
                  <input
                    type="text"
                    value={settings.ssh_user}
                    onChange={(e) => handleChange('ssh_user', e.target.value)}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  SSH Private Key
                </label>

                {sshKeyInfo?.configured && sshKeyInfo?.exists ? (
                  <div className="bg-green-50 dark:bg-green-900/30 border border-green-200 dark:border-green-800 rounded-lg p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-3">
                        <svg className="w-5 h-5 text-green-600 dark:text-green-400" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                        </svg>
                        <div>
                          <p className="text-sm font-medium text-green-800 dark:text-green-300">
                            {sshKeyInfo.filename}
                          </p>
                          <p className="text-xs text-green-600 dark:text-green-400">
                            Key is configured and ready to use
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={handleSshKeyDelete}
                        disabled={deletingKey}
                        className="px-3 py-1 text-sm bg-red-100 hover:bg-red-200 dark:bg-red-900/30 dark:hover:bg-red-900/50 text-red-700 dark:text-red-400 rounded-md transition-colors disabled:opacity-50"
                      >
                        {deletingKey ? 'Deleting...' : 'Delete'}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <div className="flex items-center justify-center w-full">
                      <label className="flex flex-col items-center justify-center w-full h-32 border-2 border-gray-300 dark:border-gray-600 border-dashed rounded-lg cursor-pointer bg-gray-50 dark:bg-gray-700 hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors">
                        <div className="flex flex-col items-center justify-center pt-5 pb-6">
                          {uploadingKey ? (
                            <>
                              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-yellow-500 mb-2"></div>
                              <p className="text-sm text-gray-500 dark:text-gray-400">Uploading...</p>
                            </>
                          ) : (
                            <>
                              <svg className="w-8 h-8 mb-2 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                              </svg>
                              <p className="mb-2 text-sm text-gray-500 dark:text-gray-400">
                                <span className="font-semibold">Click to upload</span> SSH private key
                              </p>
                              <p className="text-xs text-gray-500 dark:text-gray-400">
                                id_rsa, id_ed25519, or id_ecdsa
                              </p>
                            </>
                          )}
                        </div>
                        <input
                          type="file"
                          className="hidden"
                          onChange={handleSshKeyUpload}
                          disabled={uploadingKey}
                        />
                      </label>
                    </div>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Upload your SSH private key for authentication. The key will be stored securely.
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Ingestion Configuration */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">Ingestion Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.extract_media}
                    onChange={(e) => handleChange('extract_media', e.target.checked)}
                    className="w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    Extract Media Files
                  </span>
                </label>
                <p className="ml-6 text-sm text-gray-500 dark:text-gray-400">
                  Enable extraction of photos and videos from messages
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Ingestion Mode
                </label>
                <select
                  value={settings.ingest_mode}
                  onChange={(e) => handleChange('ingest_mode', e.target.value)}
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                >
                  <option value="continuous">Continuous</option>
                  <option value="interval">Interval</option>
                </select>
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Continuous: Runs immediately after previous completes. Interval: Runs on fixed schedule
                </p>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Timeout (seconds)
                  </label>
                  <input
                    type="number"
                    value={settings.ingest_timeout_seconds}
                    onChange={(e) => handleChange('ingest_timeout_seconds', parseInt(e.target.value))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Delay Between Runs (seconds)
                  </label>
                  <input
                    type="number"
                    value={settings.ingest_delay_seconds}
                    onChange={(e) => handleChange('ingest_delay_seconds', parseInt(e.target.value))}
                    className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                  />
                </div>
              </div>
            </div>
          </div>

          {/* UI Configuration */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">UI Configuration</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  DM Exclude Name
                </label>
                <input
                  type="text"
                  value={settings.dm_exclude_name}
                  onChange={(e) => handleChange('dm_exclude_name', e.target.value)}
                  placeholder="Your Name"
                  className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                />
                <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                  Name to exclude from DM conversation titles (e.g., your own name)
                </p>
              </div>
            </div>
          </div>

          {/* Ntfy Notifications */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">Ntfy Notifications</h2>
            <div className="space-y-4">
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.ntfy_enabled}
                    onChange={(e) => handleChange('ntfy_enabled', e.target.checked)}
                    className="w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    Enable Ntfy Notifications
                  </span>
                </label>
                <p className="ml-6 text-sm text-gray-500 dark:text-gray-400">
                  Receive push notifications for new Snapchat messages via ntfy
                </p>
              </div>

              {settings.ntfy_enabled && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Ntfy Server URL
                    </label>
                    <input
                      type="text"
                      value={settings.ntfy_server_url}
                      onChange={(e) => handleChange('ntfy_server_url', e.target.value)}
                      placeholder="https://ntfy.sh"
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                    />
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      Public ntfy.sh server or your self-hosted instance
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Media Messages Topic
                      </label>
                      <input
                        type="text"
                        value={settings.ntfy_media_topic}
                        onChange={(e) => handleChange('ntfy_media_topic', e.target.value)}
                        placeholder="snapchat-media"
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      />
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Topic for photo/video notifications
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Text Messages Topic
                      </label>
                      <input
                        type="text"
                        value={settings.ntfy_text_topic}
                        onChange={(e) => handleChange('ntfy_text_topic', e.target.value)}
                        placeholder="snapchat-text"
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      />
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Topic for text-only notifications
                      </p>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Authentication (Optional)
                    </label>
                    <div className="space-y-3">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <input
                            type="text"
                            value={settings.ntfy_username}
                            onChange={(e) => handleChange('ntfy_username', e.target.value)}
                            placeholder="Username"
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                          />
                        </div>
                        <div>
                          <input
                            type="password"
                            value={settings.ntfy_password}
                            onChange={(e) => handleChange('ntfy_password', e.target.value)}
                            placeholder="Password"
                            className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                          />
                        </div>
                      </div>
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        Username and password for basic authentication on protected topics
                      </p>
                      <div className="relative">
                        <div className="absolute inset-0 flex items-center">
                          <div className="w-full border-t border-gray-300 dark:border-gray-600"></div>
                        </div>
                        <div className="relative flex justify-center text-xs">
                          <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">OR</span>
                        </div>
                      </div>
                      <input
                        type="password"
                        value={settings.ntfy_auth_token}
                        onChange={(e) => handleChange('ntfy_auth_token', e.target.value)}
                        placeholder="Bearer token (tk_xxxxxxxxxxxxxxxxxxxxxxxx)"
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      />
                      <p className="text-sm text-gray-500 dark:text-gray-400">
                        Use either username/password OR bearer token (not both). Leave empty for public topics.
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Notification Priority
                      </label>
                      <select
                        value={settings.ntfy_priority}
                        onChange={(e) => handleChange('ntfy_priority', e.target.value)}
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      >
                        <option value="min">Min</option>
                        <option value="low">Low</option>
                        <option value="default">Default</option>
                        <option value="high">High</option>
                        <option value="urgent">Urgent</option>
                      </select>
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Notification importance level
                      </p>
                    </div>

                    <div className="flex items-center">
                      <label className="flex items-center">
                        <input
                          type="checkbox"
                          checked={settings.ntfy_attach_media}
                          onChange={(e) => handleChange('ntfy_attach_media', e.target.checked)}
                          className="w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
                        />
                        <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                          Attach Media Files
                        </span>
                      </label>
                    </div>
                  </div>

                  <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <div className="flex items-start">
                      <svg className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      <div className="flex-1">
                        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-1">
                          About Ntfy
                        </h3>
                        <p className="text-sm text-blue-700 dark:text-blue-400">
                          Ntfy is a simple HTTP-based pub-sub notification service. Subscribe to your topics using the ntfy mobile app or web interface to receive push notifications.
                          <a href="https://ntfy.sh" target="_blank" rel="noopener noreferrer" className="underline ml-1">Learn more</a>
                        </p>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* APNs Push Notifications */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-4">iOS Push Notifications (APNs)</h2>
            <div className="space-y-4">
              <div>
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={settings.apns_enabled}
                    onChange={(e) => handleChange('apns_enabled', e.target.checked)}
                    className="w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                    Enable APNs Push Notifications
                  </span>
                </label>
                <p className="ml-6 text-sm text-gray-500 dark:text-gray-400">
                  Send native iOS push notifications for new Snapchat messages
                </p>
              </div>

              {settings.apns_enabled && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Key ID
                      </label>
                      <input
                        type="text"
                        value={settings.apns_key_id}
                        onChange={(e) => handleChange('apns_key_id', e.target.value)}
                        placeholder="ABCD123456"
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      />
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        10-character key identifier from Apple
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Team ID
                      </label>
                      <input
                        type="text"
                        value={settings.apns_team_id}
                        onChange={(e) => handleChange('apns_team_id', e.target.value)}
                        placeholder="XYZ9876543"
                        className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                      />
                      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        10-character team identifier from Apple
                      </p>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Bundle ID
                    </label>
                    <input
                      type="text"
                      value={settings.apns_bundle_id}
                      onChange={(e) => handleChange('apns_bundle_id', e.target.value)}
                      placeholder="com.example.myapp"
                      className="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-yellow-500 focus:border-transparent"
                    />
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                      Your iOS app's bundle identifier
                    </p>
                  </div>

                  <div>
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={settings.apns_use_sandbox}
                        onChange={(e) => handleChange('apns_use_sandbox', e.target.checked)}
                        className="w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
                      />
                      <span className="ml-2 text-sm font-medium text-gray-700 dark:text-gray-300">
                        Use Sandbox Environment
                      </span>
                    </label>
                    <p className="ml-6 text-sm text-gray-500 dark:text-gray-400">
                      Enable for development builds. Disable for production/TestFlight builds.
                    </p>
                  </div>

                  <div className="bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <div className="flex items-start">
                      <svg className="w-5 h-5 text-blue-600 dark:text-blue-400 mt-0.5 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
                      </svg>
                      <div className="flex-1">
                        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-1">
                          Getting APNs Credentials
                        </h3>
                        <p className="text-sm text-blue-700 dark:text-blue-400 mb-2">
                          To get your APNs credentials:
                        </p>
                        <ol className="text-sm text-blue-700 dark:text-blue-400 list-decimal list-inside space-y-1">
                          <li>Go to <a href="https://developer.apple.com/account/resources/authkeys/list" target="_blank" rel="noopener noreferrer" className="underline">Apple Developer Keys</a></li>
                          <li>Create a new key with "Apple Push Notifications service (APNs)" enabled</li>
                          <li>Download the .p8 file and note the Key ID</li>
                          <li>Find your Team ID in your <a href="https://developer.apple.com/account" target="_blank" rel="noopener noreferrer" className="underline">Apple Developer account</a></li>
                          <li>Upload the .p8 key file below</li>
                        </ol>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Save Button */}
          <div className="flex justify-end">
            <button
              onClick={handleSave}
              disabled={saving}
              className="bg-yellow-500 hover:bg-yellow-600 dark:bg-yellow-600 dark:hover:bg-yellow-700 text-white font-medium py-3 px-6 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
