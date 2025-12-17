//
//  SyncManager.swift
//  SnapStash
//
//  Created by Claude Code
//

import Foundation
import BackgroundTasks
import Combine

class SyncManager: ObservableObject {
    static let shared = SyncManager()

    private let dataRepository = DataRepository.shared
    private let mediaStorage = MediaStorageManager.shared
    @Published var isSyncing: Bool = false
    @Published var syncProgress: Double = 0.0
    @Published var lastError: Error?

    // Background task identifier
    private let backgroundTaskIdentifier = "com.georgesaker147.snapstash.sync"
    private var isBackgroundTaskRegistered = false

    private init() {
        // Don't register here - will be called from AppDelegate
    }

    // MARK: - Background Task Registration

    func registerBackgroundTasks() {
        // Only register once
        guard !isBackgroundTaskRegistered else {
            print("SyncManager: Background task already registered, skipping")
            return
        }

        let success = BGTaskScheduler.shared.register(forTaskWithIdentifier: backgroundTaskIdentifier, using: nil) { task in
            self.handleBackgroundSync(task: task as! BGAppRefreshTask)
        }

        if success {
            isBackgroundTaskRegistered = true
            print("SyncManager: Background task registered successfully")
        } else {
            print("SyncManager: Failed to register background task")
        }
    }

    func scheduleBackgroundSync() {
        let request = BGAppRefreshTaskRequest(identifier: backgroundTaskIdentifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: 15 * 60) // 15 minutes from now

        do {
            try BGTaskScheduler.shared.submit(request)
            print("SyncManager: Background sync scheduled")
        } catch {
            print("SyncManager: Failed to schedule background sync: \(error)")
        }
    }

    private func handleBackgroundSync(task: BGAppRefreshTask) {
        // Schedule next sync
        scheduleBackgroundSync()

        // Create background task
        let syncTask = Task {
            await performSync(downloadMedia: false) // Don't download media in background to save data
        }

        // Handle task expiration
        task.expirationHandler = {
            syncTask.cancel()
        }

        // Complete the task when sync finishes
        Task {
            await syncTask.value
            task.setTaskCompleted(success: self.lastError == nil)
        }
    }

    // MARK: - Manual Sync

    @MainActor
    func performManualSync(downloadMedia: Bool = true) async {
        guard !isSyncing else {
            print("SyncManager: Sync already in progress")
            return
        }

        // Always check connectivity when manually syncing
        print("🔄 Manual sync requested - checking connectivity...")
        dataRepository.checkConnectivity()
        // Give connectivity check a moment to complete
        try? await Task.sleep(nanoseconds: 500_000_000) // 500ms

        isSyncing = true
        syncProgress = 0.0
        lastError = nil

        await performSync(downloadMedia: downloadMedia)

        isSyncing = false
        syncProgress = 1.0
    }

    private func performSync(downloadMedia: Bool) async {
        print("SyncManager: Starting sync...")

        // Skip sync if offline
        guard dataRepository.isOnline else {
            print("SyncManager: Skipping sync (offline mode)")
            return
        }

        do {
            // Step 0: Sync current user (10%)
            await updateProgress(0.05)
            do {
                _ = try await dataRepository.fetchCurrentUser(forceRefresh: true)
                print("SyncManager: Synced current user")
            } catch {
                print("SyncManager: Failed to sync current user: \(error)")
            }

            // Step 1: Sync conversations (20%)
            await updateProgress(0.1)
            let conversations = try await dataRepository.fetchConversations(forceRefresh: true)
            print("SyncManager: Synced \(conversations.count) conversations")
            await updateProgress(0.2)

            // Step 2: Sync messages for top conversations (60%)
            let topConversations = Array(conversations.prefix(10))
            let progressPerConversation = 0.6 / Double(topConversations.count)

            for (index, conversation) in topConversations.enumerated() {
                do {
                    let messages = try await dataRepository.fetchMessages(for: conversation.id, limit: 100, forceRefresh: true)
                    print("SyncManager: Synced \(messages.count) messages for conversation \(conversation.id)")

                    // Download media for this conversation if requested
                    if downloadMedia {
                        await mediaStorage.downloadMediaForConversation(conversation.id, limit: 50)
                    }

                    await updateProgress(0.2 + Double(index + 1) * progressPerConversation)
                } catch {
                    print("SyncManager: Failed to sync conversation \(conversation.id): \(error)")
                }
            }

            // Step 3: Cleanup old data (20%)
            await updateProgress(0.8)
            await cleanupOldData()
            await updateProgress(1.0)

            print("SyncManager: Sync completed successfully")

        } catch {
            print("SyncManager: Sync failed: \(error)")
            await MainActor.run {
                self.lastError = error
            }
        }
    }

    @MainActor
    private func updateProgress(_ progress: Double) {
        self.syncProgress = progress
    }

    // MARK: - Cleanup

    private func cleanupOldData() async {
        // Remove messages older than 30 days
        CoreDataStack.shared.cleanupOldMessages(olderThan: 30)

        // Cleanup old media files if storage is full
        let storageSize = await mediaStorage.getCurrentStorageSize()
        let maxSize = 500 * 1024 * 1024 // 500 MB

        if storageSize > Int64(maxSize * 3 / 4) {
            await mediaStorage.cleanupOldMedia()
        }
    }

    // MARK: - Incremental Sync

    func syncConversation(_ conversationId: String) async {
        // Always attempt to check connectivity for conversation sync
        if !dataRepository.isOnline {
            print("🔄 Conversation sync requested while offline - checking connectivity...")
            dataRepository.checkConnectivity()
            // Give connectivity check a moment to complete
            try? await Task.sleep(nanoseconds: 500_000_000) // 500ms
        }

        // Skip sync if still offline after check
        guard dataRepository.isOnline else {
            print("SyncManager: Skipping conversation sync (offline mode)")
            return
        }

        do {
            _ = try await dataRepository.fetchMessages(for: conversationId, limit: 100, forceRefresh: true)
            await mediaStorage.downloadMediaForConversation(conversationId, limit: 50)
            print("SyncManager: Synced conversation \(conversationId)")
        } catch {
            print("SyncManager: Failed to sync conversation \(conversationId): \(error)")
        }
    }

    // MARK: - App Lifecycle

    func handleAppForeground() {
        // Check connectivity
        dataRepository.checkConnectivity()

        // Perform quick sync if last sync was more than 1 hour ago
        Task {
            if let lastSync = await dataRepository.getLastSyncDate(for: "conversations") {
                let hoursSinceSync = Date().timeIntervalSince(lastSync) / 3600

                if hoursSinceSync > 1 {
                    await performManualSync(downloadMedia: false)
                }
            } else {
                // No previous sync, do full sync
                await performManualSync(downloadMedia: true)
            }
        }
    }

    func handleAppBackground() {
        // Schedule background sync
        scheduleBackgroundSync()
    }
}
