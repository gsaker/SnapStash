//
//  MediaStorageManager.swift
//  SnapStash
//
//  Created by Claude Code
//

import Foundation
import CoreData
import UIKit

// Notification for when media is downloaded
extension Notification.Name {
    static let mediaDidDownload = Notification.Name("mediaDidDownload")
}

class MediaStorageManager {
    static let shared = MediaStorageManager()

    private let fileManager = FileManager.default
    private let apiService = APIService()
    private let coreDataStack = CoreDataStack.shared
    private let dataRepository = DataRepository.shared

    // Media storage directory in App Group container (shared with notification extension)
    private var mediaDirectory: URL {
        // Use App Group container for shared access between app and extension
        if let containerURL = fileManager.containerURL(forSecurityApplicationGroupIdentifier: "group.com.georgesaker147.snapstash") {
            let mediaPath = containerURL.appendingPathComponent("Media", isDirectory: true)

            if !fileManager.fileExists(atPath: mediaPath.path) {
                try? fileManager.createDirectory(at: mediaPath, withIntermediateDirectories: true)
            }

            return mediaPath
        } else {
            // Fallback to Documents directory if App Group is not available
            let documentsPath = fileManager.urls(for: .documentDirectory, in: .userDomainMask)[0]
            let mediaPath = documentsPath.appendingPathComponent("Media", isDirectory: true)

            if !fileManager.fileExists(atPath: mediaPath.path) {
                try? fileManager.createDirectory(at: mediaPath, withIntermediateDirectories: true)
            }

            return mediaPath
        }
    }

    // Maximum storage size: 500 MB
    private let maxStorageSize: Int64 = 500 * 1024 * 1024

    private init() {}

    // MARK: - Download and Store Media

    func downloadAndStoreMedia(mediaId: Int) async throws -> URL {
        // Check if already downloaded
        if let localPath = await getLocalMediaPath(for: mediaId) {
            if fileManager.fileExists(atPath: localPath.path) {
                print("📁 Media \(mediaId) found in cache: \(localPath.path)")
                return localPath
            }
        }

        // Check if offline before attempting download
        guard dataRepository.isOnline else {
            print("⚠️ Cannot download media \(mediaId) - offline mode")
            throw NSError(domain: "MediaStorageManager", code: -1, userInfo: [NSLocalizedDescriptionKey: "Device is offline"])
        }

        // Download from server
        let data = try await apiService.downloadMedia(mediaId: mediaId)

        // Generate local file path
        let localPath = mediaDirectory.appendingPathComponent("\(mediaId)")

        // Write to disk
        try data.write(to: localPath)

        // Update CoreData with local path
        await updateMediaEntity(mediaId: mediaId, localPath: localPath.path)

        // Post notification that media was downloaded
        NotificationCenter.default.post(name: .mediaDidDownload, object: nil, userInfo: ["mediaId": mediaId])

        // Cleanup if storage exceeds limit
        await cleanupOldMediaIfNeeded()

        return localPath
    }

    func getLocalMediaPath(for mediaId: Int) async -> URL? {
        return await coreDataStack.persistentContainer.performBackgroundTask { context in
            let fetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()
            fetchRequest.predicate = NSPredicate(format: "id == %lld", mediaId)
            fetchRequest.fetchLimit = 1

            do {
                let results = try context.fetch(fetchRequest)
                if let entity = results.first, let localPath = entity.localFilePath {
                    return URL(fileURLWithPath: localPath)
                }
            } catch {
                print("MediaStorageManager: Failed to fetch media entity: \(error)")
            }

            return nil
        }
    }

    private func updateMediaEntity(mediaId: Int, localPath: String) async {
        await coreDataStack.performBackgroundTask { context in
            // Set merge policy to prefer newer data
            context.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy

            let fetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()
            fetchRequest.predicate = NSPredicate(format: "id == %lld", mediaId)
            fetchRequest.fetchLimit = 1

            do {
                let results = try context.fetch(fetchRequest)
                if let entity = results.first {
                    entity.localFilePath = localPath
                    entity.downloadedAt = Date()
                    self.coreDataStack.saveContext(context)
                }
            } catch {
                print("MediaStorageManager: Failed to update media entity: \(error)")
            }
        }
    }

    // MARK: - Batch Download

    func downloadMediaForConversation(_ conversationId: String, limit: Int = 20) async {
        // Skip if offline
        guard dataRepository.isOnline else {
            print("MediaStorageManager: Skipping download (offline mode)")
            return
        }

        // Fetch media IDs from CoreData that are NOT already downloaded
        let mediaIdsToDownload = await coreDataStack.persistentContainer.performBackgroundTask { context in
            let fetchRequest: NSFetchRequest<MessageEntity> = MessageEntity.fetchRequest()
            fetchRequest.predicate = NSPredicate(format: "conversationId == %@ AND mediaAssetId != 0", conversationId)
            fetchRequest.sortDescriptors = [NSSortDescriptor(key: "creationTimestamp", ascending: false)]
            fetchRequest.fetchLimit = limit

            do {
                let messages = try context.fetch(fetchRequest)
                let mediaIds = messages.compactMap { Int($0.mediaAssetId) }

                // Filter out media that's already downloaded
                var notDownloaded: [Int] = []
                for mediaId in mediaIds {
                    let mediaFetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()
                    mediaFetchRequest.predicate = NSPredicate(format: "id == %lld", mediaId)
                    mediaFetchRequest.fetchLimit = 1

                    if let mediaEntity = try? context.fetch(mediaFetchRequest).first {
                        // Check if file exists locally (access within context)
                        if let localPath = mediaEntity.value(forKey: "localFilePath") as? String {
                            print("📁 Media \(mediaId) has localPath: \(localPath), exists: \(FileManager.default.fileExists(atPath: localPath))")
                            if FileManager.default.fileExists(atPath: localPath) {
                                // Already downloaded, skip
                                continue
                            }
                        } else {
                            print("⚠️ Media \(mediaId) has NO localFilePath in CoreData")
                        }
                    } else {
                        print("❌ Media \(mediaId) entity not found in CoreData")
                    }
                    notDownloaded.append(mediaId)
                }

                print("MediaStorageManager: \(notDownloaded.count) media items need downloading out of \(mediaIds.count)")
                return notDownloaded
            } catch {
                print("MediaStorageManager: Failed to fetch messages for media download: \(error)")
                return []
            }
        }

        guard !mediaIdsToDownload.isEmpty else {
            print("MediaStorageManager: All media already cached for conversation \(conversationId)")
            return
        }

        // Download media in parallel (max 5 concurrent for faster loading)
        await withTaskGroup(of: Void.self) { group in
            var activeDownloads = 0
            let maxConcurrent = 5

            for mediaId in mediaIdsToDownload {
                if activeDownloads >= maxConcurrent {
                    await group.next()
                    activeDownloads -= 1
                }

                group.addTask {
                    do {
                        _ = try await self.downloadAndStoreMedia(mediaId: mediaId)
                        print("MediaStorageManager: Downloaded media \(mediaId)")
                    } catch {
                        print("MediaStorageManager: Failed to download media \(mediaId): \(error)")
                    }
                }

                activeDownloads += 1
            }
        }
    }

    // MARK: - Storage Management

    func getCurrentStorageSize() async -> Int64 {
        return await Task.detached {
            var totalSize: Int64 = 0

            guard let files = try? self.fileManager.contentsOfDirectory(at: self.mediaDirectory, includingPropertiesForKeys: [.fileSizeKey]) else {
                return 0
            }

            for file in files {
                if let attributes = try? self.fileManager.attributesOfItem(atPath: file.path),
                   let fileSize = attributes[.size] as? Int64 {
                    totalSize += fileSize
                }
            }

            return totalSize
        }.value
    }

    private func cleanupOldMediaIfNeeded() async {
        let currentSize = await getCurrentStorageSize()

        if currentSize > maxStorageSize {
            await cleanupOldMedia()
        }
    }

    func cleanupOldMedia() async {
        let currentSizeValue = await getCurrentStorageSize()
        let targetSize = maxStorageSize * 3 / 4 // Clean up to 75% capacity

        await Task.detached {
            let context = self.coreDataStack.newBackgroundContext()

            context.performAndWait {
                // Fetch media sorted by download date (oldest first)
                let fetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()
                fetchRequest.predicate = NSPredicate(format: "localFilePath != nil")
                fetchRequest.sortDescriptors = [NSSortDescriptor(key: "downloadedAt", ascending: true)]

                do {
                    let mediaEntities = try context.fetch(fetchRequest)
                    var currentSize = currentSizeValue

                    for entity in mediaEntities {
                        if currentSize <= targetSize {
                            break
                        }

                        if let localPath = entity.localFilePath {
                            let fileURL = URL(fileURLWithPath: localPath)
                            let entityId = entity.id

                            // Get file size before deletion
                            if let attributes = try? self.fileManager.attributesOfItem(atPath: localPath),
                               let fileSize = attributes[.size] as? Int64 {

                                // Delete file
                                try? self.fileManager.removeItem(at: fileURL)

                                // Clear local path in entity
                                entity.localFilePath = nil
                                entity.downloadedAt = nil

                                currentSize -= fileSize
                                print("MediaStorageManager: Deleted media file \(entityId) to free space")
                            }
                        }
                    }

                    self.coreDataStack.saveContext(context)
                } catch {
                    print("MediaStorageManager: Failed to cleanup old media: \(error)")
                }
            }
        }.value
    }

    func deleteMediaFile(for mediaId: Int) async {
        if let localPath = await getLocalMediaPath(for: mediaId) {
            try? fileManager.removeItem(at: localPath)

            await coreDataStack.performBackgroundTask { context in
                let fetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()
                fetchRequest.predicate = NSPredicate(format: "id == %lld", mediaId)
                fetchRequest.fetchLimit = 1

                do {
                    let results = try context.fetch(fetchRequest)
                    if let entity = results.first {
                        entity.localFilePath = nil
                        entity.downloadedAt = nil
                        self.coreDataStack.saveContext(context)
                    }
                } catch {
                    print("MediaStorageManager: Failed to clear media entity path: \(error)")
                }
            }
        }
    }

    func clearAllMedia() async {
        try? fileManager.removeItem(at: mediaDirectory)

        await coreDataStack.performBackgroundTask { context in
            let fetchRequest: NSFetchRequest<MediaEntity> = MediaEntity.fetchRequest()

            do {
                let entities = try context.fetch(fetchRequest)
                for entity in entities {
                    entity.localFilePath = nil
                    entity.downloadedAt = nil
                }
                self.coreDataStack.saveContext(context)
            } catch {
                print("MediaStorageManager: Failed to clear media entities: \(error)")
            }
        }
    }

    // MARK: - Media Data Retrieval (for backward compatibility with old code)

    func getMediaData(mediaId: Int) async throws -> Data {
        // Check if we have it locally first
        if let localPath = await getLocalMediaPath(for: mediaId) {
            if fileManager.fileExists(atPath: localPath.path) {
                print("📱 MediaStorageManager: Loading media \(mediaId) from local storage (offline: \(!dataRepository.isOnline))")
                return try Data(contentsOf: localPath)
            }
        }

        // Check if offline before attempting download
        guard dataRepository.isOnline else {
            print("⚠️ MediaStorageManager: Cannot load media \(mediaId) - not cached and offline")
            throw NSError(domain: "MediaStorageManager", code: -1, userInfo: [NSLocalizedDescriptionKey: "Media not available offline"])
        }

        // Download if not available
        print("⬇️ MediaStorageManager: Downloading media \(mediaId)")
        let localURL = try await downloadAndStoreMedia(mediaId: mediaId)
        return try Data(contentsOf: localURL)
    }
}
