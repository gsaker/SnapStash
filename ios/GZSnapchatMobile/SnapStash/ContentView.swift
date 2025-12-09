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
    @State private var isHealthy: Bool?
    @State private var isCheckingHealth = false
    @State private var showSettings = false

    var body: some View {
        NavigationView {
            Group {
                if isHealthy == nil {
                    // Loading state
                    VStack(spacing: 20) {
                        ProgressView()
                            .progressViewStyle(.circular)
                            .scaleEffect(1.5)
                        Text("Connecting to backend...")
                            .font(.headline)
                            .foregroundColor(.secondary)
                    }
                } else if isHealthy == false {
                    // Error state
                    VStack(spacing: 20) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .font(.system(size: 60))
                            .foregroundColor(.red)

                        Text("Backend Unavailable")
                            .font(.title2)
                            .fontWeight(.bold)

                        Text("The SnapStash backend service is not responding. Please make sure it's running and check your settings.")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal, 40)

                        VStack(spacing: 12) {
                            Button(action: { Task { await checkHealth() } }) {
                                HStack {
                                    Image(systemName: "arrow.clockwise")
                                    Text("Retry Connection")
                                }
                                .frame(maxWidth: 200)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.yellow)
                            .disabled(isCheckingHealth)

                            Button(action: { showSettings = true }) {
                                HStack {
                                    Image(systemName: "gear")
                                    Text("Open Settings")
                                }
                                .frame(maxWidth: 200)
                            }
                            .buttonStyle(.bordered)
                        }

                        Text("Current URL: \(apiService.apiBaseURL)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.top)
                    }
                    .padding()
                } else {
                    // Success state - show main app
                    ConversationListView()
                }
            }
            .task {
                await checkHealth()
            }
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
        }
    }

    private func checkHealth() async {
        isCheckingHealth = true
        isHealthy = nil

        do {
            _ = try await apiService.checkHealth()
            isHealthy = true
        } catch {
            print("Health check failed: \(error)")
            isHealthy = false
        }

        isCheckingHealth = false
    }
}

#Preview {
    ContentView()
        .environmentObject(APIService())
        .environmentObject(DeepLinkManager())
}
