//
//  ConversationListView.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import Contacts

struct ConversationListView: View {
    @EnvironmentObject var apiService: APIService
    @EnvironmentObject var deepLinkManager: DeepLinkManager
    @StateObject private var contactsManager = ContactsManager.shared
    @StateObject private var messagePreloader = MessagePreloader.shared
    @State private var conversations: [Conversation] = []
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var searchText = ""
    @State private var showSettings = false
    @State private var showContactPicker = false
    @State private var selectedConversationForContact: Conversation?
    @AppStorage("pinnedConversationIds") private var pinnedConversationIdsData: Data = Data()
    
    // Navigation state for deep links
    @State private var navigationPath = NavigationPath()
    
    // Search state
    @State private var isSearchActive = false
    @State private var searchResults: [SearchResultMessage] = []
    @State private var isSearching = false
    @State private var searchTask: Task<Void, Never>?

    private var pinnedConversationIds: Set<String> {
        get {
            (try? JSONDecoder().decode(Set<String>.self, from: pinnedConversationIdsData)) ?? []
        }
    }

    private func setPinnedConversationIds(_ ids: Set<String>) {
        pinnedConversationIdsData = (try? JSONEncoder().encode(ids)) ?? Data()
    }

    var sortedConversations: [Conversation] {
        let filtered = searchText.isEmpty ? conversations : conversations.filter { conversation in
            (conversation.groupName?.localizedCaseInsensitiveContains(searchText) ?? false) ||
            conversation.id.localizedCaseInsensitiveContains(searchText)
        }
        // Sort: pinned first, then by original order
        return filtered.sorted { conv1, conv2 in
            let pinned1 = pinnedConversationIds.contains(conv1.id)
            let pinned2 = pinnedConversationIds.contains(conv2.id)
            if pinned1 && !pinned2 { return true }
            if !pinned1 && pinned2 { return false }
            return false // Keep original order within each group
        }
    }

    private func togglePin(for conversation: Conversation) {
        var ids = pinnedConversationIds
        if ids.contains(conversation.id) {
            ids.remove(conversation.id)
        } else {
            ids.insert(conversation.id)
        }
        setPinnedConversationIds(ids)
    }

    private func isPinned(_ conversation: Conversation) -> Bool {
        pinnedConversationIds.contains(conversation.id)
    }

    var body: some View {
        NavigationStack(path: $navigationPath) {
            Group {
                if isLoading && conversations.isEmpty {
                    ProgressView("Loading conversations...")
                        .padding()
                } else if let errorMessage = errorMessage {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 50))
                            .foregroundColor(.red)
                        Text("Error")
                            .font(.headline)
                        Text(errorMessage)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                        Button("Retry") {
                            Task {
                                await loadConversations()
                            }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                    .padding()
                } else if conversations.isEmpty {
                    VStack(spacing: 16) {
                        Image(systemName: "bubble.left.and.bubble.right")
                            .font(.system(size: 50))
                            .foregroundColor(.gray)
                        Text("No Conversations")
                            .font(.headline)
                        Text("No conversations found")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    .padding()
                } else {
                    List {
                        // Show search results when searching messages
                        if isSearchActive && !searchText.isEmpty {
                            if isSearching {
                                HStack {
                                    Spacer()
                                    ProgressView()
                                        .padding()
                                    Spacer()
                                }
                            } else if searchResults.isEmpty {
                                HStack {
                                    Spacer()
                                    VStack(spacing: 8) {
                                        Image(systemName: "magnifyingglass")
                                            .font(.title)
                                            .foregroundColor(.secondary)
                                        Text("No messages found")
                                            .foregroundColor(.secondary)
                                    }
                                    .padding()
                                    Spacer()
                                }
                            } else {
                                Section(header: Text("Messages (\(searchResults.count))")) {
                                    ForEach(searchResults) { result in
                                        NavigationLink(destination: ChatView(
                                            conversation: Conversation(
                                                id: result.conversationId,
                                                groupName: result.conversation?.groupName,
                                                isGroupChat: result.conversation?.isGroupChat ?? false,
                                                participantCount: nil,
                                                lastMessageAt: nil,
                                                createdAt: "",
                                                updatedAt: "",
                                                lastMessagePreview: nil
                                            ),
                                            highlightMessageId: result.id
                                        )) {
                                            SearchResultRow(result: result, searchQuery: searchText)
                                        }
                                    }
                                }
                            }
                        } else {
                            // Normal conversation list
                            ForEach(sortedConversations) { conversation in
                                NavigationLink(destination: ChatView(conversation: conversation)) {
                                    ConversationRow(
                                        conversation: conversation,
                                        isPinned: isPinned(conversation),
                                        matchedContact: contactsManager.getMatchedContact(
                                            for: conversation.id,
                                            displayName: conversation.displayName
                                        )
                                    )
                                }
                                .contextMenu {
                                    Button {
                                        togglePin(for: conversation)
                                    } label: {
                                        Label(
                                            isPinned(conversation) ? "Unpin" : "Pin",
                                            systemImage: isPinned(conversation) ? "pin.slash" : "pin"
                                        )
                                    }
                                    
                                    Button {
                                        let url = "SnapStash://conversation?id=\(conversation.id)"
                                        UIPasteboard.general.string = url
                                    } label: {
                                        Label("Copy URL", systemImage: "link")
                                    }
                                    
                                    // Contact matching options
                                    if contactsManager.authorizationStatus == .authorized {
                                        Divider()
                                        
                                        Button {
                                            selectedConversationForContact = conversation
                                            showContactPicker = true
                                        } label: {
                                            Label("Link to Contact", systemImage: "person.crop.circle.badge.plus")
                                        }
                                        
                                        if contactsManager.hasManualMapping(conversationId: conversation.id) {
                                            Button(role: .destructive) {
                                                contactsManager.clearManualMapping(conversationId: conversation.id)
                                            } label: {
                                                Label("Clear Contact Link", systemImage: "person.crop.circle.badge.xmark")
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    .listStyle(.plain)
                    .if(isSearchActive) { view in
                        view.searchable(text: $searchText, isPresented: $isSearchActive, prompt: "Search messages")
                    }
                    .onChange(of: searchText) { _, newValue in
                        searchTask?.cancel()
                        if newValue.isEmpty {
                            searchResults = []
                            isSearching = false
                        } else {
                            searchTask = Task {
                                await performSearch(query: newValue)
                            }
                        }
                    }
                    .refreshable {
                        await loadConversations()
                    }
                }
            }
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: { showSettings = true }) {
                        Image(systemName: "gear")
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    HStack(spacing: 16) {
                        Button(action: { isSearchActive = true }) {
                            Image(systemName: "magnifyingglass")
                        }
                        Button(action: { Task { await loadConversations() } }) {
                            Image(systemName: "arrow.clockwise")
                        }
                        .disabled(isLoading)
                    }
                }
            }
            .toolbarBackground(.visible, for: .navigationBar)
            .sheet(isPresented: $showSettings) {
                SettingsView()
            }
            .sheet(isPresented: $showContactPicker) {
                if let conversation = selectedConversationForContact {
                    ContactPickerView(
                        contactsManager: contactsManager,
                        conversationId: conversation.id,
                        conversationName: conversation.displayName
                    ) { contactId in
                        contactsManager.setManualMapping(conversationId: conversation.id, contactId: contactId)
                    }
                }
            }
            .task {
                await loadConversations()
                // Request contacts access and fetch contacts
                if contactsManager.authorizationStatus == .notDetermined {
                    _ = await contactsManager.requestAccess()
                } else if contactsManager.authorizationStatus == .authorized {
                    await contactsManager.fetchContacts()
                }
            }
            .onChange(of: deepLinkManager.pendingConversationId) { _, conversationId in
                if let conversationId = conversationId {
                    handleDeepLink(conversationId: conversationId)
                }
            }
            .onAppear {
                // Handle deep link if app was opened with one
                if let conversationId = deepLinkManager.pendingConversationId {
                    handleDeepLink(conversationId: conversationId)
                }
            }
            .navigationDestination(for: Conversation.self) { conversation in
                ChatView(conversation: conversation)
            }
        }
    }
    
    private func handleDeepLink(conversationId: String) {
        // First check if we have this conversation loaded
        if let conversation = conversations.first(where: { $0.id == conversationId }) {
            navigationPath.append(conversation)
            deepLinkManager.clearPendingConversation()
        } else {
            // If conversations aren't loaded yet, or conversation not found, 
            // create a minimal conversation object to navigate to
            let conversation = Conversation(
                id: conversationId,
                groupName: nil,
                isGroupChat: false,
                participantCount: nil,
                lastMessageAt: nil,
                createdAt: "",
                updatedAt: "",
                lastMessagePreview: nil
            )
            navigationPath.append(conversation)
            deepLinkManager.clearPendingConversation()
        }
    }

    private func loadConversations() async {
        isLoading = true
        errorMessage = nil

        do {
            let response = try await apiService.getConversations(limit: 100, offset: 0, excludeAds: true)
            conversations = response.conversations
            
            // Preload messages for top conversations in background
            Task.detached(priority: .background) {
                await MessagePreloader.shared.preloadTopConversations(response.conversations, using: apiService)
            }
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
    
    private func performSearch(query: String) async {
        guard !query.isEmpty else { return }
        
        isSearching = true
        
        // Debounce - wait briefly before searching
        try? await Task.sleep(nanoseconds: 300_000_000) // 300ms
        
        // Check if task was cancelled
        if Task.isCancelled { return }
        
        do {
            let response = try await apiService.searchMessages(query: query, limit: 100)
            if !Task.isCancelled {
                searchResults = response.results
            }
        } catch {
            print("Search error: \(error)")
            if !Task.isCancelled {
                searchResults = []
            }
        }
        
        if !Task.isCancelled {
            isSearching = false
        }
    }
}

// MARK: - Search Result Row
struct SearchResultRow: View {
    let result: SearchResultMessage
    let searchQuery: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            // Conversation name and timestamp
            HStack {
                Text(result.conversation?.displayName ?? "Unknown")
                    .font(.headline)
                    .lineLimit(1)
                Spacer()
                Text(formatDate(result.date))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
            // Sender info
            if let sender = result.sender {
                Text(sender.displayName ?? sender.username)
                    .font(.caption)
                    .foregroundColor(.blue)
            }
            
            // Message text with highlighted search term
            if let text = result.text {
                HighlightedText(text: text.htmlDecoded, highlight: searchQuery)
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(2)
            }
        }
        .padding(.vertical, 4)
    }
    
    private func formatDate(_ date: Date) -> String {
        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            let formatter = DateFormatter()
            formatter.timeStyle = .short
            return formatter.string(from: date)
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else {
            let formatter = DateFormatter()
            formatter.dateStyle = .short
            return formatter.string(from: date)
        }
    }
}

// MARK: - Highlighted Text View
struct HighlightedText: View {
    let text: String
    let highlight: String
    
    private var highlightedText: Text {
        guard !highlight.isEmpty else {
            return Text(text)
        }
        
        var result = Text("")
        let lowercasedText = text.lowercased()
        let lowercasedHighlight = highlight.lowercased()
        var currentIndex = text.startIndex
        
        while let range = lowercasedText[currentIndex...].range(of: lowercasedHighlight) {
            // Add text before the match
            if currentIndex < range.lowerBound {
                let beforeRange = currentIndex..<range.lowerBound
                result = result + Text(String(text[beforeRange]))
            }
            
            // Add the highlighted match (using original case)
            let originalRange = Range(uncheckedBounds: (
                lower: text.index(text.startIndex, offsetBy: lowercasedText.distance(from: lowercasedText.startIndex, to: range.lowerBound)),
                upper: text.index(text.startIndex, offsetBy: lowercasedText.distance(from: lowercasedText.startIndex, to: range.upperBound))
            ))
            result = result + Text(String(text[originalRange])).bold().foregroundColor(.primary)
            
            currentIndex = range.upperBound
        }
        
        // Add remaining text after last match
        if currentIndex < text.endIndex {
            result = result + Text(String(text[currentIndex...]))
        }
        
        return result
    }
    
    var body: some View {
        highlightedText
    }
}

struct ConversationRow: View {
    let conversation: Conversation
    var isPinned: Bool = false
    var matchedContact: MatchedContact? = nil

    private var avatarColor: Color {
        conversation.isGroupChat ? .blue : .green
    }

    private var initials: String {
        let name = conversation.displayName
        let components = name.components(separatedBy: " ")
        if components.count >= 2 {
            let first = components[0].prefix(1)
            let last = components[1].prefix(1)
            return "\(first)\(last)".uppercased()
        } else {
            return String(name.prefix(2)).uppercased()
        }
    }

    var body: some View {
        HStack(spacing: 12) {
            // Avatar - use contact photo if available
            ContactPhotoView(
                contact: conversation.isGroupChat ? nil : matchedContact,
                fallbackInitials: initials,
                fallbackColor: avatarColor,
                size: 50
            )

            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    if isPinned {
                        Image(systemName: "pin.fill")
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    
                    Text(conversation.displayName)
                        .font(.headline)
                        .lineLimit(1)

                    Spacer()

                    if let lastMessageAt = conversation.lastMessageAt {
                        Text(formatTimestamp(lastMessageAt))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Last message preview
                HStack(spacing: 4) {
                    if let preview = conversation.lastMessagePreview {
                        if preview.hasMedia {
                            // Show media icon based on type
                            Image(systemName: mediaIconName(for: preview.mediaType))
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            Text(mediaLabel(for: preview.mediaType, text: preview.text?.htmlDecoded))
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        } else if let text = preview.text, !text.isEmpty {
                            Text(text.htmlDecoded)
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        } else {
                            Text(conversation.isGroupChat ? "\(conversation.participantCount ?? 0) participants" : "No messages")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                        }
                    } else {
                        Text(conversation.isGroupChat ? "\(conversation.participantCount ?? 0) participants" : "No messages")
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }
            }
        }
        .padding(.vertical, 4)
    }

    private func formatTimestamp(_ timestamp: String) -> String {
        let formatter = ISO8601DateFormatter()
        guard let date = formatter.date(from: timestamp) else {
            return ""
        }

        let calendar = Calendar.current
        if calendar.isDateInToday(date) {
            let timeFormatter = DateFormatter()
            timeFormatter.timeStyle = .short
            return timeFormatter.string(from: date)
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else {
            let dateFormatter = DateFormatter()
            dateFormatter.dateStyle = .short
            return dateFormatter.string(from: date)
        }
    }

    private func mediaIconName(for mediaType: String?) -> String {
        switch mediaType?.lowercased() {
        case "image":
            return "photo"
        case "video":
            return "video"
        case "audio":
            return "mic"
        default:
            return "paperclip"
        }
    }

    private func mediaLabel(for mediaType: String?, text: String?) -> String {
        let typeLabel: String
        switch mediaType?.lowercased() {
        case "image":
            typeLabel = "Photo"
        case "video":
            typeLabel = "Video"
        case "audio":
            typeLabel = "Voice Note"
        default:
            typeLabel = "Media"
        }

        if let text = text, !text.isEmpty {
            return "\(typeLabel) · \(text)"
        }
        return typeLabel
    }
}

#Preview {
    ConversationListView()
        .environmentObject(APIService())
        .environmentObject(DeepLinkManager())
}
