//
//  SettingsView.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import Combine
import Contacts

// MARK: - Theme Settings
class ThemeSettings: ObservableObject {
    @Published var senderBubbleRed: Double {
        didSet { UserDefaults.standard.set(senderBubbleRed, forKey: "senderBubbleRed") }
    }
    @Published var senderBubbleGreen: Double {
        didSet { UserDefaults.standard.set(senderBubbleGreen, forKey: "senderBubbleGreen") }
    }
    @Published var senderBubbleBlue: Double {
        didSet { UserDefaults.standard.set(senderBubbleBlue, forKey: "senderBubbleBlue") }
    }
    @Published var senderBubbleOpacity: Double {
        didSet { UserDefaults.standard.set(senderBubbleOpacity, forKey: "senderBubbleOpacity") }
    }
    
    @Published var recipientBubbleRed: Double {
        didSet { UserDefaults.standard.set(recipientBubbleRed, forKey: "recipientBubbleRed") }
    }
    @Published var recipientBubbleGreen: Double {
        didSet { UserDefaults.standard.set(recipientBubbleGreen, forKey: "recipientBubbleGreen") }
    }
    @Published var recipientBubbleBlue: Double {
        didSet { UserDefaults.standard.set(recipientBubbleBlue, forKey: "recipientBubbleBlue") }
    }
    @Published var recipientBubbleOpacity: Double {
        didSet { UserDefaults.standard.set(recipientBubbleOpacity, forKey: "recipientBubbleOpacity") }
    }
    
    init() {
        let defaults = UserDefaults.standard
        self.senderBubbleRed = defaults.object(forKey: "senderBubbleRed") as? Double ?? 1.0
        self.senderBubbleGreen = defaults.object(forKey: "senderBubbleGreen") as? Double ?? 0.84
        self.senderBubbleBlue = defaults.object(forKey: "senderBubbleBlue") as? Double ?? 0.0
        self.senderBubbleOpacity = defaults.object(forKey: "senderBubbleOpacity") as? Double ?? 1.0
        self.recipientBubbleRed = defaults.object(forKey: "recipientBubbleRed") as? Double ?? 0.5
        self.recipientBubbleGreen = defaults.object(forKey: "recipientBubbleGreen") as? Double ?? 0.5
        self.recipientBubbleBlue = defaults.object(forKey: "recipientBubbleBlue") as? Double ?? 0.5
        self.recipientBubbleOpacity = defaults.object(forKey: "recipientBubbleOpacity") as? Double ?? 0.2
    }
    
    var senderBubbleColor: Color {
        Color(red: senderBubbleRed, green: senderBubbleGreen, blue: senderBubbleBlue).opacity(senderBubbleOpacity)
    }
    
    var recipientBubbleColor: Color {
        Color(red: recipientBubbleRed, green: recipientBubbleGreen, blue: recipientBubbleBlue).opacity(recipientBubbleOpacity)
    }
    
    func resetToDefaults() {
        senderBubbleRed = 1.0
        senderBubbleGreen = 0.84
        senderBubbleBlue = 0.0
        senderBubbleOpacity = 1.0
        recipientBubbleRed = 0.5
        recipientBubbleGreen = 0.5
        recipientBubbleBlue = 0.5
        recipientBubbleOpacity = 0.2
    }
}

struct SettingsView: View {
    @EnvironmentObject var apiService: APIService
    @EnvironmentObject var themeSettings: ThemeSettings
    @Environment(\.dismiss) var dismiss

    @State private var apiURL: String = ""
    @State private var isTestingConnection = false
    @State private var connectionStatus: ConnectionStatus = .unknown
    @State private var showingSaveAlert = false
    
    @State private var senderColor: Color = .yellow
    @State private var recipientColor: Color = Color.gray.opacity(0.2)
    @State private var themeApplied = false

    enum ConnectionStatus {
        case unknown
        case testing
        case success
        case failed(String)

        var color: Color {
            switch self {
            case .unknown: return .gray
            case .testing: return .blue
            case .success: return .green
            case .failed: return .red
            }
        }

        var icon: String {
            switch self {
            case .unknown: return "circle"
            case .testing: return "arrow.clockwise"
            case .success: return "checkmark.circle.fill"
            case .failed: return "xmark.circle.fill"
            }
        }

        var message: String {
            switch self {
            case .unknown: return "Not tested"
            case .testing: return "Testing connection..."
            case .success: return "Connected"
            case .failed(let error): return "Failed: \(error)"
            }
        }
    }

    var body: some View {
        NavigationView {
            Form {
                Section {
                    HStack {
                        Image(systemName: "bubble.left.and.bubble.right.fill")
                            .font(.system(size: 50))
                            .foregroundColor(.yellow)
                        VStack(alignment: .leading) {
                            Text("SnapStash Mobile")
                                .font(.title2)
                                .fontWeight(.bold)
                            Text("iOS Client v1.0")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.vertical, 8)
                } header: {
                    Text("About")
                }

                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("API Base URL")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        TextField("http://localhost:8067", text: $apiURL)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .keyboardType(.URL)
                            .textFieldStyle(.roundedBorder)
                    }

                    HStack {
                        Image(systemName: connectionStatus.icon)
                            .foregroundColor(connectionStatus.color)
                            .imageScale(.large)

                        Text(connectionStatus.message)
                            .font(.subheadline)
                            .foregroundColor(connectionStatus.color)

                        Spacer()

                        if case .testing = connectionStatus {
                            ProgressView()
                                .progressViewStyle(.circular)
                        }
                    }
                    .padding(.vertical, 4)

                    Button(action: testConnection) {
                        HStack {
                            Image(systemName: "network")
                            Text("Test Connection")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .disabled(apiURL.isEmpty || isTestingConnection)

                } header: {
                    Text("Backend Configuration")
                } footer: {
                    Text("Enter the base URL of your SnapStash backend API. Example: http://192.168.1.100:8067")
                }

                Section {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Your Messages")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        ColorPicker("Bubble Color", selection: $senderColor, supportsOpacity: true)
                        
                        // Preview bubble
                        HStack {
                            Spacer()
                            Text("Hello! 👋")
                                .foregroundColor(.white)
                                .padding(12)
                                .background(
                                    RoundedRectangle(cornerRadius: 16)
                                        .fill(senderColor)
                                )
                        }
                    }
                    .padding(.vertical, 4)
                    
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Received Messages")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        
                        ColorPicker("Bubble Color", selection: $recipientColor, supportsOpacity: true)
                        
                        // Preview bubble
                        HStack {
                            Text("Hey there! 😊")
                                .foregroundColor(.primary)
                                .padding(12)
                                .background(
                                    RoundedRectangle(cornerRadius: 16)
                                        .fill(recipientColor)
                                )
                            Spacer()
                        }
                    }
                    .padding(.vertical, 4)
                    
                    Button(action: saveThemeSettings) {
                        HStack {
                            Image(systemName: themeApplied ? "checkmark.circle.fill" : "paintbrush")
                            Text(themeApplied ? "Theme Applied!" : "Apply Theme")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(themeApplied ? .green : .yellow)
                    .animation(.easeInOut(duration: 0.3), value: themeApplied)
                    
                    Button(action: resetTheme) {
                        HStack {
                            Image(systemName: "arrow.counterclockwise")
                            Text("Reset to Default")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                } header: {
                    Text("Message Theme")
                } footer: {
                    Text("Customize the appearance of message bubbles in conversations.")
                }

                ContactPermissionsSection()

                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("This app connects to a SnapStash backend service to display your extracted Snapchat messages and media.")
                            .font(.caption)

                        Text("Make sure your backend is running and accessible from your device.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                } header: {
                    Text("Information")
                }
            }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        dismiss()
                    }
                }
            }
            .onAppear {
                apiURL = apiService.apiBaseURL
                senderColor = themeSettings.senderBubbleColor
                recipientColor = themeSettings.recipientBubbleColor
            }
            .alert("Settings Saved", isPresented: $showingSaveAlert) {
                Button("OK", role: .cancel) {
                    dismiss()
                }
            } message: {
                Text("The API URL has been updated to \(apiURL)")
            }
        }
    }

    private func testConnection() {
        isTestingConnection = true
        connectionStatus = .testing

        Task {
            do {
                // Create a temporary API service with the test URL
                let testService = APIService()
                testService.apiBaseURL = apiURL

                _ = try await testService.checkHealth()
                connectionStatus = .success
            } catch let error as APIError {
                connectionStatus = .failed(error.message)
            } catch {
                connectionStatus = .failed(error.localizedDescription)
            }

            isTestingConnection = false
        }
    }

    private func saveSettings() {
        apiService.apiBaseURL = apiURL
        showingSaveAlert = true
    }
    
    private func saveThemeSettings() {
        let uiColor = UIColor(senderColor)
        var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
        uiColor.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
        themeSettings.senderBubbleRed = Double(red)
        themeSettings.senderBubbleGreen = Double(green)
        themeSettings.senderBubbleBlue = Double(blue)
        themeSettings.senderBubbleOpacity = Double(alpha)
        
        let recipientUIColor = UIColor(recipientColor)
        recipientUIColor.getRed(&red, green: &green, blue: &blue, alpha: &alpha)
        themeSettings.recipientBubbleRed = Double(red)
        themeSettings.recipientBubbleGreen = Double(green)
        themeSettings.recipientBubbleBlue = Double(blue)
        themeSettings.recipientBubbleOpacity = Double(alpha)
        
        // Show visual feedback
        withAnimation {
            themeApplied = true
        }
        
        // Reset after delay
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
            withAnimation {
                themeApplied = false
            }
        }
    }
    
    private func resetTheme() {
        themeSettings.resetToDefaults()
        senderColor = themeSettings.senderBubbleColor
        recipientColor = themeSettings.recipientBubbleColor
    }
}

// MARK: - Contact Permissions Section
struct ContactPermissionsSection: View {
    @ObservedObject var contactsManager = ContactsManager.shared
    @State private var isRequesting = false
    
    private var statusText: String {
        switch contactsManager.authorizationStatus {
        case .notDetermined:
            return "Not requested"
        case .restricted:
            return "Restricted"
        case .denied:
            return "Denied - Enable in Settings"
        case .authorized:
            return "Enabled (\(contactsManager.contacts.count) contacts)"
        @unknown default:
            return "Unknown"
        }
    }
    
    private var statusColor: Color {
        switch contactsManager.authorizationStatus {
        case .authorized:
            return .green
        case .denied, .restricted:
            return .red
        default:
            return .gray
        }
    }
    
    private var statusIcon: String {
        switch contactsManager.authorizationStatus {
        case .authorized:
            return "checkmark.circle.fill"
        case .denied, .restricted:
            return "xmark.circle.fill"
        default:
            return "circle"
        }
    }
    
    var body: some View {
        Section {
            HStack {
                Image(systemName: "person.crop.circle")
                    .foregroundColor(.blue)
                    .imageScale(.large)
                
                VStack(alignment: .leading, spacing: 2) {
                    Text("Contact Photos")
                        .font(.body)
                    Text("Match profile pictures from contacts")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                
                Spacer()
                
                HStack(spacing: 4) {
                    Image(systemName: statusIcon)
                        .foregroundColor(statusColor)
                    Text(statusText)
                        .font(.caption)
                        .foregroundColor(statusColor)
                }
            }
            
            if contactsManager.authorizationStatus == .notDetermined {
                Button(action: requestAccess) {
                    HStack {
                        if isRequesting {
                            ProgressView()
                                .progressViewStyle(.circular)
                        } else {
                            Image(systemName: "person.crop.circle.badge.plus")
                        }
                        Text("Enable Contact Matching")
                    }
                    .frame(maxWidth: .infinity)
                }
                .disabled(isRequesting)
            } else if contactsManager.authorizationStatus == .denied {
                Button(action: openSettings) {
                    HStack {
                        Image(systemName: "gear")
                        Text("Open Settings")
                    }
                    .frame(maxWidth: .infinity)
                }
            } else if contactsManager.authorizationStatus == .authorized {
                Button(action: refreshContacts) {
                    HStack {
                        if contactsManager.isLoading {
                            ProgressView()
                                .progressViewStyle(.circular)
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                        Text("Refresh Contacts")
                    }
                    .frame(maxWidth: .infinity)
                }
                .disabled(contactsManager.isLoading)
            }
        } header: {
            Text("Contact Integration")
        } footer: {
            Text("When enabled, the app will try to match conversation names with your contacts to display their profile photos. You can also manually link conversations to contacts via long-press menu.")
        }
    }
    
    private func requestAccess() {
        isRequesting = true
        Task {
            _ = await contactsManager.requestAccess()
            await MainActor.run {
                isRequesting = false
            }
        }
    }
    
    private func openSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }
    
    private func refreshContacts() {
        Task {
            await contactsManager.fetchContacts()
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(APIService())
        .environmentObject(ThemeSettings())
}
