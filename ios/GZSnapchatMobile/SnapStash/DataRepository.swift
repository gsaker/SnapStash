//
//  DataRepository.swift
//  SnapStash
//
//  Created by Claude Code
//

import Foundation
import CoreData
import Combine

class DataRepository: ObservableObject {
    static let shared = DataRepository()

    private let coreDataStack = CoreDataStack.shared
    private let apiService = APIService()
    @Published var isOnline: Bool = false  // Default to offline for safety, will check immediately
    @Published var lastSyncDate: Date?

    // Store current user ID persistently
    private let currentUserIdKey = "currentUserId"
    var currentUserId: String? {
        get {
            UserDefaults.standard.string(forKey: currentUserIdKey)
        }
        set {
            UserDefaults.standard.set(newValue, forKey: currentUserIdKey)
        }
    }

    private init() {
        checkConnectivity()
    }

    // MARK: - Connectivity

    func checkConnectivity() {
        Task {
            do {
                _ = try await apiService.checkHealth()
                await MainActor.run {
                    self.isOnline = true
                    print("✅ Connectivity check: ONLINE")
                }
            } catch {
                await MainActor.run {
                    self.isOnline = false
                    print("⚠️ Connectivity check: OFFLINE")
                }
            }
        }
    }

    // MARK: - Conversations

    func fetchConversations(forceRefresh: Bool = false) async throws -> [Conversation] {
        // If forcing refresh, always attempt to check connectivity first
        if forceRefresh && !isOnline {
            print("🔄 Force refresh requested while offline - checking connectivity...")
            checkConnectivity()
            // Give connectivity check a moment to complete
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms
        }

        // Try to fetch from server if online or force refresh
        if isOnline || forceRefresh {
            do {
                let response = try await apiService.getConversations(limit: 100, offset: 0, excludeAds: true)
                // If we were offline but succeeded, we're back online
                if !isOnline {
                    await MainActor.run {
                        self.isOnline = true
                        print("✅ Connectivity restored - back online!")
                    }
                }
                await saveConversations(response.conversations)
                updateSyncMetadata(for: "conversations")
                return response.conversations
            } catch {
                print("DataRepository: Failed to fetch conversations from server: \(error)")
                // Mark as offline if we failed
                await MainActor.run {
                    self.isOnline = false
                }
                // Fall back to local data
            }
        }

        // Return local data
        return await fetchConversationsFromLocal()
    }

    private func fetchConversationsFromLocal() async -> [Conversation] {
        return await coreDataStack.persistentContainer.performBackgroundTask { context in
            let fetchRequest: NSFetchRequest<ConversationEntity> = ConversationEntity.fetchRequest()
            fetchRequest.sortDescriptors = [NSSortDescriptor(key: "lastMessageAt", ascending: false)]

            do {
                let entities = try context.fetch(fetchRequest)
                return entities.compactMap { entity in
                    self.conversationFromEntity(entity)
                }
            } catch {
                print("DataRepository: Failed to fetch conversations from CoreData: \(error)")
                return []
            }
        }
    }

    private func saveConversations(_ conversations: [Conversation]) async {
        await coreDataStack.performBackgroundTask { context in
            for conversation in conversations {
                let fetchRequest: NSFetchRequest<ConversationEntity> = ConversationEntity.fetchRequest()
                fetchRequest.predicate = NSPredicate(format: "id == %@", conversation.id)
                fetchRequest.fetchLimit = 1

                do {
                    let results = try context.fetch(fetchRequest)
                    let entity = results.first ?? ConversationEntity(context: context)

                    entity.id = conversation.id
                    entity.groupName = conversation.groupName
                    entity.isGroupChat = conversation.isGroupChat
                    entity.participantCount = Int32(conversation.participantCount ?? 0)
                    entity.lastMessageAt = conversation.lastMessageAt
                    entity.lastSyncTimestamp = Date()

                    // Encode lastMessagePreview as JSON
                    if let preview = conversation.lastMessagePreview {
                        let encoder = JSONEncoder()
                        if let data = try? encoder.encode(preview) {
                            entity.lastMessagePreview = data
                        }
                    }

                    // Encode avatar as JSON
                    if let avatar = conversation.avatar {
                        let encoder = JSONEncoder()
                        if let data = try? encoder.encode(avatar) {
                            entity.avatar = data
                        }
                    }
                } catch {
                    print("DataRepository: Failed to save conversation \(conversation.id): \(error)")
                }
            }

            self.coreDataStack.saveContext(context)
        }
    }

    private func conversationFromEntity(_ entity: ConversationEntity) -> Conversation? {
        var lastMessagePreview: LastMessagePreview?
        if let data = entity.lastMessagePreview {
            let decoder = JSONDecoder()
            lastMessagePreview = try? decoder.decode(LastMessagePreview.self, from: data)
        }

        var avatar: ConversationAvatar?
        if let data = entity.avatar {
            let decoder = JSONDecoder()
            avatar = try? decoder.decode(ConversationAvatar.self, from: data)
        }

        return Conversation(
            id: entity.id ?? "",
            groupName: entity.groupName,
            isGroupChat: entity.isGroupChat,
            participantCount: Int(entity.participantCount),
            lastMessageAt: entity.lastMessageAt,
            createdAt: "", // Not stored in entity, use empty string
            updatedAt: "", // Not stored in entity, use empty string
            lastMessagePreview: lastMessagePreview,
            avatar: avatar
        )
    }

    // MARK: - Messages

    func fetchMessages(for conversationId: String, limit: Int = 100, offset: Int = 0, forceRefresh: Bool = false) async throws -> [Message] {
        // If forcing refresh, always attempt to check connectivity first
        if forceRefresh && !isOnline {
            print("🔄 Force refresh requested while offline - checking connectivity...")
            checkConnectivity()
            // Give connectivity check a moment to complete
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms
        }

        // Try to fetch from server if online or force refresh
        if isOnline || forceRefresh {
            do {
                let response = try await apiService.getMessages(conversationId: conversationId, limit: limit, offset: offset)
                // If we were offline but succeeded, we're back online
                if !isOnline {
                    await MainActor.run {
                        self.isOnline = true
                        print("✅ Connectivity restored - back online!")
                    }
                }
                await saveMessages(response.messages, for: conversationId)
                updateSyncMetadata(for: "messages_\(conversationId)")
                return response.messages
            } catch {
                print("DataRepository: Failed to fetch messages from server: \(error)")
                // Mark as offline if we failed
                await MainActor.run {
                    self.isOnline = false
                }
                // Fall back to local data
            }
        }

        // Return local data
        return await fetchMessagesFromLocal(conversationId: conversationId, limit: limit, offset: offset)
    }

    // Public method to fetch only from local storage without any network calls
    func fetchMessagesFromLocalOnly(conversationId: String, limit: Int = 100, offset: Int = 0) async -> [Message] {
        return await fetchMessagesFromLocal(conversationId: conversationId, limit: limit, offset: offset)
    }

    private func fetchMessagesFromLocal(conversationId: String, limit: Int, offset: Int) async -> [Message] {
        return await coreDataStack.persistentContainer.performBackgroundTask { context in
            let fetchRequest: NSFetchRequest<MessageEntity> = MessageEntity.fetchRequest()
            fetchRequest.predicate = NSPredicate(format: "conversationId == %@", conversationId)
            fetchRequest.sortDescriptors = [NSSortDescriptor(key: "creationTimestamp", ascending: false)]
            fetchRequest.fetchLimit = limit
            fetchRequest.fetchOffset = offset

            do {
                let entities = try context.fetch(fetchRequest)
                return entities.compactMap { entity in
                    self.messageFromEntity(entity, context: context)
                }
            } catch {
                print("DataRepository: Failed to fetch messages from CoreData: \(error)")
                return []
            }
        }
    }

    private func saveMessages(_ messages: [Message], for conversationId: String) async {
        await coreDataStack.performBackgroundTask { context in
            for message in messages {
                let fetchRequest: NSFetchRequest<MessageEntity> = MessageEntity.fetchRequest()
                fetchRequest.predicate = NSPredicate(format: "id == %lld", message.id)
                fetchRequest.fetchLimit = 1

                do {
                    let results = try context.fetch(fetchRequest)
                    let entity = results.first ?? MessageEntity(context: context)

                    entity.id = Int64(message.id)
                    entity.conversationId = message.conversationId
                    entity.text = message.text
                    entity.contentType = Int32(message.contentType)
                    entity.creationTimestamp = message.creationTimestamp
                    entity.readTimestamp = message.readTimestamp ?? 0
                    entity.senderId = message.senderId
                    entity.mediaAssetId = message.mediaAssetId.map { Int64($0) } ?? 0

                    // Save sender user and establish relationship
                    if let sender = message.sender {
                        let userEntity = self.saveUser(sender, in: context)
                        entity.sender = userEntity
                    }

                    // Save media asset and establish relationship
                    if let mediaAsset = message.mediaAsset {
                        let mediaEntity = self.saveMedia(mediaAsset, in: context)
                        entity.mediaAsset = mediaEntity
                        print("✅ Linked message \(message.id) to media \(mediaAsset.id)")
                    }
                } catch {
                    print("DataRepository: Failed to save message \(message.id): \(error)")
                }
            }

            self.coreDataStack.saveContext(context)
        }
    }

    private func messageFromEntity(_ entity: MessageEntity, context: NSManagedObjectContext) -> Message? {
        var sender: User?
        if let userEntity = entity.sender {
            sender = userFromEntity(userEntity)
        }

        var mediaAsset: MediaAsset?
        if let mediaEntity = entity.mediaAsset {
            mediaAsset = mediaAssetFromEntity(mediaEntity)
            print("📦 Message \(entity.id) has mediaAsset: \(mediaAsset?.id ?? -1)")
        } else if entity.mediaAssetId != 0 {
            print("⚠️ Message \(entity.id) has mediaAssetId \(entity.mediaAssetId) but no relationship!")
        }

        return Message(
            id: Int(entity.id),
            text: entity.text,
            contentType: Int(entity.contentType),
            cacheId: nil, // Not stored in entity
            creationTimestamp: entity.creationTimestamp,
            readTimestamp: entity.readTimestamp == 0 ? nil : entity.readTimestamp,
            parsingSuccessful: true, // Default to true
            senderId: entity.senderId ?? "",
            conversationId: entity.conversationId ?? "",
            serverMessageId: nil, // Not stored in entity
            clientMessageId: nil, // Not stored in entity
            mediaAssetId: entity.mediaAssetId == 0 ? nil : Int(entity.mediaAssetId),
            createdAt: "", // Not stored in entity
            updatedAt: "", // Not stored in entity
            sender: sender,
            mediaAsset: mediaAsset
        )
    }

    // MARK: - Users

    @discardableResult
    private func saveUser(_ user: User, in context: NSManagedObjectContext) -> UserEntity? {
        let fetchRequest: NSFetchRequest<UserEntity> = UserEntity.fetchRequest()
        fetchRequest.predicate = NSPredicate(format: "id == %@", user.id)
        fetchRequest.fetchLimit = 1

        do {
            let results = try context.fetch(fetchRequest)
            let entity = results.first ?? UserEntity(context: context)

            entity.id = user.id
            entity.username = user.username
            entity.displayName = user.displayName
            entity.bitmojiAvatarId = user.bitmojiAvatarId
            entity.bitmojiSelfieId = user.bitmojiSelfieId
            entity.bitmojiUrl = user.bitmojiUrl

            return entity
        } catch {
            print("DataRepository: Failed to save user \(user.id): \(error)")
            return nil
        }
    }

    private func userFromEntity(_ entity: UserEntity) -> User {
        return User(
            id: entity.id ?? "",
            username: entity.username ?? "",
            displayName: entity.displayName ?? "",
            bitmojiAvatarId: entity.bitmojiAvatarId,
            bitmojiSelfieId: entity.bitmojiSelfieId,
            bitmojiUrl: entity.bitmojiUrl,
            createdAt: nil, // Not stored in entity
            updatedAt: nil  // Not stored in entity
        )
    }

    // MARK: - Media

    @discardableResult
    private func saveMedia(_ mediaAsset: MediaAsset, in context: NSManagedObjectContext) -> MediaEntity? {
        let fetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()
        fetchRequest.predicate = NSPredicate(format: "id == %lld", mediaAsset.id)
        fetchRequest.fetchLimit = 1

        do {
            let results = try context.fetch(fetchRequest)
            let entity = results.first ?? MediaEntity(context: context)

            entity.id = Int64(mediaAsset.id)
            entity.fileType = mediaAsset.fileType
            entity.mimeType = mediaAsset.mimeType
            entity.fileSize = Int64(mediaAsset.fileSize ?? 0)
            entity.serverFilePath = mediaAsset.filePath
            entity.fileCoreDataHash = mediaAsset.fileHash
            entity.cacheKey = mediaAsset.cacheKey
            entity.senderId = mediaAsset.senderId
            entity.originalFilename = mediaAsset.originalFilename
            entity.category = mediaAsset.category

            if let sender = mediaAsset.sender {
                let senderEntity = self.saveUser(sender, in: context)
                entity.sender = senderEntity
            }

            return entity
        } catch {
            print("DataRepository: Failed to save media \(mediaAsset.id): \(error)")
            return nil
        }
    }

    private func mediaAssetFromEntity(_ entity: MediaEntity) -> MediaAsset? {
        var sender: User?
        if let userEntity = entity.sender {
            sender = userFromEntity(userEntity)
        }

        return MediaAsset(
            id: Int(entity.id),
            originalFilename: entity.originalFilename,
            filePath: entity.serverFilePath ?? "",
            fileHash: entity.fileCoreDataHash ?? "",
            fileSize: Int(entity.fileSize),
            fileType: entity.fileType ?? "image",
            mimeType: entity.mimeType ?? "image/jpeg",
            cacheKey: entity.cacheKey ?? "",
            cacheId: entity.cacheKey ?? "", // Use cacheKey as cacheId
            category: entity.category ?? "",
            timestampSource: nil, // Not stored in entity
            mappingMethod: nil, // Not stored in entity
            fileTimestamp: nil, // Not stored in entity
            senderId: entity.senderId,
            createdAt: "", // Not stored in entity
            updatedAt: nil, // Not stored in entity
            sender: sender
        )
    }

    // MARK: - Sync Metadata

    private func updateSyncMetadata(for entityType: String) {
        let context = coreDataStack.newBackgroundContext()
        context.perform {
            let fetchRequest: NSFetchRequest<SyncMetadataEntity> = SyncMetadataEntity.fetchRequest()
            fetchRequest.predicate = NSPredicate(format: "entityType == %@", entityType)
            fetchRequest.fetchLimit = 1

            do {
                let results = try context.fetch(fetchRequest)
                let entity = results.first ?? SyncMetadataEntity(context: context)

                entity.entityType = entityType
                entity.lastSuccessfulSync = Date()
                entity.lastSyncAttempt = Date()
                entity.syncError = nil

                self.coreDataStack.saveContext(context)

                DispatchQueue.main.async {
                    self.lastSyncDate = Date()
                }
            } catch {
                print("DataRepository: Failed to update sync metadata: \(error)")
            }
        }
    }

    func getLastSyncDate(for entityType: String) async -> Date? {
        return await coreDataStack.persistentContainer.performBackgroundTask { context in
            let fetchRequest: NSFetchRequest<SyncMetadataEntity> = SyncMetadataEntity.fetchRequest()
            fetchRequest.predicate = NSPredicate(format: "entityType == %@", entityType)
            fetchRequest.fetchLimit = 1

            do {
                let results = try context.fetch(fetchRequest)
                return results.first?.lastSuccessfulSync
            } catch {
                return nil
            }
        }
    }

    // MARK: - Current User

    func fetchCurrentUser(forceRefresh: Bool = false) async throws -> User {
        // If forcing refresh, always attempt to check connectivity first
        if forceRefresh && !isOnline {
            print("🔄 Force refresh requested while offline - checking connectivity...")
            checkConnectivity()
            // Give connectivity check a moment to complete
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms
        }

        if isOnline || forceRefresh {
            do {
                let user = try await apiService.getCurrentUser()
                // If we were offline but succeeded, we're back online
                if !isOnline {
                    await MainActor.run {
                        self.isOnline = true
                        print("✅ Connectivity restored - back online!")
                    }
                }
                await saveCurrentUser(user)
                // Save current user ID for offline use
                currentUserId = user.id
                return user
            } catch {
                print("DataRepository: Failed to fetch current user from server: \(error)")
                // Mark as offline if we failed
                await MainActor.run {
                    self.isOnline = false
                }
            }
        }

        // Return from local storage or throw
        guard let user = await fetchCurrentUserFromLocal() else {
            throw NSError(domain: "DataRepository", code: -1, userInfo: [NSLocalizedDescriptionKey: "No current user found in local storage"])
        }

        return user
    }

    private func fetchCurrentUserFromLocal() async -> User? {
        return await coreDataStack.persistentContainer.performBackgroundTask { context in
            // Fetch from UserDefaults or a dedicated entity
            // For now, we'll use the first user in the database as a fallback
            let fetchRequest: NSFetchRequest<UserEntity> = UserEntity.fetchRequest()
            fetchRequest.fetchLimit = 1

            do {
                let results = try context.fetch(fetchRequest)
                if let entity = results.first {
                    return self.userFromEntity(entity)
                }
            } catch {
                print("DataRepository: Failed to fetch current user from CoreData: \(error)")
            }

            return nil
        }
    }

    private func saveCurrentUser(_ user: User) async {
        await coreDataStack.performBackgroundTask { context in
            self.saveUser(user, in: context)
            self.coreDataStack.saveContext(context)
        }
    }
}
