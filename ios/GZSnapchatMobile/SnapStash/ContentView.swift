//
//  ContentView.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI

struct ContentView: View {
    @EnvironmentObject var apiService: APIService
    @EnvironmentObject var deepLinkManager: DeepLinkManager
    @StateObject private var syncManager = SyncManager.shared

    var body: some View {
        NavigationView {
            ConversationListView()
        }
        .task {
            // Offline-first: Load immediately from local storage, sync in background
            syncManager.handleAppForeground()
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in
            syncManager.handleAppForeground()
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.didEnterBackgroundNotification)) { _ in
            syncManager.handleAppBackground()
        }
    }
}

#Preview {
    ContentView()
        .environmentObject(APIService())
        .environmentObject(DeepLinkManager())
}
