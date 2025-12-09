//
//  SnapStashMobileApp.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import Combine

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
        }
    }
}
