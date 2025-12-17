//
//  CoreDataStack.swift
//  SnapStash
//
//  Created by Claude Code
//

import Foundation
import CoreData

class CoreDataStack {
    static let shared = CoreDataStack()

    private init() {}

    lazy var persistentContainer: NSPersistentContainer = {
        let container = NSPersistentContainer(name: "SnapStashDataModel")

        // Use App Group container for shared access between app and extension
        if let appGroupURL = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.georgesaker147.snapstash") {
            let storeURL = appGroupURL.appendingPathComponent("SnapStashDataModel.sqlite")
            let description = NSPersistentStoreDescription(url: storeURL)

            // Enable persistent history tracking for sync
            description.setOption(true as NSNumber, forKey: NSPersistentHistoryTrackingKey)
            description.setOption(true as NSNumber, forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey)

            container.persistentStoreDescriptions = [description]
            print("CoreData: Using App Group storage at \(storeURL.path)")
        } else {
            // Fallback to default location if App Group is not available
            let description = container.persistentStoreDescriptions.first
            description?.setOption(true as NSNumber, forKey: NSPersistentHistoryTrackingKey)
            description?.setOption(true as NSNumber, forKey: NSPersistentStoreRemoteChangeNotificationPostOptionKey)
            print("CoreData: Warning - App Group not available, using default storage")
        }

        container.loadPersistentStores { storeDescription, error in
            if let error = error as NSError? {
                print("CoreData: Failed to load persistent store: \(error), \(error.userInfo)")
            } else {
                print("CoreData: Persistent store loaded successfully at \(storeDescription.url?.absoluteString ?? "unknown location")")
            }
        }

        container.viewContext.automaticallyMergesChangesFromParent = true
        container.viewContext.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy

        return container
    }()

    var viewContext: NSManagedObjectContext {
        return persistentContainer.viewContext
    }

    func newBackgroundContext() -> NSManagedObjectContext {
        let context = persistentContainer.newBackgroundContext()
        context.mergePolicy = NSMergeByPropertyObjectTrumpMergePolicy
        return context
    }

    func saveContext(_ context: NSManagedObjectContext? = nil) {
        let contextToSave = context ?? viewContext

        guard contextToSave.hasChanges else { return }

        contextToSave.perform {
            do {
                try contextToSave.save()
            } catch {
                let nserror = error as NSError
                print("CoreData: Failed to save context: \(nserror), \(nserror.userInfo)")
            }
        }
    }

    func performBackgroundTask(_ block: @escaping (NSManagedObjectContext) -> Void) {
        persistentContainer.performBackgroundTask(block)
    }

    // MARK: - Maintenance

    func deleteAllData() {
        let context = newBackgroundContext()
        context.perform {
            let entities = ["ConversationEntity", "MessageEntity", "MediaEntity", "UserEntity", "SyncMetadataEntity"]

            for entityName in entities {
                let fetchRequest = NSFetchRequest<NSFetchRequestResult>(entityName: entityName)
                let deleteRequest = NSBatchDeleteRequest(fetchRequest: fetchRequest)

                do {
                    try context.execute(deleteRequest)
                    print("CoreData: Deleted all \(entityName) records")
                } catch {
                    print("CoreData: Failed to delete \(entityName): \(error)")
                }
            }

            self.saveContext(context)
        }
    }

    func cleanupOldMessages(olderThan days: Int = 30) {
        let context = newBackgroundContext()
        context.perform {
            let cutoffDate = Date().addingTimeInterval(-TimeInterval(days * 24 * 60 * 60))
            let cutoffTimestamp = Int64(cutoffDate.timeIntervalSince1970 * 1000)

            let fetchRequest = NSFetchRequest<NSFetchRequestResult>(entityName: "MessageEntity")
            fetchRequest.predicate = NSPredicate(format: "creationTimestamp < %lld", cutoffTimestamp)

            let deleteRequest = NSBatchDeleteRequest(fetchRequest: fetchRequest)

            do {
                let result = try context.execute(deleteRequest) as? NSBatchDeleteResult
                if let count = result?.result as? Int {
                    print("CoreData: Cleaned up \(count) old messages")
                }
            } catch {
                print("CoreData: Failed to cleanup old messages: \(error)")
            }

            self.saveContext(context)
        }
    }
}
