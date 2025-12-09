//
//  Models.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import Foundation

// MARK: - User
struct User: Codable, Identifiable {
    let id: String
    let username: String
    let displayName: String
    let createdAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case username
        case displayName = "display_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

// MARK: - LastMessagePreview
struct LastMessagePreview: Codable {
    let text: String?
    let hasMedia: Bool
    let mediaType: String?
    let senderName: String?
    let timestamp: Int64?

    enum CodingKeys: String, CodingKey {
        case text
        case hasMedia = "has_media"
        case mediaType = "media_type"
        case senderName = "sender_name"
        case timestamp
    }
}

// MARK: - Conversation
struct Conversation: Codable, Identifiable, Hashable {
    let id: String
    let groupName: String?
    let isGroupChat: Bool
    let participantCount: Int?
    let lastMessageAt: String?
    let createdAt: String
    let updatedAt: String
    let lastMessagePreview: LastMessagePreview?

    enum CodingKeys: String, CodingKey {
        case id
        case groupName = "group_name"
        case isGroupChat = "is_group_chat"
        case participantCount = "participant_count"
        case lastMessageAt = "last_message_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastMessagePreview = "last_message_preview"
    }
    
    // Hashable conformance - use id for equality
    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }
    
    static func == (lhs: Conversation, rhs: Conversation) -> Bool {
        lhs.id == rhs.id
    }

    var displayName: String {
        guard let groupName = groupName, !groupName.isEmpty else {
            return "Unknown"
        }
        return groupName
    }
}

// MARK: - MediaAsset
struct MediaAsset: Codable, Identifiable {
    let id: Int
    let originalFilename: String?
    let filePath: String
    let fileHash: String
    let fileSize: Int
    let fileType: String
    let mimeType: String
    let cacheKey: String
    let cacheId: String
    let category: String
    let timestampSource: String?
    let mappingMethod: String?
    let fileTimestamp: String?
    let senderId: String?
    let createdAt: String
    let updatedAt: String?
    let sender: User?

    enum CodingKeys: String, CodingKey {
        case id
        case originalFilename = "original_filename"
        case filePath = "file_path"
        case fileHash = "file_hash"
        case fileSize = "file_size"
        case fileType = "file_type"
        case mimeType = "mime_type"
        case cacheKey = "cache_key"
        case cacheId = "cache_id"
        case category
        case timestampSource = "timestamp_source"
        case mappingMethod = "mapping_method"
        case fileTimestamp = "file_timestamp"
        case senderId = "sender_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case sender
    }

    var isImage: Bool {
        fileType.lowercased() == "image" || mimeType.lowercased().hasPrefix("image/")
    }

    var isVideo: Bool {
        let fileTypeIsVideo = fileType.lowercased() == "video"
        let mimeTypeIsVideo = mimeType.lowercased().hasPrefix("video/")
        let mimeTypeIsAudio = mimeType.lowercased().hasPrefix("audio/")
        let fileTypeIsAudio = fileType.lowercased() == "audio"
        
        // It's video only if: (fileType is video OR mimeType is video) AND NOT audio
        return (fileTypeIsVideo || mimeTypeIsVideo) && !mimeTypeIsAudio && !fileTypeIsAudio
    }

    var isAudio: Bool {
        fileType.lowercased() == "audio" || mimeType.lowercased().hasPrefix("audio/")
    }
}

// MARK: - Message
struct Message: Codable, Identifiable {
    let id: Int
    let text: String?
    let contentType: Int
    let cacheId: String?
    let creationTimestamp: Int64
    let readTimestamp: Int64?
    let parsingSuccessful: Bool
    let senderId: String
    let conversationId: String
    let serverMessageId: String?
    let clientMessageId: String?
    let mediaAssetId: Int?
    let createdAt: String
    let updatedAt: String
    let sender: User?
    let mediaAsset: MediaAsset?

    enum CodingKeys: String, CodingKey {
        case id
        case text
        case contentType = "content_type"
        case cacheId = "cache_id"
        case creationTimestamp = "creation_timestamp"
        case readTimestamp = "read_timestamp"
        case parsingSuccessful = "parsing_successful"
        case senderId = "sender_id"
        case conversationId = "conversation_id"
        case serverMessageId = "server_message_id"
        case clientMessageId = "client_message_id"
        case mediaAssetId = "media_asset_id"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case sender
        case mediaAsset = "media_asset"
    }

    var date: Date {
        Date(timeIntervalSince1970: TimeInterval(creationTimestamp) / 1000.0)
    }

    var hasMedia: Bool {
        mediaAsset != nil
    }

    /// Returns true if the message appears to be media content but no actual media data is available.
    /// This includes messages with a mediaAssetId but no mediaAsset, or messages with certain content types
    /// that indicate media was sent/received but the file is unavailable.
    var appearsToBeMedia: Bool {
        // Has a media asset ID but no actual media data
        if mediaAssetId != nil && mediaAsset == nil {
            return true
        }
        // Content type indicates media (non-text content types are typically > 0)
        // Common content types: 0 = text, 1+ = various media types
        if contentType > 0 && (text == nil || text?.isEmpty == true) && mediaAsset == nil {
            return true
        }
        return false
    }

    /// Returns true if the message has content that should be displayed in the chat.
    /// For received messages with missing media and no text, returns false to hide empty bubbles.
    func hasVisibleContent(isFromCurrentUser: Bool) -> Bool {
        // Has text content
        if let text = text, !text.isEmpty {
            return true
        }
        // Has actual media
        if mediaAsset != nil {
            return true
        }
        // For sent messages with no text and no media, show placeholder
        // (these are likely media messages where the media isn't available)
        if isFromCurrentUser {
            return true
        }
        // For received messages with missing media, hide the bubble
        return false
    }

    var displayText: String {
        if let text = text, !text.isEmpty {
            return text
        } else if hasMedia {
            return "[Media]"
        } else {
            return "[No content]"
        }
    }
}

// MARK: - Pagination
struct PaginationMeta: Codable {
    let total: Int
    let limit: Int
    let offset: Int
    let hasNext: Bool
    let hasPrev: Bool

    enum CodingKeys: String, CodingKey {
        case total
        case limit
        case offset
        case hasNext = "has_next"
        case hasPrev = "has_prev"
    }
}

// MARK: - API Responses
struct ConversationsResponse: Codable {
    let conversations: [Conversation]
    let pagination: PaginationMeta
}

struct MessagesResponse: Codable {
    let messages: [Message]
    let pagination: PaginationMeta
}

struct ConversationDetailResponse: Codable {
    let id: String
    let groupName: String?
    let isGroupChat: Bool
    let participantCount: Int?
    let lastMessageAt: String?
    let createdAt: String
    let updatedAt: String
    let recentMessages: [Message]?
    let statistics: MessageStatistics?

    enum CodingKeys: String, CodingKey {
        case id
        case groupName = "group_name"
        case isGroupChat = "is_group_chat"
        case participantCount = "participant_count"
        case lastMessageAt = "last_message_at"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case recentMessages = "recent_messages"
        case statistics
    }
}

struct MessageStatistics: Codable {
    let totalMessages: Int
    let textMessages: Int
    let mediaMessages: Int
    let messagesWithMedia: Int

    enum CodingKeys: String, CodingKey {
        case totalMessages = "total_messages"
        case textMessages = "text_messages"
        case mediaMessages = "media_messages"
        case messagesWithMedia = "messages_with_media"
    }
}

struct HealthResponse: Codable {
    let status: String
    let timestamp: String?
}

// MARK: - Search
struct SearchResultConversation: Codable {
    let id: String
    let groupName: String?
    let isGroupChat: Bool
    
    enum CodingKeys: String, CodingKey {
        case id
        case groupName = "group_name"
        case isGroupChat = "is_group_chat"
    }
    
    var displayName: String {
        guard let groupName = groupName, !groupName.isEmpty else {
            return "Unknown"
        }
        return groupName
    }
}

struct SearchResultSender: Codable {
    let id: String
    let username: String
    let displayName: String?
    
    enum CodingKeys: String, CodingKey {
        case id
        case username
        case displayName = "display_name"
    }
}

struct SearchResultMessage: Codable, Identifiable {
    let id: Int
    let text: String?
    let contentType: Int
    let creationTimestamp: Int64
    let readTimestamp: Int64?
    let senderId: String
    let conversationId: String
    let mediaAssetId: Int?
    let sender: SearchResultSender?
    let conversation: SearchResultConversation?
    
    enum CodingKeys: String, CodingKey {
        case id
        case text
        case contentType = "content_type"
        case creationTimestamp = "creation_timestamp"
        case readTimestamp = "read_timestamp"
        case senderId = "sender_id"
        case conversationId = "conversation_id"
        case mediaAssetId = "media_asset_id"
        case sender
        case conversation
    }
    
    var date: Date {
        Date(timeIntervalSince1970: TimeInterval(creationTimestamp) / 1000.0)
    }
}

struct SearchResponse: Codable {
    let query: String
    let results: [SearchResultMessage]
    let pagination: PaginationMeta
}

// MARK: - API Error
struct APIError: Error, LocalizedError {
    let statusCode: Int?
    let message: String

    var errorDescription: String? {
        if let statusCode = statusCode {
            return "API Error (\(statusCode)): \(message)"
        }
        return message
    }
}

// MARK: - String Extension for HTML Entity Decoding
extension String {
    /// Decodes HTML entities like &#128591; to their corresponding Unicode characters (emojis)
    var htmlDecoded: String {
        var result = self
        
        // Decode numeric HTML entities (e.g., &#128591; for 🙏)
        let pattern = "&#(\\d+);"
        if let regex = try? NSRegularExpression(pattern: pattern, options: []) {
            let range = NSRange(result.startIndex..., in: result)
            let matches = regex.matches(in: result, options: [], range: range).reversed()
            
            for match in matches {
                if let codeRange = Range(match.range(at: 1), in: result),
                   let code = Int(result[codeRange]),
                   let scalar = Unicode.Scalar(code) {
                    let char = String(Character(scalar))
                    if let fullRange = Range(match.range, in: result) {
                        result.replaceSubrange(fullRange, with: char)
                    }
                }
            }
        }
        
        // Decode hexadecimal HTML entities (e.g., &#x1F64F; for 🙏)
        let hexPattern = "&#[xX]([0-9a-fA-F]+);"
        if let hexRegex = try? NSRegularExpression(pattern: hexPattern, options: []) {
            let range = NSRange(result.startIndex..., in: result)
            let matches = hexRegex.matches(in: result, options: [], range: range).reversed()
            
            for match in matches {
                if let codeRange = Range(match.range(at: 1), in: result),
                   let code = Int(result[codeRange], radix: 16),
                   let scalar = Unicode.Scalar(code) {
                    let char = String(Character(scalar))
                    if let fullRange = Range(match.range, in: result) {
                        result.replaceSubrange(fullRange, with: char)
                    }
                }
            }
        }
        
        // Decode common named HTML entities
        let namedEntities: [String: String] = [
            "&amp;": "&",
            "&lt;": "<",
            "&gt;": ">",
            "&quot;": "\"",
            "&apos;": "'",
            "&nbsp;": " "
        ]
        
        for (entity, char) in namedEntities {
            result = result.replacingOccurrences(of: entity, with: char)
        }
        
        return result
    }
}
