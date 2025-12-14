//
//  BitmojiAvatarView.swift
//  SnapStash
//
//  Created on 11/12/2025.
//

import SwiftUI

// MARK: - Unified Avatar View
/// A unified avatar view that displays either a Bitmoji, contact photo, or initials
/// based on the current avatar source setting and available data.
struct UnifiedAvatarView: View {
    let conversation: Conversation?
    let user: User?
    let matchedContact: MatchedContact?
    let displayName: String
    let size: CGFloat
    let isGroupChat: Bool
    
    @ObservedObject private var avatarSettings = AvatarSettings.shared
    
    init(
        conversation: Conversation? = nil,
        user: User? = nil,
        matchedContact: MatchedContact? = nil,
        displayName: String,
        size: CGFloat = 50,
        isGroupChat: Bool = false
    ) {
        self.conversation = conversation
        self.user = user
        self.matchedContact = matchedContact
        self.displayName = displayName
        self.size = size
        self.isGroupChat = isGroupChat
    }
    
    private var initials: String {
        let components = displayName.components(separatedBy: " ")
        if components.count >= 2 {
            let first = components[0].prefix(1)
            let last = components[1].prefix(1)
            return "\(first)\(last)".uppercased()
        } else {
            return String(displayName.prefix(2)).uppercased()
        }
    }
    
    private var avatarColor: Color {
        isGroupChat ? .blue : .green
    }
    
    var body: some View {
        switch avatarSettings.avatarSource {
        case .bitmoji:
            bitmojiAvatar
        case .contacts:
            contactAvatar
        case .initials:
            initialsAvatar
        }
    }
    
    @ViewBuilder
    private var bitmojiAvatar: some View {
        if isGroupChat {
            // Group chat with stacked bitmojis
            groupBitmojiAvatar
        } else {
            // Single user bitmoji
            singleBitmojiAvatar
        }
    }
    
    @ViewBuilder
    private var singleBitmojiAvatar: some View {
        let bitmojiUrl = conversation?.avatar?.bitmojiUrl ?? user?.bitmojiUrl
        
        if let urlString = bitmojiUrl, let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .empty:
                    initialsAvatar
                        .overlay(
                            ProgressView()
                                .scaleEffect(0.5)
                        )
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                        .frame(width: size, height: size)
                        .clipShape(Circle())
                        .background(
                            Circle()
                                .fill(Color.yellow)
                                .frame(width: size, height: size)
                        )
                case .failure:
                    initialsAvatar
                @unknown default:
                    initialsAvatar
                }
            }
        } else {
            initialsAvatar
        }
    }
    
    @ViewBuilder
    private var groupBitmojiAvatar: some View {
        let participants = conversation?.avatar?.participants ?? []
        
        if participants.isEmpty {
            initialsAvatar
        } else {
            GroupBitmojiStack(participants: participants, size: size, fallbackInitials: initials)
        }
    }
    
    @ViewBuilder
    private var contactAvatar: some View {
        ContactPhotoView(
            contact: isGroupChat ? nil : matchedContact,
            fallbackInitials: initials,
            fallbackColor: avatarColor,
            size: size
        )
    }
    
    @ViewBuilder
    private var initialsAvatar: some View {
        ZStack {
            Circle()
                .fill(avatarColor)
                .frame(width: size, height: size)
            Text(initials)
                .font(.system(size: size * 0.32, weight: .semibold))
                .foregroundColor(.white)
        }
    }
}

// MARK: - Group Bitmoji Stack
/// Displays stacked bitmoji avatars for group chats (up to 3 participants)
struct GroupBitmojiStack: View {
    let participants: [UserAvatar]
    let size: CGFloat
    let fallbackInitials: String
    
    private var stackedSize: CGFloat {
        size * 0.6
    }
    
    var body: some View {
        let displayParticipants = Array(participants.prefix(3))
        let count = displayParticipants.count
        
        ZStack {
            if count == 1 {
                // Single participant - centered
                SingleParticipantAvatar(
                    participant: displayParticipants[0],
                    size: stackedSize
                )
            } else if count == 2 {
                // Two participants - top-left and bottom-right
                SingleParticipantAvatar(
                    participant: displayParticipants[0],
                    size: stackedSize
                )
                .offset(x: -size * 0.15, y: -size * 0.15)
                .zIndex(2)
                
                SingleParticipantAvatar(
                    participant: displayParticipants[1],
                    size: stackedSize
                )
                .offset(x: size * 0.15, y: size * 0.15)
                .zIndex(1)
            } else {
                // Three participants - top-left, top-right, bottom-center
                SingleParticipantAvatar(
                    participant: displayParticipants[0],
                    size: stackedSize * 0.85
                )
                .offset(x: -size * 0.18, y: -size * 0.12)
                .zIndex(3)
                
                SingleParticipantAvatar(
                    participant: displayParticipants[1],
                    size: stackedSize * 0.85
                )
                .offset(x: size * 0.18, y: -size * 0.12)
                .zIndex(2)
                
                SingleParticipantAvatar(
                    participant: displayParticipants[2],
                    size: stackedSize * 0.85
                )
                .offset(x: 0, y: size * 0.18)
                .zIndex(1)
            }
        }
        .frame(width: size, height: size)
    }
}

// MARK: - Single Participant Avatar (simplified)
struct SingleParticipantAvatar: View {
    let participant: UserAvatar
    let size: CGFloat
    
    @State private var imageError = false
    
    private var initials: String {
        guard let name = participant.displayName else { return "?" }
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
        Group {
            if let urlString = participant.bitmojiUrl, let url = URL(string: urlString), !imageError {
                AsyncImage(url: url) { phase in
                    switch phase {
                    case .empty:
                        initialsView
                    case .success(let image):
                        image
                            .resizable()
                            .scaledToFill()
                            .frame(width: size, height: size)
                            .clipShape(Circle())
                            .background(
                                Circle()
                                    .fill(Color.yellow)
                            )
                            .overlay(
                                Circle()
                                    .stroke(Color(UIColor.systemBackground), lineWidth: 2)
                            )
                    case .failure:
                        initialsView
                            .onAppear { imageError = true }
                    @unknown default:
                        initialsView
                    }
                }
            } else {
                initialsView
            }
        }
    }
    
    private var initialsView: some View {
        ZStack {
            Circle()
                .fill(Color.yellow)
                .frame(width: size, height: size)
            Text(initials)
                .font(.system(size: size * 0.35, weight: .semibold))
                .foregroundColor(.black)
        }
        .overlay(
            Circle()
                .stroke(Color(UIColor.systemBackground), lineWidth: 2)
        )
    }
}

// MARK: - Simple Bitmoji Avatar (for message bubbles)
/// A simpler bitmoji avatar view for use in message bubbles
struct SimpleBitmojiAvatar: View {
    let user: User?
    let displayName: String
    let size: CGFloat
    
    @ObservedObject private var avatarSettings = AvatarSettings.shared
    
    private var initials: String {
        let name = user?.displayName ?? displayName
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
        if avatarSettings.avatarSource == .bitmoji,
           let urlString = user?.bitmojiUrl,
           let url = URL(string: urlString) {
            AsyncImage(url: url) { phase in
                switch phase {
                case .empty:
                    initialsView
                case .success(let image):
                    image
                        .resizable()
                        .scaledToFill()
                        .frame(width: size, height: size)
                        .clipShape(Circle())
                        .background(
                            Circle()
                                .fill(Color.yellow)
                        )
                case .failure:
                    initialsView
                @unknown default:
                    initialsView
                }
            }
        } else {
            initialsView
        }
    }
    
    private var initialsView: some View {
        ZStack {
            Circle()
                .fill(Color.green)
                .frame(width: size, height: size)
            Text(initials)
                .font(.system(size: size * 0.35, weight: .semibold))
                .foregroundColor(.white)
        }
    }
}
