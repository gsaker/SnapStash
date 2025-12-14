//
//  SettingsView.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import Combine
import Contacts

// MARK: - Avatar Source Setting
enum AvatarSource: String, CaseIterable {
    case bitmoji = "bitmoji"
    case contacts = "contacts"
    case initials = "initials"
    
    var displayName: String {
        switch self {
        case .bitmoji: return "Snapchat Bitmoji"
        case .contacts: return "Device Contacts"
        case .initials: return "Initials Only"
        }
    }
    
    var icon: String {
        switch self {
        case .bitmoji: return "face.smiling"
        case .contacts: return "person.crop.circle"
        case .initials: return "textformat"
        }
    }
    
    var description: String {
        switch self {
        case .bitmoji: return "Use Snapchat Bitmoji avatars from the server"
        case .contacts: return "Match conversations with device contacts"
        case .initials: return "Show initials only (no photos)"
        }
    }
}

class AvatarSettings: ObservableObject {
    static let shared = AvatarSettings()
    
    @Published var avatarSource: AvatarSource {
        didSet {
            UserDefaults.standard.set(avatarSource.rawValue, forKey: "avatarSource")
        }
    }
    
    init() {
        let savedSource = UserDefaults.standard.string(forKey: "avatarSource") ?? AvatarSource.bitmoji.rawValue
        self.avatarSource = AvatarSource(rawValue: savedSource) ?? .bitmoji
    }
}

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
    @ObservedObject var avatarSettings = AvatarSettings.shared

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

                AvatarSourceSection()

                // Only show contact permissions if contacts source is selected
                if avatarSettings.avatarSource == .contacts {
                    ContactPermissionsSection()
                }

                PushNotificationsSection()

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

// MARK: - Avatar Source Section
struct AvatarSourceSection: View {
    @ObservedObject var avatarSettings = AvatarSettings.shared
    
    var body: some View {
        Section {
            ForEach(AvatarSource.allCases, id: \.rawValue) { source in
                Button(action: {
                    withAnimation {
                        avatarSettings.avatarSource = source
                    }
                }) {
                    HStack {
                        Image(systemName: source.icon)
                            .foregroundColor(avatarSettings.avatarSource == source ? .yellow : .gray)
                            .frame(width: 24)
                        
                        VStack(alignment: .leading, spacing: 2) {
                            Text(source.displayName)
                                .font(.body)
                                .foregroundColor(.primary)
                            Text(source.description)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        
                        Spacer()
                        
                        if avatarSettings.avatarSource == source {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundColor(.yellow)
                        }
                    }
                }
                .buttonStyle(.plain)
            }
        } header: {
            Text("Avatar Source")
        } footer: {
            Text("Choose how profile pictures are displayed in conversations.")
        }
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

// MARK: - Push Notifications Section
struct PushNotificationsSection: View {
    @State private var notificationStatus: UNAuthorizationStatus = .notDetermined
    @State private var deviceToken: String?
    @State private var isTokenRegistered: Bool = false
    @State private var isSendingTest: Bool = false
    @State private var testResult: String?

    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: 12) {
                // Notification Permission Status
                HStack {
                    Image(systemName: statusIcon)
                        .foregroundColor(statusColor)
                        .imageScale(.large)

                    VStack(alignment: .leading, spacing: 4) {
                        Text("Notification Permission")
                            .font(.subheadline)
                            .fontWeight(.medium)
                        Text(statusText)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    Spacer()
                }
                .padding(.vertical, 4)

                // Device Token Status
                if let token = deviceToken {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Image(systemName: isTokenRegistered ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
                                .foregroundColor(isTokenRegistered ? .green : .orange)
                            Text("Device Token")
                                .font(.subheadline)
                                .fontWeight(.medium)
                        }

                        Text(isTokenRegistered ? "Registered with backend" : "Not registered with backend")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        Text(token.prefix(40) + "...")
                            .font(.system(.caption, design: .monospaced))
                            .foregroundColor(.secondary)
                            .lineLimit(1)
                    }
                    .padding(.vertical, 4)
                }

                // Action buttons
                if notificationStatus == .denied {
                    Button(action: openSettings) {
                        HStack {
                            Image(systemName: "gear")
                            Text("Open Settings")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                } else if notificationStatus == .notDetermined {
                    Button(action: requestPermission) {
                        HStack {
                            Image(systemName: "bell.badge")
                            Text("Enable Notifications")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                } else if notificationStatus == .authorized && isTokenRegistered {
                    Button(action: sendTestNotification) {
                        HStack {
                            if isSendingTest {
                                ProgressView()
                                    .progressViewStyle(.circular)
                                    .padding(.trailing, 4)
                            }
                            Image(systemName: "bell.badge.fill")
                            Text(isSendingTest ? "Sending..." : "Send Test Notification")
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.bordered)
                    .disabled(isSendingTest)

                    // Show test result
                    if let testResult = testResult {
                        HStack {
                            Image(systemName: testResult.contains("✅") ? "checkmark.circle.fill" : "xmark.circle.fill")
                                .foregroundColor(testResult.contains("✅") ? .green : .red)
                            Text(testResult)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        } header: {
            Text("Push Notifications")
        } footer: {
            Text("Receive push notifications when new messages arrive. Requires backend APNs configuration.")
        }
        .onAppear {
            checkNotificationStatus()
            loadDeviceToken()
        }
    }

    private var statusIcon: String {
        switch notificationStatus {
        case .authorized:
            return "bell.fill"
        case .denied:
            return "bell.slash.fill"
        case .notDetermined:
            return "bell"
        case .provisional:
            return "bell.badge"
        case .ephemeral:
            return "bell"
        @unknown default:
            return "bell"
        }
    }

    private var statusColor: Color {
        switch notificationStatus {
        case .authorized, .provisional:
            return .green
        case .denied:
            return .red
        case .notDetermined, .ephemeral:
            return .orange
        @unknown default:
            return .gray
        }
    }

    private var statusText: String {
        switch notificationStatus {
        case .authorized:
            return "Enabled"
        case .denied:
            return "Denied - Enable in Settings"
        case .notDetermined:
            return "Not Requested"
        case .provisional:
            return "Provisional"
        case .ephemeral:
            return "Ephemeral"
        @unknown default:
            return "Unknown"
        }
    }

    private func checkNotificationStatus() {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            DispatchQueue.main.async {
                self.notificationStatus = settings.authorizationStatus
            }
        }
    }

    private func loadDeviceToken() {
        let sharedDefaults = UserDefaults(suiteName: "group.com.georgesaker147.snapstash")
        // Try both keys for backwards compatibility
        deviceToken = sharedDefaults?.string(forKey: "deviceToken")
            ?? sharedDefaults?.string(forKey: "apnsDeviceToken")
        isTokenRegistered = sharedDefaults?.bool(forKey: "deviceTokenRegistered") ?? false
    }

    private func requestPermission() {
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            DispatchQueue.main.async {
                if granted {
                    UIApplication.shared.registerForRemoteNotifications()
                }
                checkNotificationStatus()
            }
        }
    }

    private func openSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) {
            UIApplication.shared.open(url)
        }
    }

    private func sendTestNotification() {
        guard let apiBaseURL = UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.string(forKey: "apiBaseURL") else {
            testResult = "❌ No API URL configured"
            return
        }

        isSendingTest = true
        testResult = nil

        Task {
            do {
                guard let url = URL(string: "\(apiBaseURL)/api/test/notification") else {
                    await MainActor.run {
                        testResult = "❌ Invalid URL"
                        isSendingTest = false
                    }
                    return
                }

                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.timeoutInterval = 30

                let body: [String: Any] = [
                    "title": "Test Notification",
                    "body": "This is a test notification from SnapStash!",
                    "conversation_id": "test-conversation"
                ]

                request.httpBody = try JSONSerialization.data(withJSONObject: body)

                let (_, response) = try await URLSession.shared.data(for: request)

                await MainActor.run {
                    if let httpResponse = response as? HTTPURLResponse {
                        if (200...299).contains(httpResponse.statusCode) {
                            testResult = "✅ Test notification sent!"
                        } else {
                            testResult = "❌ Failed: HTTP \(httpResponse.statusCode)"
                        }
                    } else {
                        testResult = "❌ Invalid response"
                    }
                    isSendingTest = false
                }
            } catch {
                await MainActor.run {
                    testResult = "❌ Error: \(error.localizedDescription)"
                    isSendingTest = false
                }
            }
        }
    }
}

#Preview {
    SettingsView()
        .environmentObject(APIService())
        .environmentObject(ThemeSettings())
}
