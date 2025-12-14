//
//  ChatView.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import AVFoundation
import Speech
import QuickLook

// MARK: - View Extension for Conditional Modifiers
extension View {
    @ViewBuilder
    func `if`<Content: View>(_ condition: Bool, transform: (Self) -> Content) -> some View {
        if condition {
            transform(self)
        } else {
            self
        }
    }
}

// MARK: - Identifiable URL Wrapper for Sheet Presentation
struct IdentifiableURL: Identifiable {
    let id = UUID()
    let url: URL
}

struct ChatView: View {
    @EnvironmentObject var apiService: APIService
    let conversation: Conversation
    var highlightMessageId: Int? = nil

    @State private var messages: [Message] = []
    @State private var isLoading = false
    @State private var isLoadingOlder = false
    @State private var errorMessage: String?
    @State private var currentUserId: String?
    @State private var selectedMessage: Message?
    @State private var showMessageDetail = false
    @State private var didLoadInitialMessages = false
    
    // Pagination state
    @State private var hasMoreOlderMessages = true
    @State private var currentOffset = 0
    @State private var scrollToMessageId: Int? = nil
    @State private var scrollToAfterLoad: Int? = nil  // Message to scroll to after loading older messages
    @State private var isLoadingAll = false  // Loading all messages in background
    private let pageSize = 100
    
    // Search state
    @State private var searchText = ""
    @State private var isSearchActive = false
    @State private var searchResults: [SearchResultMessage] = []
    @State private var isSearching = false
    @State private var searchTask: Task<Void, Never>?
    @State private var highlightedMessageId: Int? = nil

    var body: some View {
        VStack(spacing: 0) {
            if isLoading && messages.isEmpty && !didLoadInitialMessages {
                ProgressView("Loading messages...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
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
                            await loadMessages()
                        }
                    }
                    .buttonStyle(.borderedProminent)
                }
                .padding()
            } else if messages.isEmpty && didLoadInitialMessages {
                VStack(spacing: 16) {
                    Image(systemName: "bubble.left")
                        .font(.system(size: 50))
                        .foregroundColor(.gray)
                    Text("No Messages")
                        .font(.headline)
                    Text("No messages in this conversation")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if messages.isEmpty {
                // Still loading - show spinner while we wait for cached or network data
                ProgressView("Loading messages...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(spacing: 8) {
                            // Load more indicator at the top
                            if hasMoreOlderMessages {
                                LoadMoreView(isLoading: isLoadingOlder) {
                                    // Capture the first message ID before loading
                                    if let firstMessageId = messages.first?.id {
                                        scrollToAfterLoad = firstMessageId
                                    }
                                    Task {
                                        await loadOlderMessages()
                                    }
                                }
                                .id("topLoader")
                            }
                            
                            ForEach(Array(messages.enumerated()), id: \.element.id) { index, message in
                                // Show date separator if this is the first message or a different day than previous
                                if shouldShowDateSeparator(for: index) {
                                    DateSeparator(date: message.date)
                                        .padding(.vertical, 8)
                                }
                                
                                MessageBubble(
                                    message: message,
                                    isFromCurrentUser: message.senderId == currentUserId,
                                    showSenderName: shouldShowSenderName(for: index),
                                    onLongPress: {
                                        selectedMessage = message
                                        showMessageDetail = true
                                    }
                                )
                                .id(message.id)
                                .background(
                                    highlightedMessageId == message.id ?
                                    RoundedRectangle(cornerRadius: 12)
                                        .fill(Color.yellow.opacity(0.3))
                                        .padding(-8)
                                    : nil
                                )
                                .animation(.easeInOut(duration: 0.3), value: highlightedMessageId)
                            }
                            
                            // Invisible anchor at the very bottom for reliable scrolling
                            Color.clear
                                .frame(height: 1)
                                .id("bottomAnchor")
                        }
                        .padding()
                    }
                    .defaultScrollAnchor(.bottom)
                    .onChange(of: messages.count) { oldCount, newCount in
                        // After loading older messages, scroll to maintain position
                        if let targetId = scrollToAfterLoad {
                            // Small delay to let SwiftUI finish layout
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                                proxy.scrollTo(targetId, anchor: .top)
                                scrollToAfterLoad = nil
                            }
                        }
                    }
                    .onChange(of: scrollToMessageId) { _, newValue in
                        // Handle scrolling to a specific message (e.g., from search)
                        if let messageId = newValue {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                                withAnimation {
                                    proxy.scrollTo(messageId, anchor: .center)
                                }
                                // Clear after scrolling
                                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                                    scrollToMessageId = nil
                                }
                            }
                        }
                    }
                    .onAppear {
                        // Initial scroll - either to highlighted message or to bottom
                        if let highlightId = highlightMessageId {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) {
                                withAnimation {
                                    proxy.scrollTo(highlightId, anchor: .center)
                                }
                            }
                        } else {
                            // Scroll to bottom
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                                proxy.scrollTo("bottomAnchor", anchor: .bottom)
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(conversation.displayName)
        .navigationBarTitleDisplayMode(.inline)
        .if(isSearchActive) { view in
            view.searchable(text: $searchText, isPresented: $isSearchActive, prompt: "Search in conversation")
        }
        .onChange(of: searchText) { _, newValue in
            searchTask?.cancel()
            if newValue.isEmpty {
                searchResults = []
                isSearching = false
                highlightedMessageId = nil
            } else {
                searchTask = Task {
                    await performSearch(query: newValue)
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                HStack(spacing: 16) {
                    Button(action: { isSearchActive = true }) {
                        Image(systemName: "magnifyingglass")
                    }
                    Button(action: { Task { await loadAllMessages() } }) {
                        if isLoadingAll {
                            ProgressView()
                                .scaleEffect(0.7)
                        } else {
                            Image(systemName: "arrow.down.to.line")
                        }
                    }
                    .disabled(isLoadingAll || !hasMoreOlderMessages)
                    Button(action: { Task { await loadMessages() } }) {
                        Image(systemName: "arrow.clockwise")
                    }
                    .disabled(isLoading)
                }
            }
        }
        .onAppear {
            // Immediately load cached messages if available (synchronous)
            if let cached = MessagePreloader.shared.getCachedMessages(for: conversation.id) {
                print("📦 Instantly loading \(cached.messages.count) preloaded messages for conversation: \(conversation.id)")
                messages = cached.messages
                currentOffset = cached.messages.count
                hasMoreOlderMessages = cached.pagination.hasNext
                didLoadInitialMessages = true
            }
        }
        .task {
            await loadCurrentUser()
            // Only load from network if we don't have cached messages, or to refresh
            if messages.isEmpty {
                await loadMessages()
            }
            // Handle initial highlight if coming from search
            if let highlightId = highlightMessageId {
                highlightedMessageId = highlightId
                // Clear after delay
                DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                    withAnimation {
                        highlightedMessageId = nil
                    }
                }
            }
        }
        .refreshable {
            await loadMessages()
        }
        .overlay {
            // Search results overlay
            if isSearchActive && !searchText.isEmpty {
                ChatSearchResultsOverlay(
                    searchText: searchText,
                    isSearching: isSearching,
                    searchResults: searchResults,
                    onSelectResult: { result in
                        isSearchActive = false
                        searchText = ""
                        searchResults = []
                        // Set the highlight and scroll target
                        highlightedMessageId = result.id
                        scrollToMessageId = result.id
                        
                        // Check if message exists in current messages
                        if !messages.contains(where: { $0.id == result.id }) {
                            // Message not loaded yet - need to load more messages
                            // For now, keep loading older messages until we find it
                            Task {
                                await loadMessagesUntilFound(messageId: result.id)
                            }
                        }
                    },
                    onDismiss: {
                        isSearchActive = false
                        searchText = ""
                        searchResults = []
                    }
                )
            }
        }
        .overlay {
            if showMessageDetail, let message = selectedMessage {
                MessageDetailOverlay(
                    message: message,
                    isFromCurrentUser: message.senderId == currentUserId,
                    isPresented: $showMessageDetail
                )
            }
        }
        .toolbar(showMessageDetail ? .hidden : .visible, for: .navigationBar)
    }

    private func loadCurrentUser() async {
        do {
            let user = try await apiService.getCurrentUser()
            currentUserId = user.id
        } catch {
            // Current user not available, all messages will be shown as from others
            print("Could not fetch current user: \(error)")
        }
    }

    private func loadMessages() async {
        isLoading = true
        errorMessage = nil
        
        // Reset pagination state
        currentOffset = 0
        hasMoreOlderMessages = true

        // Check for preloaded messages first
        if let cached = MessagePreloader.shared.getCachedMessages(for: conversation.id) {
            print("📦 Using preloaded messages for conversation: \(conversation.id) (\(cached.messages.count) messages)")
            messages = cached.messages
            currentOffset = cached.messages.count
            hasMoreOlderMessages = cached.pagination.hasNext
            isLoading = false
            didLoadInitialMessages = true
            return
        }

        do {
            print("🔍 Loading messages for conversation: \(conversation.id)")
            let response = try await apiService.getMessages(
                conversationId: conversation.id,
                limit: pageSize,
                offset: 0
            )
            print("✅ Loaded \(response.messages.count) messages (total: \(response.pagination.total), hasNext: \(response.pagination.hasNext))")
            messages = response.messages.sorted { $0.creationTimestamp < $1.creationTimestamp }
            currentOffset = response.messages.count
            // Use hasNext to check for older messages (API returns newest first, so "next" page = older messages)
            hasMoreOlderMessages = response.pagination.hasNext
            
            // Update preloader cache with fresh data
            MessagePreloader.shared.updateCache(
                for: conversation.id,
                messages: messages,
                pagination: response.pagination
            )
        } catch let error as APIError {
            print("❌ APIError loading messages: \(error.message)")
            errorMessage = error.message
        } catch {
            print("❌ Error loading messages: \(error)")
            errorMessage = error.localizedDescription
        }

        isLoading = false
        didLoadInitialMessages = true
    }
    
    private func loadOlderMessages() async {
        guard !isLoadingOlder && hasMoreOlderMessages else { return }
        
        isLoadingOlder = true
        
        do {
            print("🔍 Loading older messages, offset: \(currentOffset)")
            let response = try await apiService.getMessages(
                conversationId: conversation.id,
                limit: pageSize,
                offset: currentOffset
            )
            print("✅ Loaded \(response.messages.count) older messages (hasNext: \(response.pagination.hasNext))")
            
            if response.messages.isEmpty {
                hasMoreOlderMessages = false
            } else {
                // Prepend older messages (they come sorted by newest first from API, so we need to sort and prepend)
                let olderMessages = response.messages.sorted { $0.creationTimestamp < $1.creationTimestamp }
                // scrollPosition API automatically maintains scroll position when items are prepended
                messages = olderMessages + messages
                currentOffset += response.messages.count
                // Use hasNext to check for more older messages
                hasMoreOlderMessages = response.pagination.hasNext
                
                // Update preloader cache with all loaded messages
                MessagePreloader.shared.updateCache(
                    for: conversation.id,
                    messages: messages,
                    pagination: response.pagination
                )
            }
        } catch {
            print("❌ Error loading older messages: \(error)")
            // Don't show error for pagination failures, just stop loading
            hasMoreOlderMessages = false
        }
        
        isLoadingOlder = false
    }
    
    private func loadAllMessages() async {
        guard !isLoadingAll && hasMoreOlderMessages else { return }
        
        isLoadingAll = true
        
        // Accumulate all older messages first, then update UI once at the end
        var allOlderMessages: [Message] = []
        var tempOffset = currentOffset
        var hasMore = hasMoreOlderMessages
        
        // Keep loading until we have all messages
        while hasMore && !Task.isCancelled {
            do {
                print("🔍 Loading all messages, offset: \(tempOffset)")
                let response = try await apiService.getMessages(
                    conversationId: conversation.id,
                    limit: pageSize,
                    offset: tempOffset
                )
                print("✅ Loaded \(response.messages.count) messages (hasNext: \(response.pagination.hasNext))")
                
                if response.messages.isEmpty {
                    hasMore = false
                } else {
                    // Accumulate older messages (sort and prepend to accumulated list)
                    let olderMessages = response.messages.sorted { $0.creationTimestamp < $1.creationTimestamp }
                    allOlderMessages = olderMessages + allOlderMessages
                    tempOffset += response.messages.count
                    hasMore = response.pagination.hasNext
                }
                
                // Small delay to avoid overwhelming the server
                try? await Task.sleep(nanoseconds: 100_000_000) // 100ms
            } catch {
                print("❌ Error loading all messages: \(error)")
                hasMore = false
                break
            }
        }
        
        // Now update the UI once with all the accumulated messages
        if !allOlderMessages.isEmpty {
            messages = allOlderMessages + messages
            currentOffset = tempOffset
        }
        hasMoreOlderMessages = hasMore
        
        isLoadingAll = false
        print("✅ Finished loading all messages. Total: \(messages.count)")
    }
    
    private func performSearch(query: String) async {
        guard !query.isEmpty else { return }
        
        isSearching = true
        
        // Debounce - wait briefly before searching
        try? await Task.sleep(nanoseconds: 300_000_000) // 300ms
        
        // Check if task was cancelled
        if Task.isCancelled { return }
        
        do {
            let response = try await apiService.searchMessages(
                query: query,
                conversationId: conversation.id,
                limit: 100
            )
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
    
    private func loadMessagesUntilFound(messageId: Int) async {
        // Keep loading older messages until we find the target message
        var maxAttempts = 20 // Limit attempts to prevent infinite loops
        
        while maxAttempts > 0 && hasMoreOlderMessages {
            // Check if message is now in our list
            if messages.contains(where: { $0.id == messageId }) {
                // Found it! Trigger scroll
                DispatchQueue.main.async {
                    scrollToMessageId = messageId
                }
                return
            }
            
            // Load more older messages
            guard !isLoadingOlder else {
                // Wait a bit if already loading
                try? await Task.sleep(nanoseconds: 100_000_000) // 100ms
                continue
            }
            
            isLoadingOlder = true
            
            do {
                let response = try await apiService.getMessages(
                    conversationId: conversation.id,
                    limit: pageSize,
                    offset: currentOffset
                )
                
                if response.messages.isEmpty {
                    hasMoreOlderMessages = false
                } else {
                    let olderMessages = response.messages.sorted { $0.creationTimestamp < $1.creationTimestamp }
                    messages = olderMessages + messages
                    currentOffset += response.messages.count
                    hasMoreOlderMessages = response.pagination.hasNext
                }
            } catch {
                print("❌ Error loading messages while searching: \(error)")
                hasMoreOlderMessages = false
            }
            
            isLoadingOlder = false
            maxAttempts -= 1
        }
        
        // Final check after loading
        if messages.contains(where: { $0.id == messageId }) {
            DispatchQueue.main.async {
                scrollToMessageId = messageId
            }
        }
    }
    
    private func shouldShowDateSeparator(for index: Int) -> Bool {
        if index == 0 { return true }
        
        let currentMessage = messages[index]
        let previousMessage = messages[index - 1]
        
        let calendar = Calendar.current
        return !calendar.isDate(currentMessage.date, inSameDayAs: previousMessage.date)
    }
    
    private func shouldShowSenderName(for index: Int) -> Bool {
        // Never show sender name in direct messages
        guard conversation.isGroupChat else { return false }
        
        let currentMessage = messages[index]
        
        // Don't show sender name if current message has no visible content
        guard currentMessage.hasVisibleContent(isFromCurrentUser: currentMessage.senderId == currentUserId) else {
            return false
        }
        
        // In group chats, show sender name when sender changes from previous visible message
        // Find the previous message that has visible content
        var previousVisibleIndex = index - 1
        while previousVisibleIndex >= 0 {
            let prevMessage = messages[previousVisibleIndex]
            if prevMessage.hasVisibleContent(isFromCurrentUser: prevMessage.senderId == currentUserId) {
                // Found a visible message, check if sender is different
                return currentMessage.senderId != prevMessage.senderId
            }
            previousVisibleIndex -= 1
        }
        
        // No previous visible message found, show sender name
        return true
    }
}

// MARK: - Load More View
struct LoadMoreView: View {
    let isLoading: Bool
    let onLoadMore: () -> Void
    
    var body: some View {
        HStack {
            Spacer()
            if isLoading {
                ProgressView()
                    .scaleEffect(0.8)
                Text("Loading older messages...")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                Button(action: onLoadMore) {
                    HStack(spacing: 8) {
                        Image(systemName: "arrow.up.circle")
                        Text("Load older messages")
                    }
                    .font(.caption)
                    .foregroundColor(.blue)
                }
            }
            Spacer()
        }
        .padding(.vertical, 12)
    }
}

struct DateSeparator: View {
    let date: Date
    
    var body: some View {
        HStack {
            VStack { Divider() }
            Text(formatDate(date))
                .font(.caption)
                .foregroundColor(.secondary)
                .padding(.horizontal, 8)
            VStack { Divider() }
        }
    }
    
    private func formatDate(_ date: Date) -> String {
        let calendar = Calendar.current
        
        if calendar.isDateInToday(date) {
            return "Today"
        } else if calendar.isDateInYesterday(date) {
            return "Yesterday"
        } else if calendar.isDate(date, equalTo: Date(), toGranularity: .weekOfYear) {
            // Same week - show day name
            let formatter = DateFormatter()
            formatter.dateFormat = "EEEE"
            return formatter.string(from: date)
        } else if calendar.isDate(date, equalTo: Date(), toGranularity: .year) {
            // Same year - show month and day
            let formatter = DateFormatter()
            formatter.dateFormat = "d MMMM"
            return formatter.string(from: date)
        } else {
            // Different year - show full date
            let formatter = DateFormatter()
            formatter.dateFormat = "d MMMM yyyy"
            return formatter.string(from: date)
        }
    }
}

struct MessageBubble: View {
    @EnvironmentObject var themeSettings: ThemeSettings
    @EnvironmentObject var apiService: APIService
    let message: Message
    let isFromCurrentUser: Bool
    let showSenderName: Bool
    let onLongPress: () -> Void
    @State private var isPressed = false
    @State private var quickLookURL: IdentifiableURL?
    
    // Check if this is an audio-only message (audio player handles its own long press)
    private var isAudioOnlyMessage: Bool {
        guard let media = message.mediaAsset else { return false }
        let isAudioMessage = message.contentType == 4 || media.isAudio
        // Audio-only if it's an audio message with no text
        return isAudioMessage && (message.text == nil || message.text?.isEmpty == true)
    }

    var body: some View {
        HStack {
            if isFromCurrentUser {
                Spacer()
            }

            VStack(alignment: isFromCurrentUser ? .trailing : .leading, spacing: 4) {
                // Message content - only show if there's something to display
                if message.hasVisibleContent(isFromCurrentUser: isFromCurrentUser) {
                    // Sender name (only in group chats when sender changes)
                    if showSenderName && !isFromCurrentUser, let sender = message.sender {
                        Text(sender.displayName)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 4)
                    }
                    
                    VStack(alignment: .leading, spacing: 8) {
                        // Media preview or sent media indicator
                        if let media = message.mediaAsset {
                            // Check if this is an audio message:
                            // - content_type 4 indicates audio/voice message in Snapchat
                            // - OR the media itself is detected as audio
                            let isAudioMessage = message.contentType == 4 || media.isAudio
                            let _ = print("🎵 Media check - fileType: '\(media.fileType)', mimeType: '\(media.mimeType)', contentType: \(message.contentType), isAudioMessage: \(isAudioMessage)")
                            
                            if isAudioMessage {
                                AudioPlayerView(media: media, isFromCurrentUser: isFromCurrentUser, onLongPress: onLongPress)
                            } else {
                                MediaPreview(media: media)
                                    .onTapGesture {
                                        openInQuickLook(media: media)
                                    }
                            }
                        } else if isFromCurrentUser && (message.text == nil || message.text?.isEmpty == true) {
                            // Show "Media Sent" placeholder for sent messages with no text and no media
                            MediaPlaceholder()
                        }

                        // Text content
                        if let text = message.text, !text.isEmpty {
                            Text(text.htmlDecoded)
                                .foregroundColor(isFromCurrentUser ? .white : .primary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(12)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(isFromCurrentUser ? themeSettings.senderBubbleColor : themeSettings.recipientBubbleColor)
                    )
                    .contentShape(Rectangle())
                    .scaleEffect(isPressed ? 0.95 : 1.0)
                    .animation(.easeInOut(duration: 0.1), value: isPressed)
                    .if(!isAudioOnlyMessage) { view in
                        view.onLongPressGesture(minimumDuration: 0.2, pressing: { pressing in
                            isPressed = pressing
                        }, perform: {
                            let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                            impactFeedback.impactOccurred()
                            onLongPress()
                        })
                    }
                }
            }
            .frame(maxWidth: 280, alignment: isFromCurrentUser ? .trailing : .leading)

            if !isFromCurrentUser {
                Spacer()
            }
        }
        .sheet(item: $quickLookURL) { identifiableURL in
            QuickLookSheet(url: identifiableURL.url)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }
    
    private func openInQuickLook(media: MediaAsset) {
        Task {
            do {
                // Check for preloaded media first
                let mediaData: Data
                if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
                    print("📦 Using preloaded media for QuickLook ID: \(media.id)")
                    mediaData = cachedData
                } else {
                    mediaData = try await apiService.downloadMedia(mediaId: media.id)
                    // Update preloader cache
                    MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: mediaData)
                }
                
                // Determine proper file extension
                let fileExtension: String
                if media.isImage {
                    fileExtension = media.mimeType.contains("png") ? "png" : "jpg"
                } else if media.isVideo {
                    fileExtension = "mp4"
                } else {
                    fileExtension = media.fileType
                }
                
                let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("preview_\(media.id).\(fileExtension)")
                try mediaData.write(to: tempURL)
                
                await MainActor.run {
                    quickLookURL = IdentifiableURL(url: tempURL)
                }
            } catch {
                print("Failed to open media in QuickLook: \(error)")
            }
        }
    }
}

struct MediaPreview: View {
    @EnvironmentObject var apiService: APIService
    let media: MediaAsset
    @State private var imageData: Data?
    @State private var thumbnailImage: UIImage?
    @State private var isLoading = false
    @State private var actualDisplaySize: CGSize?

    // Fixed dimensions for placeholder and max size
    private let maxWidth: CGFloat = 250
    private let maxHeight: CGFloat = 250

    var body: some View {
        Group {
            if let imageData = imageData, let uiImage = UIImage(data: imageData) {
                // Image preview
                let displaySize = calculateDisplaySize(for: uiImage.size)

                Image(uiImage: uiImage)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: displaySize.width, height: displaySize.height)
                    .clipped()
                    .cornerRadius(12)
            } else if let thumbnail = thumbnailImage {
                // Video thumbnail with play button overlay
                let displaySize = calculateDisplaySize(for: thumbnail.size)
                
                ZStack {
                    Image(uiImage: thumbnail)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: displaySize.width, height: displaySize.height)
                        .clipped()
                        .cornerRadius(12)
                    
                    // Play button overlay
                    Circle()
                        .fill(Color.black.opacity(0.5))
                        .frame(width: 60, height: 60)
                    
                    Image(systemName: "play.fill")
                        .font(.system(size: 24))
                        .foregroundColor(.white)
                }
            } else {
                // Placeholder with fixed size to prevent layout shift
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.gray.opacity(0.2))
                    .frame(width: maxWidth, height: maxHeight)
                    .overlay(
                        VStack(spacing: 8) {
                            if isLoading {
                                ProgressView()
                                    .scaleEffect(1.2)
                                Text("Loading...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            } else {
                                Image(systemName: mediaIcon)
                                    .font(.system(size: 40))
                                    .foregroundColor(.gray)
                                Text(media.fileType.capitalized)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                    )
            }
        }
        .task {
            if media.isImage {
                await loadImage()
            } else if media.isVideo {
                await loadVideoThumbnail()
            }
        }
    }

    private func calculateDisplaySize(for imageSize: CGSize) -> CGSize {
        let aspectRatio = imageSize.width / imageSize.height

        if aspectRatio > 1 {
            // Landscape: fit to width
            let width = min(maxWidth, imageSize.width)
            let height = width / aspectRatio
            return CGSize(width: width, height: min(height, maxHeight))
        } else {
            // Portrait or square: fit to height
            let height = min(maxHeight, imageSize.height)
            let width = height * aspectRatio
            return CGSize(width: min(width, maxWidth), height: height)
        }
    }

    private var mediaIcon: String {
        if media.isImage {
            return "photo"
        } else if media.isVideo {
            return "video"
        } else if media.isAudio {
            return "waveform"
        } else {
            return "doc"
        }
    }

    private func loadImage() async {
        // Check for preloaded media first
        if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
            print("📦 Using preloaded image for ID: \(media.id)")
            imageData = cachedData
            return
        }
        
        isLoading = true
        do {
            let data = try await apiService.downloadMedia(mediaId: media.id)
            imageData = data
            // Update preloader cache
            MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: data)
        } catch {
            print("Failed to load image: \(error)")
        }
        isLoading = false
    }
    
    private func loadVideoThumbnail() async {
        // Check for preloaded media first
        if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
            print("📦 Using preloaded video for thumbnail ID: \(media.id)")
            thumbnailImage = await generateThumbnail(from: cachedData)
            return
        }
        
        isLoading = true
        do {
            let videoData = try await apiService.downloadMedia(mediaId: media.id)
            // Update preloader cache
            MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: videoData)
            // Generate thumbnail from video data
            thumbnailImage = await generateThumbnail(from: videoData)
        } catch {
            print("Failed to load video thumbnail: \(error)")
        }
        isLoading = false
    }
    
    private func generateThumbnail(from videoData: Data) async -> UIImage? {
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("thumb_\(media.id).mp4")
        do {
            try videoData.write(to: tempURL)
            let asset = AVURLAsset(url: tempURL)
            let imageGenerator = AVAssetImageGenerator(asset: asset)
            imageGenerator.appliesPreferredTrackTransform = true
            imageGenerator.maximumSize = CGSize(width: 500, height: 500)
            
            let cgImage = try imageGenerator.copyCGImage(at: .zero, actualTime: nil)
            try? FileManager.default.removeItem(at: tempURL)
            return UIImage(cgImage: cgImage)
        } catch {
            print("Failed to generate thumbnail: \(error)")
            try? FileManager.default.removeItem(at: tempURL)
            return nil
        }
    }
}

// MARK: - Enlarged Media Preview (for popup overlay)
struct EnlargedMediaPreview: View {
    @EnvironmentObject var apiService: APIService
    let media: MediaAsset
    let maxWidth: CGFloat
    let maxHeight: CGFloat
    @State private var imageData: Data?
    @State private var thumbnailImage: UIImage?
    @State private var isLoading = false

    var body: some View {
        Group {
            if let imageData = imageData, let uiImage = UIImage(data: imageData) {
                // Image preview
                let displaySize = calculateDisplaySize(for: uiImage.size)

                Image(uiImage: uiImage)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .frame(width: displaySize.width, height: displaySize.height)
                    .clipped()
                    .cornerRadius(12)
            } else if let thumbnail = thumbnailImage {
                // Video thumbnail with play button overlay
                let displaySize = calculateDisplaySize(for: thumbnail.size)
                
                ZStack {
                    Image(uiImage: thumbnail)
                        .resizable()
                        .aspectRatio(contentMode: .fill)
                        .frame(width: displaySize.width, height: displaySize.height)
                        .clipped()
                        .cornerRadius(12)
                    
                    // Play button overlay
                    Circle()
                        .fill(Color.black.opacity(0.5))
                        .frame(width: 70, height: 70)
                    
                    Image(systemName: "play.fill")
                        .font(.system(size: 28))
                        .foregroundColor(.white)
                }
            } else {
                // Placeholder with fixed size to prevent layout shift
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color.gray.opacity(0.2))
                    .frame(width: maxWidth, height: maxHeight)
                    .overlay(
                        VStack(spacing: 8) {
                            if isLoading {
                                ProgressView()
                                    .scaleEffect(1.2)
                                Text("Loading...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            } else {
                                Image(systemName: mediaIcon)
                                    .font(.system(size: 50))
                                    .foregroundColor(.gray)
                                Text(media.fileType.capitalized)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                        }
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(Color.gray.opacity(0.3), lineWidth: 1)
                    )
            }
        }
        .task {
            if media.isImage {
                await loadImage()
            } else if media.isVideo {
                await loadVideoThumbnail()
            }
        }
    }

    private func calculateDisplaySize(for imageSize: CGSize) -> CGSize {
        let aspectRatio = imageSize.width / imageSize.height

        if aspectRatio > 1 {
            // Landscape: fit to width
            let width = min(maxWidth, imageSize.width)
            let height = width / aspectRatio
            return CGSize(width: width, height: min(height, maxHeight))
        } else {
            // Portrait or square: fit to height
            let height = min(maxHeight, imageSize.height)
            let width = height * aspectRatio
            return CGSize(width: min(width, maxWidth), height: height)
        }
    }

    private var mediaIcon: String {
        if media.isImage {
            return "photo"
        } else if media.isVideo {
            return "video"
        } else if media.isAudio {
            return "waveform"
        } else {
            return "doc"
        }
    }

    private func loadImage() async {
        // Check for preloaded media first
        if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
            print("📦 Using preloaded image for enlarged ID: \(media.id)")
            imageData = cachedData
            return
        }
        
        isLoading = true
        do {
            let data = try await apiService.downloadMedia(mediaId: media.id)
            imageData = data
            // Update preloader cache
            MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: data)
        } catch {
            print("Failed to load image: \(error)")
        }
        isLoading = false
    }
    
    private func loadVideoThumbnail() async {
        // Check for preloaded media first
        if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
            print("📦 Using preloaded video for enlarged thumbnail ID: \(media.id)")
            thumbnailImage = await generateThumbnail(from: cachedData)
            return
        }
        
        isLoading = true
        do {
            let videoData = try await apiService.downloadMedia(mediaId: media.id)
            // Update preloader cache
            MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: videoData)
            thumbnailImage = await generateThumbnail(from: videoData)
        } catch {
            print("Failed to load video thumbnail: \(error)")
        }
        isLoading = false
    }
    
    private func generateThumbnail(from videoData: Data) async -> UIImage? {
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("thumb_enlarged_\(media.id).mp4")
        do {
            try videoData.write(to: tempURL)
            let asset = AVURLAsset(url: tempURL)
            let imageGenerator = AVAssetImageGenerator(asset: asset)
            imageGenerator.appliesPreferredTrackTransform = true
            imageGenerator.maximumSize = CGSize(width: 800, height: 800)
            
            let cgImage = try imageGenerator.copyCGImage(at: .zero, actualTime: nil)
            try? FileManager.default.removeItem(at: tempURL)
            return UIImage(cgImage: cgImage)
        } catch {
            print("Failed to generate thumbnail: \(error)")
            try? FileManager.default.removeItem(at: tempURL)
            return nil
        }
    }
}

struct MediaPlaceholder: View {
    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "photo")
                .font(.system(size: 14))
                .foregroundColor(.white.opacity(1))
            
            Text("Media sent")
                .font(.subheadline)
                .foregroundColor(.white.opacity(1))
        }
    }
}

// MARK: - Audio Player View
struct AudioPlayerView: View {
    @EnvironmentObject var apiService: APIService
    let media: MediaAsset
    let isFromCurrentUser: Bool
    var onLongPress: (() -> Void)? = nil
    
    @State private var isLoading = false
    @State private var isPlaying = false
    @State private var audioPlayer: AVAudioPlayer?
    @State private var playbackProgress: Double = 0
    @State private var duration: TimeInterval = 0
    @State private var currentTime: TimeInterval = 0
    @State private var progressTimer: Timer?
    @State private var loadError = false
    @State private var isPressed = false
    @State private var audioFileURL: URL?
    
    private let playerWidth: CGFloat = 200
    
    var body: some View {
        HStack(spacing: 12) {
            // Play/Pause button
            ZStack {
                Circle()
                    .fill(isFromCurrentUser ? Color.white.opacity(0.2) : Color.blue.opacity(0.15))
                    .frame(width: 44, height: 44)
                
                if isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: isFromCurrentUser ? .white : .blue))
                        .scaleEffect(0.8)
                } else {
                    Image(systemName: isPlaying ? "pause.fill" : "play.fill")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundColor(isFromCurrentUser ? .white : .blue)
                }
            }
            .contentShape(Circle())
            .onTapGesture {
                if !isLoading && !loadError {
                    togglePlayback()
                }
            }
            
            VStack(alignment: .leading, spacing: 6) {
                // Waveform visualization / progress bar
                GeometryReader { geometry in
                    ZStack(alignment: .leading) {
                        // Background track
                        WaveformView(isFromCurrentUser: isFromCurrentUser, opacity: 0.3)
                        
                        // Progress overlay
                        WaveformView(isFromCurrentUser: isFromCurrentUser, opacity: 1.0)
                            .mask(
                                Rectangle()
                                    .frame(width: geometry.size.width * playbackProgress)
                            )
                    }
                    .contentShape(Rectangle())
                    .onTapGesture { location in
                        // Tap to seek
                        let progress = max(0, min(1, location.x / geometry.size.width))
                        seek(to: progress)
                    }
                }
                .frame(height: 24)
                
                // Time labels
                HStack {
                    Text(formatTime(currentTime))
                        .font(.caption2)
                        .foregroundColor(isFromCurrentUser ? .white.opacity(0.7) : .secondary)
                    
                    Spacer()
                    
                    Text(formatTime(duration))
                        .font(.caption2)
                        .foregroundColor(isFromCurrentUser ? .white.opacity(0.7) : .secondary)
                }
            }
            .frame(width: playerWidth - 56)
        }
        .frame(width: playerWidth)
        .scaleEffect(isPressed ? 0.95 : 1.0)
        .animation(.easeInOut(duration: 0.1), value: isPressed)
        .contentShape(Rectangle())
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 0.3)
                .onChanged { _ in
                    isPressed = true
                }
                .onEnded { _ in
                    isPressed = false
                    let impactFeedback = UIImpactFeedbackGenerator(style: .medium)
                    impactFeedback.impactOccurred()
                    onLongPress?()
                }
        )
        .onDisappear {
            stopPlayback()
        }
    }
    
    // Expose the audio file URL for transcription
    func getAudioFileURL() -> URL? {
        return audioFileURL
    }
    
    private func togglePlayback() {
        if audioPlayer == nil {
            loadAndPlay()
        } else if isPlaying {
            pausePlayback()
        } else {
            resumePlayback()
        }
    }
    
    private func loadAndPlay() {
        isLoading = true
        loadError = false
        
        Task {
            do {
                // Check for preloaded media first
                let audioData: Data
                if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
                    print("📦 Using preloaded audio for ID: \(media.id)")
                    audioData = cachedData
                } else {
                    audioData = try await apiService.downloadMedia(mediaId: media.id)
                    // Update preloader cache
                    MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: audioData)
                }
                
                // Save to temp file for AVAudioPlayer
                let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("audio_\(media.id).m4a")
                try audioData.write(to: tempURL)
                
                await MainActor.run {
                    do {
                        // Configure audio session
                        try AVAudioSession.sharedInstance().setCategory(.playback, mode: .default)
                        try AVAudioSession.sharedInstance().setActive(true)
                        
                        let player = try AVAudioPlayer(contentsOf: tempURL)
                        player.prepareToPlay()
                        self.audioPlayer = player
                        self.audioFileURL = tempURL
                        self.duration = player.duration
                        self.isLoading = false
                        
                        // Start playback
                        player.play()
                        self.isPlaying = true
                        startProgressTimer()
                    } catch {
                        print("Failed to initialize audio player: \(error)")
                        self.isLoading = false
                        self.loadError = true
                    }
                }
            } catch {
                await MainActor.run {
                    print("Failed to load audio: \(error)")
                    self.isLoading = false
                    self.loadError = true
                }
            }
        }
    }
    
    private func pausePlayback() {
        audioPlayer?.pause()
        isPlaying = false
        stopProgressTimer()
    }
    
    private func resumePlayback() {
        audioPlayer?.play()
        isPlaying = true
        startProgressTimer()
    }
    
    private func stopPlayback() {
        audioPlayer?.stop()
        audioPlayer = nil
        isPlaying = false
        stopProgressTimer()
        playbackProgress = 0
        currentTime = 0
    }
    
    private func seek(to progress: Double) {
        guard let player = audioPlayer else { return }
        let newTime = progress * player.duration
        player.currentTime = newTime
        currentTime = newTime
        playbackProgress = progress
    }
    
    private func startProgressTimer() {
        progressTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { _ in
            guard let player = audioPlayer else { return }
            
            currentTime = player.currentTime
            playbackProgress = player.duration > 0 ? player.currentTime / player.duration : 0
            
            // Check if playback finished
            if !player.isPlaying && player.currentTime >= player.duration - 0.1 {
                isPlaying = false
                playbackProgress = 0
                currentTime = 0
                player.currentTime = 0
                stopProgressTimer()
            }
        }
    }
    
    private func stopProgressTimer() {
        progressTimer?.invalidate()
        progressTimer = nil
    }
    
    private func formatTime(_ time: TimeInterval) -> String {
        let minutes = Int(time) / 60
        let seconds = Int(time) % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

// MARK: - Waveform Visualization
struct WaveformView: View {
    let isFromCurrentUser: Bool
    let opacity: Double
    
    // Pre-generated waveform pattern (simulated)
    private let barCount = 30
    
    var body: some View {
        HStack(alignment: .bottom, spacing: 2) {
            ForEach(0..<barCount, id: \.self) { index in
                RoundedRectangle(cornerRadius: 1)
                    .fill(isFromCurrentUser ? Color.white.opacity(opacity) : Color.blue.opacity(opacity))
                    .frame(width: 3, height: waveformHeight(for: index))
            }
        }
    }
    
    private func waveformHeight(for index: Int) -> CGFloat {
        // Create a pseudo-random but consistent waveform pattern
        let seed = Double(index)
        let height = 8 + 16 * abs(sin(seed * 0.5) * cos(seed * 0.3))
        return CGFloat(height)
    }
}

// MARK: - Message Detail Overlay
struct MessageDetailOverlay: View {
    @EnvironmentObject var apiService: APIService
    @EnvironmentObject var themeSettings: ThemeSettings
    let message: Message
    let isFromCurrentUser: Bool
    @Binding var isPresented: Bool
    @State private var scale: CGFloat = 0.8
    @State private var opacity: Double = 0
    @State private var showCopiedFeedback = false
    
    // QuickLook states
    @State private var quickLookURL: IdentifiableURL?
    
    // Transcription states (for audio/video messages)
    @State private var showTranscription = false
    @State private var transcriptionText: String = ""
    @State private var isTranscribing = false
    @State private var transcriptionError: String?
    
    // Check if this is an audio message
    private var isAudioMessage: Bool {
        guard let media = message.mediaAsset else { return false }
        return message.contentType == 4 || media.isAudio
    }
    
    // Check if this is a video message
    private var isVideoMessage: Bool {
        guard let media = message.mediaAsset else { return false }
        return media.isVideo
    }
    
    // Check if this message can be transcribed (audio or video)
    private var canTranscribe: Bool {
        return isAudioMessage || isVideoMessage
    }
    
    var body: some View {
        GeometryReader { geometry in
            ZStack {
                // Blurred background
                Color.black.opacity(0.4)
                    .background(.ultraThinMaterial)
                    .ignoresSafeArea()
                    .onTapGesture {
                        dismissWithAnimation()
                    }
                
                // Message detail card
                ScrollView {
                    VStack(spacing: 0) {
                    // Action buttons
                    HStack(spacing: 16) {
                        // Copy button (for text messages)
                        if let text = message.text, !text.isEmpty {
                            ActionButton(
                                icon: "doc.on.doc",
                                label: "Copy",
                                color: .blue
                            ) {
                                UIPasteboard.general.string = text.htmlDecoded
                                showCopiedFeedback = true
                                let impactFeedback = UIImpactFeedbackGenerator(style: .light)
                                impactFeedback.impactOccurred()
                                DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                                    showCopiedFeedback = false
                                }
                            }
                        }
                        
                        // Transcribe button (for audio/video messages)
                        if canTranscribe {
                            ActionButton(
                                icon: "text.bubble",
                                label: "Transcribe",
                                color: .purple
                            ) {
                                transcribeMedia()
                            }
                        }
                        
                        // Share button
                        ActionButton(
                            icon: "square.and.arrow.up",
                            label: "Share",
                            color: .green
                        ) {
                            shareMessage()
                        }
                    }
                    .padding(.bottom, 16)
                    .onTapGesture { } // Prevent tap from propagating to dismiss
                    
                    // Copied feedback
                    if showCopiedFeedback {
                        Text("Copied to clipboard!")
                            .font(.caption)
                            .fontWeight(.medium)
                            .foregroundColor(.white)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Capsule().fill(Color.black.opacity(0.7)))
                            .transition(.opacity.combined(with: .scale))
                            .padding(.bottom, 8)
                    }
                    
                    // Enlarged message bubble with selectable text
                    VStack(alignment: .center, spacing: 4) {
                        VStack(alignment: .leading, spacing: 8) {
                            if let media = message.mediaAsset {
                                if isAudioMessage {
                                    AudioPlayerView(media: media, isFromCurrentUser: isFromCurrentUser)
                                } else {
                                    // Use enlarged media preview for images/videos - tap to open in QuickLook
                                    EnlargedMediaPreview(
                                        media: media,
                                        maxWidth: geometry.size.width - 56,
                                        maxHeight: geometry.size.height * 0.65
                                    )
                                    .onTapGesture {
                                        openInQuickLook(media: media)
                                    }
                                }
                            } else if isFromCurrentUser && (message.text == nil || message.text?.isEmpty == true) {
                                MediaPlaceholder()
                            }
                            
                            if let text = message.text, !text.isEmpty {
                                SelectableText(text: text.htmlDecoded, textColor: isFromCurrentUser ? .white : .primary)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(isFromCurrentUser ? themeSettings.senderBubbleColor : themeSettings.recipientBubbleColor)
                        )
                        .fixedSize(horizontal: message.mediaAsset == nil || isAudioMessage, vertical: true)
                    }
                    .frame(maxWidth: message.mediaAsset != nil && !isAudioMessage ? geometry.size.width - 32 : 320, alignment: .center)
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.bottom, 20)
                    .onTapGesture { } // Prevent tap from propagating to dismiss
                    
                    // Transcription Card (for audio/video messages)
                    if canTranscribe && showTranscription {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Image(systemName: "text.bubble.fill")
                                    .foregroundColor(.purple)
                                Text("Transcription")
                                    .font(.headline)
                                Spacer()
                                
                                if !transcriptionText.isEmpty {
                                    Button(action: {
                                        UIPasteboard.general.string = transcriptionText
                                        showCopiedFeedback = true
                                        let impactFeedback = UIImpactFeedbackGenerator(style: .light)
                                        impactFeedback.impactOccurred()
                                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                                            showCopiedFeedback = false
                                        }
                                    }) {
                                        Image(systemName: "doc.on.doc")
                                            .foregroundColor(.blue)
                                    }
                                }
                            }
                            
                            if isTranscribing {
                                HStack {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                    Text("Transcribing audio...")
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                .frame(maxWidth: .infinity, alignment: .center)
                                .padding(.vertical, 20)
                            } else if let error = transcriptionError {
                                HStack(spacing: 8) {
                                    Image(systemName: "exclamationmark.triangle.fill")
                                        .foregroundColor(.orange)
                                    Text(error)
                                        .font(.subheadline)
                                        .foregroundColor(.secondary)
                                }
                                .padding(.vertical, 8)
                            } else if !transcriptionText.isEmpty {
                                Text(transcriptionText)
                                    .font(.body)
                                    .foregroundColor(.primary)
                                    .textSelection(.enabled)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                        .padding(16)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(Color(.systemBackground))
                        )
                        .shadow(color: Color.black.opacity(0.15), radius: 10, x: 0, y: 5)
                        .padding(.bottom, 16)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                        .onTapGesture { } // Prevent tap from propagating to dismiss
                    }
                    
                    // Message info card
                    VStack(alignment: .leading, spacing: 12) {
                        // Time sent
                        HStack(spacing: 12) {
                            Image(systemName: "clock")
                                .foregroundColor(.yellow)
                                .frame(width: 24)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Sent")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(formatFullDateTime(message.date))
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                            }
                            Spacer()
                        }
                        
                        Divider()
                        
                        // Read time (if available)
                        if let readTimestamp = message.readTimestamp, readTimestamp > 0 {
                            HStack(spacing: 12) {
                                Image(systemName: "eye")
                                    .foregroundColor(.green)
                                    .frame(width: 24)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Read")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Text(formatFullDateTime(Date(timeIntervalSince1970: TimeInterval(readTimestamp) / 1000.0)))
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                }
                                Spacer()
                            }
                            
                            Divider()
                        }
                        
                        // Sender
                        HStack(spacing: 12) {
                            Image(systemName: "person")
                                .foregroundColor(.blue)
                                .frame(width: 24)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("From")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                                Text(message.sender?.displayName ?? message.senderId)
                                    .font(.subheadline)
                                    .fontWeight(.medium)
                            }
                            Spacer()
                        }
                        
                        // Media info (if has media)
                        if let media = message.mediaAsset {
                            Divider()
                            
                            HStack(spacing: 12) {
                                Image(systemName: isAudioMessage ? "waveform" : media.isVideo ? "video" : media.isImage ? "photo" : "doc")
                                    .foregroundColor(.purple)
                                    .frame(width: 24)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(isAudioMessage ? "Audio" : "Media")
                                        .font(.caption)
                                        .foregroundColor(.secondary)
                                    Text(isAudioMessage ? "Voice Message • \(formatFileSize(media.fileSize))" : "\(media.fileType.capitalized) • \(formatFileSize(media.fileSize))")
                                        .font(.subheadline)
                                        .fontWeight(.medium)
                                }
                                Spacer()
                            }
                        }
                    }
                    .padding(16)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(Color(.systemBackground))
                    )
                    .shadow(color: Color.black.opacity(0.15), radius: 10, x: 0, y: 5)
                    .onTapGesture { } // Prevent tap from propagating to dismiss
                }
                .padding(.horizontal, 24)
                .padding(.top, 16)
                .padding(.bottom, 40)
                .frame(minHeight: geometry.size.height)
                .contentShape(Rectangle())
                .onTapGesture {
                    dismissWithAnimation()
                }
            }
            .scaleEffect(scale)
            .opacity(opacity)
        }
        }
        .onAppear {
            withAnimation(.spring(response: 0.15, dampingFraction: 0.7)) {
                scale = 1.0
                opacity = 1.0
            }
        }
        .sheet(item: $quickLookURL) { url in
            QuickLookSheet(url: url.url)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
    }
    
    private func openInQuickLook(media: MediaAsset) {
        Task {
            do {
                // Check for preloaded media first
                let mediaData: Data
                if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
                    print("📦 Using preloaded media for QuickLook detail ID: \(media.id)")
                    mediaData = cachedData
                } else {
                    mediaData = try await apiService.downloadMedia(mediaId: media.id)
                    // Update preloader cache
                    MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: mediaData)
                }
                
                // Determine proper file extension
                let fileExtension: String
                if media.isImage {
                    fileExtension = media.mimeType.contains("png") ? "png" : "jpg"
                } else if media.isVideo {
                    fileExtension = "mp4"
                } else {
                    fileExtension = media.fileType
                }
                
                let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("preview_detail_\(media.id).\(fileExtension)")
                try mediaData.write(to: tempURL)
                
                await MainActor.run {
                    quickLookURL = IdentifiableURL(url: tempURL)
                }
            } catch {
                print("Failed to open media in QuickLook: \(error)")
            }
        }
    }
    
    private func dismissWithAnimation() {
        withAnimation(.easeOut(duration: 0.1)) {
            scale = 0.8
            opacity = 0
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
            isPresented = false
        }
    }
    
    private func formatFullDateTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEEE, d MMMM yyyy 'at' h:mm:ss a"
        return formatter.string(from: date)
    }
    
    private func formatFileSize(_ bytes: Int) -> String {
        let kb = Double(bytes) / 1024
        if kb < 1024 {
            return String(format: "%.1f KB", kb)
        }
        let mb = kb / 1024
        return String(format: "%.1f MB", mb)
    }
    
    private func shareMessage() {
        var itemsToShare: [Any] = []
        
        if let text = message.text, !text.isEmpty {
            itemsToShare.append(text.htmlDecoded)
        }
        
        // For messages with media (audio, image, video), share the media file
        if let media = message.mediaAsset {
            Task {
                do {
                    let mediaData = try await apiService.downloadMedia(mediaId: media.id)
                    
                    // Determine file extension based on media type
                    let fileExtension: String
                    if isAudioMessage {
                        fileExtension = "m4a"
                    } else if media.isVideo {
                        fileExtension = "mp4"
                    } else if media.isImage {
                        fileExtension = media.mimeType.contains("png") ? "png" : "jpg"
                    } else {
                        fileExtension = media.fileType
                    }
                    
                    let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("share_media_\(media.id).\(fileExtension)")
                    try mediaData.write(to: tempURL)
                    
                    await MainActor.run {
                        // Include both the media file and any text
                        var shareItems: [Any] = [tempURL]
                        if let text = message.text, !text.isEmpty {
                            shareItems.append(text.htmlDecoded)
                        }
                        presentShareSheet(items: shareItems)
                    }
                } catch {
                    print("Failed to share media: \(error)")
                    // If media download fails but we have text, share just the text
                    await MainActor.run {
                        if !itemsToShare.isEmpty {
                            presentShareSheet(items: itemsToShare)
                        }
                    }
                }
            }
            return
        }
        
        if !itemsToShare.isEmpty {
            presentShareSheet(items: itemsToShare)
        }
    }
    
    private func presentShareSheet(items: [Any]) {
        let activityController = UIActivityViewController(
            activityItems: items,
            applicationActivities: nil
        )
        
        if let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
           let rootViewController = windowScene.windows.first?.rootViewController {
            var topController = rootViewController
            while let presentedController = topController.presentedViewController {
                topController = presentedController
            }
            topController.present(activityController, animated: true)
        }
    }
    
    // MARK: - Transcription Functions
    
    private func transcribeMedia() {
        withAnimation {
            showTranscription = true
        }
        
        guard let media = message.mediaAsset else { return }
        
        isTranscribing = true
        transcriptionError = nil
        transcriptionText = ""
        
        // Request speech recognition authorization
        SFSpeechRecognizer.requestAuthorization { authStatus in
            DispatchQueue.main.async {
                switch authStatus {
                case .authorized:
                    performTranscription(for: media)
                case .denied:
                    isTranscribing = false
                    transcriptionError = "Speech recognition permission denied. Please enable it in Settings."
                case .restricted:
                    isTranscribing = false
                    transcriptionError = "Speech recognition is restricted on this device."
                case .notDetermined:
                    isTranscribing = false
                    transcriptionError = "Speech recognition permission not determined."
                @unknown default:
                    isTranscribing = false
                    transcriptionError = "Unknown authorization status."
                }
            }
        }
    }
    
    private func performTranscription(for media: MediaAsset) {
        Task {
            do {
                let mediaData = try await apiService.downloadMedia(mediaId: media.id)
                
                // Determine file extension based on media type
                let fileExtension = isVideoMessage ? "mp4" : "m4a"
                let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("transcribe_\(media.id).\(fileExtension)")
                try mediaData.write(to: tempURL)
                
                if isVideoMessage {
                    // Extract audio from video before transcribing
                    await MainActor.run {
                        extractAudioAndTranscribe(from: tempURL)
                    }
                } else {
                    await MainActor.run {
                        transcribeFile(at: tempURL)
                    }
                }
            } catch {
                await MainActor.run {
                    isTranscribing = false
                    transcriptionError = "Failed to download media: \(error.localizedDescription)"
                }
            }
        }
    }
    
    private func extractAudioAndTranscribe(from videoURL: URL) {
        let asset = AVAsset(url: videoURL)
        
        // Check if video has audio track
        Task {
            do {
                let audioTracks = try await asset.loadTracks(withMediaType: .audio)
                
                guard !audioTracks.isEmpty else {
                    await MainActor.run {
                        isTranscribing = false
                        transcriptionError = "This video has no audio track."
                    }
                    return
                }
                
                // Create audio export URL
                let audioURL = FileManager.default.temporaryDirectory.appendingPathComponent("extracted_audio_\(UUID().uuidString).m4a")
                
                // Remove existing file if any
                try? FileManager.default.removeItem(at: audioURL)
                
                // Create export session
                guard let exportSession = AVAssetExportSession(asset: asset, presetName: AVAssetExportPresetAppleM4A) else {
                    await MainActor.run {
                        isTranscribing = false
                        transcriptionError = "Failed to create audio export session."
                    }
                    return
                }
                
                exportSession.outputURL = audioURL
                exportSession.outputFileType = .m4a
                
                await exportSession.export()
                
                switch exportSession.status {
                case .completed:
                    await MainActor.run {
                        transcribeFile(at: audioURL)
                    }
                case .failed:
                    await MainActor.run {
                        isTranscribing = false
                        transcriptionError = "Failed to extract audio: \(exportSession.error?.localizedDescription ?? "Unknown error")"
                    }
                case .cancelled:
                    await MainActor.run {
                        isTranscribing = false
                        transcriptionError = "Audio extraction was cancelled."
                    }
                default:
                    await MainActor.run {
                        isTranscribing = false
                        transcriptionError = "Unexpected export status."
                    }
                }
            } catch {
                await MainActor.run {
                    isTranscribing = false
                    transcriptionError = "Failed to load audio tracks: \(error.localizedDescription)"
                }
            }
        }
    }
    
    private func transcribeFile(at url: URL) {
        guard let recognizer = SFSpeechRecognizer() else {
            isTranscribing = false
            transcriptionError = "Speech recognition not available for your language."
            return
        }
        
        guard recognizer.isAvailable else {
            isTranscribing = false
            transcriptionError = "Speech recognition is currently unavailable."
            return
        }
        
        let request = SFSpeechURLRecognitionRequest(url: url)
        request.shouldReportPartialResults = false
        
        recognizer.recognitionTask(with: request) { result, error in
            DispatchQueue.main.async {
                isTranscribing = false
                
                if let error = error {
                    transcriptionError = "Transcription failed: \(error.localizedDescription)"
                    return
                }
                
                guard let result = result else {
                    transcriptionError = "No transcription result available."
                    return
                }
                
                if result.isFinal {
                    transcriptionText = result.bestTranscription.formattedString
                    if transcriptionText.isEmpty {
                        transcriptionError = "No speech detected in the audio."
                    }
                }
            }
        }
    }
}

// MARK: - Action Button Component
struct ActionButton: View {
    let icon: String
    let label: String
    let color: Color
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            VStack(spacing: 8) {
                ZStack {
                    Circle()
                        .fill(color.opacity(0.15))
                        .frame(width: 56, height: 56)
                    
                    Image(systemName: icon)
                        .font(.system(size: 22, weight: .medium))
                        .foregroundColor(color)
                }
                
                Text(label)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundColor(.primary)
            }
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Selectable Text Component
struct SelectableText: UIViewRepresentable {
    let text: String
    let textColor: Color
    
    func makeUIView(context: Context) -> UITextView {
        let textView = UITextView()
        textView.isEditable = false
        textView.isSelectable = true
        textView.isScrollEnabled = false
        textView.backgroundColor = .clear
        textView.textContainerInset = .zero
        textView.textContainer.lineFragmentPadding = 0
        textView.font = UIFont.preferredFont(forTextStyle: .body)
        textView.dataDetectorTypes = [.link, .phoneNumber]
        textView.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        textView.setContentHuggingPriority(.required, for: .vertical)
        textView.setContentHuggingPriority(.defaultLow, for: .horizontal)
        return textView
    }
    
    func updateUIView(_ uiView: UITextView, context: Context) {
        uiView.text = text
        uiView.textColor = UIColor(textColor)
        // Force layout update
        uiView.invalidateIntrinsicContentSize()
    }
}

// MARK: - QuickLook Sheet (Popup Style)
struct QuickLookSheet: UIViewControllerRepresentable {
    let url: URL
    @Environment(\.dismiss) var dismiss
    
    func makeUIViewController(context: Context) -> UINavigationController {
        let controller = QLPreviewController()
        controller.dataSource = context.coordinator
        controller.delegate = context.coordinator
        
        let navController = UINavigationController(rootViewController: controller)
        navController.modalPresentationStyle = .pageSheet
        
        // Add a close button
        controller.navigationItem.rightBarButtonItem = UIBarButtonItem(
            barButtonSystemItem: .close,
            target: context.coordinator,
            action: #selector(Coordinator.dismissSheet)
        )
        
        return navController
    }
    
    func updateUIViewController(_ uiViewController: UINavigationController, context: Context) {
        if let qlController = uiViewController.viewControllers.first as? QLPreviewController {
            qlController.reloadData()
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(url: url, dismiss: dismiss)
    }
    
    class Coordinator: NSObject, QLPreviewControllerDataSource, QLPreviewControllerDelegate {
        let url: URL
        let dismiss: DismissAction
        
        init(url: URL, dismiss: DismissAction) {
            self.url = url
            self.dismiss = dismiss
        }
        
        func numberOfPreviewItems(in controller: QLPreviewController) -> Int {
            return 1
        }
        
        func previewController(_ controller: QLPreviewController, previewItemAt index: Int) -> QLPreviewItem {
            return url as QLPreviewItem
        }
        
        @objc func dismissSheet() {
            dismiss()
        }
    }
}

#Preview {
    NavigationView {
        ChatView(conversation: Conversation(
            id: "test",
            groupName: "Test Conversation",
            isGroupChat: false,
            participantCount: 2,
            lastMessageAt: ISO8601DateFormatter().string(from: Date()),
            createdAt: ISO8601DateFormatter().string(from: Date()),
            updatedAt: ISO8601DateFormatter().string(from: Date()),
            lastMessagePreview: nil,
            avatar: nil
        ))
    }
    .environmentObject(APIService())
    .environmentObject(ThemeSettings())
}

// MARK: - Chat Search Results Overlay
struct ChatSearchResultsOverlay: View {
    let searchText: String
    let isSearching: Bool
    let searchResults: [SearchResultMessage]
    let onSelectResult: (SearchResultMessage) -> Void
    let onDismiss: () -> Void
    
    var body: some View {
        VStack(spacing: 0) {
            // Results list
            if isSearching {
                VStack {
                    Spacer()
                    ProgressView("Searching...")
                    Spacer()
                }
                .frame(maxWidth: .infinity)
                .background(Color(.systemBackground).opacity(0.95))
            } else if searchResults.isEmpty {
                VStack {
                    Spacer()
                    VStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .font(.title)
                            .foregroundColor(.secondary)
                        Text("No messages found")
                            .foregroundColor(.secondary)
                        Text("Try a different search term")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    Spacer()
                }
                .frame(maxWidth: .infinity)
                .background(Color(.systemBackground).opacity(0.95))
            } else {
                List {
                    Section(header: Text("\(searchResults.count) results for \"\(searchText)\"")) {
                        ForEach(searchResults) { result in
                            Button {
                                onSelectResult(result)
                            } label: {
                                ChatSearchResultRow(result: result, searchQuery: searchText)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
        .background(Color(.systemBackground).opacity(0.98))
    }
}

// MARK: - Chat Search Result Row
struct ChatSearchResultRow: View {
    let result: SearchResultMessage
    let searchQuery: String
    
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                if let sender = result.sender {
                    Text(sender.displayName ?? sender.username)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundColor(.primary)
                }
                Spacer()
                Text(formatDate(result.date))
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            
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
        let formatter = DateFormatter()
        
        if calendar.isDateInToday(date) {
            formatter.timeStyle = .short
            return formatter.string(from: date)
        } else if calendar.isDateInYesterday(date) {
            formatter.timeStyle = .short
            return "Yesterday, \(formatter.string(from: date))"
        } else if calendar.isDate(date, equalTo: Date(), toGranularity: .year) {
            formatter.dateFormat = "MMM d, h:mm a"
            return formatter.string(from: date)
        } else {
            formatter.dateFormat = "MMM d, yyyy"
            return formatter.string(from: date)
        }
    }
}
