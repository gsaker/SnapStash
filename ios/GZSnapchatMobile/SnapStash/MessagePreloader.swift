//
//  MessagePreloader.swift
//  SnapStashMobile
//
//  Created by George on 08/12/2025.
//

import Foundation
import Combine

/// Manages preloading and caching of messages for top conversations to improve perceived performance.
/// Messages are preloaded based on the most recent received message timestamp.
class MessagePreloader: ObservableObject {
    static let shared = MessagePreloader()
    
    /// Number of top conversations to preload
    private let preloadCount = 10
    
    /// Number of messages to preload per conversation
    private let messagesPerConversation = 100
    
    /// Maximum number of media items to preload per conversation
    private let maxMediaPerConversation = 20
    
    /// Maximum concurrent media downloads
    private let maxConcurrentMediaDownloads = 3
    
    /// Cache of preloaded messages keyed by conversation ID
    @Published private(set) var cachedMessages: [String: [Message]] = [:]
    
    /// Cache of preloaded media data keyed by media ID
    @Published private(set) var cachedMedia: [Int: Data] = [:]
    
    /// Cache of pagination info keyed by conversation ID
    private var paginationInfo: [String: PaginationMeta] = [:]
    
    /// Timestamp of when each conversation's messages were cached
    private var cacheTimestamps: [String: Date] = [:]
    
    /// Timestamp of when each media item was cached
    private var mediaCacheTimestamps: [Int: Date] = [:]
    
    /// Cache validity duration (5 minutes)
    private let cacheValidityDuration: TimeInterval = 300
    
    /// Media cache validity duration (10 minutes - longer since media doesn't change)
    private let mediaCacheValidityDuration: TimeInterval = 600
    
    /// Currently preloading conversation IDs
    private var preloadingConversations: Set<String> = []
    
    /// Currently preloading media IDs
    private var preloadingMedia: Set<Int> = []
    
    /// Lock for thread-safe access
    private let lock = NSLock()
    
    private init() {}
    
    // MARK: - Public Methods
    
    /// Preload messages for top conversations based on last message timestamp.
    /// This should be called after the conversation list is loaded.
    /// - Parameters:
    ///   - conversations: All conversations to consider
    ///   - apiService: The API service to fetch messages
    func preloadTopConversations(_ conversations: [Conversation], using apiService: APIService) async {
        // Sort by last message timestamp (most recent first)
        let sortedConversations = conversations
            .sorted { conv1, conv2 in
                let date1 = conv1.lastMessageAt ?? ""
                let date2 = conv2.lastMessageAt ?? ""
                return date1 > date2
            }
            .prefix(preloadCount)
        
        print("📥 Starting preload for top \(sortedConversations.count) conversations")
        
        // Preload messages in parallel (but limit concurrent tasks)
        await withTaskGroup(of: Void.self) { group in
            for conversation in sortedConversations {
                group.addTask {
                    await self.preloadMessages(for: conversation.id, using: apiService)
                }
            }
        }
        
        print("✅ Message preload complete for \(sortedConversations.count) conversations")
        
        // Now preload media for all preloaded conversations
        await preloadMediaForCachedConversations(using: apiService)
    }
    
    /// Preload messages for a single conversation.
    /// - Parameters:
    ///   - conversationId: The conversation ID to preload
    ///   - apiService: The API service to fetch messages
    ///   - force: If true, reload even if cache is valid
    func preloadMessages(for conversationId: String, using apiService: APIService, force: Bool = false) async {
        // Check if already preloading
        lock.lock()
        if preloadingConversations.contains(conversationId) {
            lock.unlock()
            return
        }
        
        // Check if cache is still valid
        if !force, let cacheTime = cacheTimestamps[conversationId] {
            if Date().timeIntervalSince(cacheTime) < cacheValidityDuration {
                lock.unlock()
                print("📦 Cache still valid for conversation \(conversationId)")
                return
            }
        }
        
        preloadingConversations.insert(conversationId)
        lock.unlock()
        
        defer {
            lock.lock()
            preloadingConversations.remove(conversationId)
            lock.unlock()
        }
        
        do {
            print("📥 Preloading messages for conversation: \(conversationId)")
            let response = try await apiService.getMessages(
                conversationId: conversationId,
                limit: messagesPerConversation,
                offset: 0
            )
            
            // Sort messages by timestamp (oldest first for display)
            let sortedMessages = response.messages.sorted { $0.creationTimestamp < $1.creationTimestamp }
            
            // Update cache on main actor
            await MainActor.run {
                self.cachedMessages[conversationId] = sortedMessages
                self.paginationInfo[conversationId] = response.pagination
                self.cacheTimestamps[conversationId] = Date()
            }
            
            print("✅ Preloaded \(sortedMessages.count) messages for conversation \(conversationId)")
        } catch {
            print("❌ Failed to preload messages for \(conversationId): \(error)")
        }
    }
    
    // MARK: - Media Preloading
    
    /// Preload media for all cached conversations
    private func preloadMediaForCachedConversations(using apiService: APIService) async {
        lock.lock()
        let allCachedMessages = cachedMessages
        lock.unlock()
        
        var allMediaToPreload: [(mediaId: Int, conversationId: String)] = []
        
        // Collect media assets from cached messages (most recent messages first)
        for (conversationId, messages) in allCachedMessages {
            let messagesWithMedia = messages
                .reversed() // Most recent first
                .compactMap { message -> (mediaId: Int, conversationId: String)? in
                    guard let mediaAsset = message.mediaAsset else { return nil }
                    // Only preload images and small videos
                    if mediaAsset.isImage || (mediaAsset.isVideo && mediaAsset.fileSize < 10_000_000) {
                        return (mediaAsset.id, conversationId)
                    }
                    return nil
                }
                .prefix(maxMediaPerConversation)
            
            allMediaToPreload.append(contentsOf: messagesWithMedia)
        }
        
        guard !allMediaToPreload.isEmpty else {
            print("📷 No media to preload")
            return
        }
        
        print("📷 Starting media preload for \(allMediaToPreload.count) items")
        
        // Preload media with limited concurrency
        await withTaskGroup(of: Void.self) { group in
            var activeCount = 0
            
            for (mediaId, _) in allMediaToPreload {
                // Limit concurrent downloads
                if activeCount >= maxConcurrentMediaDownloads {
                    await group.next()
                    activeCount -= 1
                }
                
                group.addTask {
                    await self.preloadMedia(mediaId: mediaId, using: apiService)
                }
                activeCount += 1
            }
        }
        
        print("✅ Media preload complete")
    }
    
    /// Preload a single media item
    /// - Parameters:
    ///   - mediaId: The media ID to preload
    ///   - apiService: The API service to download media
    func preloadMedia(mediaId: Int, using apiService: APIService) async {
        // Check if already preloading or cached
        lock.lock()
        if preloadingMedia.contains(mediaId) {
            lock.unlock()
            return
        }
        
        if let cacheTime = mediaCacheTimestamps[mediaId],
           Date().timeIntervalSince(cacheTime) < mediaCacheValidityDuration {
            lock.unlock()
            return
        }
        
        preloadingMedia.insert(mediaId)
        lock.unlock()
        
        defer {
            lock.lock()
            preloadingMedia.remove(mediaId)
            lock.unlock()
        }
        
        do {
            let data = try await apiService.downloadMedia(mediaId: mediaId)
            
            await MainActor.run {
                self.cachedMedia[mediaId] = data
                self.mediaCacheTimestamps[mediaId] = Date()
            }
            
            print("📷 Preloaded media \(mediaId) (\(data.count) bytes)")
        } catch {
            print("❌ Failed to preload media \(mediaId): \(error)")
        }
    }
    
    /// Get cached media data if available and valid
    /// - Parameter mediaId: The media ID
    /// - Returns: Cached data or nil
    func getCachedMedia(for mediaId: Int) -> Data? {
        lock.lock()
        defer { lock.unlock() }
        
        guard let data = cachedMedia[mediaId],
              let cacheTime = mediaCacheTimestamps[mediaId],
              Date().timeIntervalSince(cacheTime) < mediaCacheValidityDuration else {
            return nil
        }
        
        return data
    }
    
    /// Check if media is cached and valid
    /// - Parameter mediaId: The media ID
    /// - Returns: True if valid cached media exists
    func hasCachedMedia(for mediaId: Int) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        
        guard cachedMedia[mediaId] != nil,
              let cacheTime = mediaCacheTimestamps[mediaId] else {
            return false
        }
        
        return Date().timeIntervalSince(cacheTime) < mediaCacheValidityDuration
    }
    
    // MARK: - Message Cache Methods
    
    /// Get cached messages for a conversation if available and valid.
    /// - Parameter conversationId: The conversation ID
    /// - Returns: Tuple of messages and pagination info, or nil if not cached/invalid
    func getCachedMessages(for conversationId: String) -> (messages: [Message], pagination: PaginationMeta)? {
        lock.lock()
        defer { lock.unlock() }
        
        guard let messages = cachedMessages[conversationId],
              let pagination = paginationInfo[conversationId],
              let cacheTime = cacheTimestamps[conversationId],
              Date().timeIntervalSince(cacheTime) < cacheValidityDuration else {
            return nil
        }
        
        return (messages, pagination)
    }
    
    /// Check if messages for a conversation are cached and valid.
    /// - Parameter conversationId: The conversation ID
    /// - Returns: True if valid cached messages exist
    func hasCachedMessages(for conversationId: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        
        guard cachedMessages[conversationId] != nil,
              let cacheTime = cacheTimestamps[conversationId] else {
            return false
        }
        
        return Date().timeIntervalSince(cacheTime) < cacheValidityDuration
    }
    
    /// Invalidate cache for a specific conversation.
    /// - Parameter conversationId: The conversation ID to invalidate
    func invalidateCache(for conversationId: String) {
        lock.lock()
        defer { lock.unlock() }
        
        // Get media IDs from this conversation's messages before removing
        if let messages = cachedMessages[conversationId] {
            for message in messages {
                if let mediaId = message.mediaAsset?.id {
                    cachedMedia.removeValue(forKey: mediaId)
                    mediaCacheTimestamps.removeValue(forKey: mediaId)
                }
            }
        }
        
        cachedMessages.removeValue(forKey: conversationId)
        paginationInfo.removeValue(forKey: conversationId)
        cacheTimestamps.removeValue(forKey: conversationId)
    }
    
    /// Clear all cached messages and media.
    func clearAllCache() {
        lock.lock()
        defer { lock.unlock() }
        
        cachedMessages.removeAll()
        paginationInfo.removeAll()
        cacheTimestamps.removeAll()
        cachedMedia.removeAll()
        mediaCacheTimestamps.removeAll()
        
        print("🗑️ All message and media cache cleared")
    }
    
    /// Clear only media cache (useful if running low on memory)
    func clearMediaCache() {
        lock.lock()
        defer { lock.unlock() }
        
        cachedMedia.removeAll()
        mediaCacheTimestamps.removeAll()
        
        print("🗑️ Media cache cleared")
    }
    
    /// Update cache with newly loaded messages (e.g., after loading older messages).
    /// This merges new messages with existing cache.
    /// - Parameters:
    ///   - conversationId: The conversation ID
    ///   - messages: All current messages (sorted oldest first)
    ///   - pagination: Current pagination info
    func updateCache(for conversationId: String, messages: [Message], pagination: PaginationMeta) {
        lock.lock()
        defer { lock.unlock() }
        
        cachedMessages[conversationId] = messages
        paginationInfo[conversationId] = pagination
        cacheTimestamps[conversationId] = Date()
    }
    
    /// Update media cache with downloaded data
    /// - Parameters:
    ///   - mediaId: The media ID
    ///   - data: The media data
    func updateMediaCache(mediaId: Int, data: Data) {
        lock.lock()
        defer { lock.unlock() }
        
        cachedMedia[mediaId] = data
        mediaCacheTimestamps[mediaId] = Date()
    }
}
