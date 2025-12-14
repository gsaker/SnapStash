//
//  SnapStashMobileApp.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import Combine
import UserNotifications
import Intents

// MARK: - Deep Link Manager
class DeepLinkManager: ObservableObject {
    @Published var pendingConversationId: String?
    
    func handleURL(_ url: URL) {
        // URL format: SnapStash://conversation?id=<conversation_id>
        // or: SnapStash://conversation/<conversation_id>
        guard url.scheme == "SnapStash" else { return }
        
        if url.host == "conversation" {
            // Check for query parameter: SnapStash://conversation?id=abc123
            if let components = URLComponents(url: url, resolvingAgainstBaseURL: false),
               let queryItems = components.queryItems,
               let conversationId = queryItems.first(where: { $0.name == "id" })?.value {
                pendingConversationId = conversationId
            }
            // Check for path parameter: SnapStash://conversation/abc123
            else if !url.pathComponents.isEmpty {
                let pathId = url.pathComponents.filter { $0 != "/" }.first
                if let conversationId = pathId {
                    pendingConversationId = conversationId
                }
            }
        }
    }
    
    func clearPendingConversation() {
        pendingConversationId = nil
    }
}

@main
struct SnapStashMobileApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate
    @StateObject private var apiService = APIService()
    @StateObject private var themeSettings = ThemeSettings()
    @StateObject private var deepLinkManager = DeepLinkManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(apiService)
                .environmentObject(themeSettings)
                .environmentObject(deepLinkManager)
                .onOpenURL { url in
                    deepLinkManager.handleURL(url)
                }
                .onReceive(NotificationCenter.default.publisher(for: .openConversation)) { notification in
                    if let conversationId = notification.userInfo?["conversationId"] as? String {
                        deepLinkManager.pendingConversationId = conversationId
                    }
                }
        }
    }
}

// MARK: - App Delegate for Push Notifications
class AppDelegate: NSObject, UIApplicationDelegate {
    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey : Any]? = nil) -> Bool {
        print("📱 SnapStash app launching...")

        // Request notification permissions
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if granted {
                print("✅ Notification permission granted")
                DispatchQueue.main.async {
                    application.registerForRemoteNotifications()
                }
            } else if let error = error {
                print("❌ Notification permission error: \(error)")
            } else {
                print("⚠️ Notification permission denied by user")
            }
        }

        // Set notification delegate
        UNUserNotificationCenter.current().delegate = self
        registerNotificationCategories()

        return true
    }

    private func registerNotificationCategories() {
        let messageCategory = UNNotificationCategory(
            identifier: "message",
            actions: [],
            intentIdentifiers: ["INSendMessageIntent"],
            options: []
        )
        UNUserNotificationCenter.current().setNotificationCategories([messageCategory])
    }

    // MARK: - Remote Notification Registration

    func application(_ application: UIApplication,
                     didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        print("📱 Device token received: \(token)")

        // Save token locally in shared storage
        UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.set(token, forKey: "deviceToken")

        // Send token to backend
        Task {
            await registerDeviceToken(token)
        }
    }

    func application(_ application: UIApplication,
                     didFailToRegisterForRemoteNotificationsWithError error: Error) {
        print("❌ Failed to register for remote notifications: \(error)")

        // Check if we're in simulator
        #if targetEnvironment(simulator)
        print("⚠️ Push notifications don't work in the simulator - use a real device")
        #endif
    }

    // MARK: - Device Token Registration

    private func registerDeviceToken(_ token: String) async {
        guard let apiURL = UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.string(forKey: "apiBaseURL") else {
            print("⚠️ No API URL configured, will register token when API URL is set")
            return
        }

        do {
            let apiService = APIService()
            apiService.apiBaseURL = apiURL
            let success = try await apiService.registerDeviceToken(token)

            if success {
                print("✅ Device token registered with backend")
                UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.set(true, forKey: "deviceTokenRegistered")
            }
        } catch {
            print("❌ Failed to register device token with backend: \(error)")
            UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.set(false, forKey: "deviceTokenRegistered")
        }
    }
}

// MARK: - Notification Delegate
extension AppDelegate: UNUserNotificationCenterDelegate {
    // Handle notification when app is in foreground
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                               willPresent notification: UNNotification,
                               withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        print("📬 Notification received while app in foreground")

        // Show notification banner, play sound, and update badge even when app is open
        completionHandler([.banner, .sound, .badge])
    }

    // Handle notification tap
    func userNotificationCenter(_ center: UNUserNotificationCenter,
                               didReceive response: UNNotificationResponse,
                               withCompletionHandler completionHandler: @escaping () -> Void) {
        print("📬 Notification tapped")

        let userInfo = response.notification.request.content.userInfo

        // Check for conversation_id in custom data
        if let conversationId = userInfo["conversation_id"] as? String {
            print("📂 Opening conversation: \(conversationId)")

            // Post notification to open conversation
            NotificationCenter.default.post(
                name: .openConversation,
                object: nil,
                userInfo: ["conversationId": conversationId]
            )
        } else {
            print("⚠️ No conversation_id in notification payload")
        }

        completionHandler()
    }
}

// MARK: - Notification Name Extension
extension Notification.Name {
    static let openConversation = Notification.Name("openConversation")
}
