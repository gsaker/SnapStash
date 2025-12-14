//
//  APIService.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import Foundation
import Combine

class APIService: ObservableObject {
    @Published var apiBaseURL: String {
        didSet {
            UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.set(apiBaseURL, forKey: "apiBaseURL")
        }
    }

    private let decoder: JSONDecoder

    init() {
        // Load saved API URL or use default
        let savedURL = UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.string(forKey: "apiBaseURL")
        let initialApiBaseURL = savedURL ?? "http://localhost:8067"
        self.apiBaseURL = initialApiBaseURL
        UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.set(initialApiBaseURL, forKey: "apiBaseURL")

        // Configure JSON decoder
        decoder = JSONDecoder()

        // Configure date decoding strategy to handle ISO8601 with fractional seconds
        let dateFormatter = DateFormatter()
        dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSS"
        dateFormatter.locale = Locale(identifier: "en_US_POSIX")
        dateFormatter.timeZone = TimeZone(secondsFromGMT: 0)

        // Try multiple date formats
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let dateString = try container.decode(String.self)

            // Try ISO8601 with microseconds
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            // Try ISO8601 with milliseconds
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSS"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            // Try standard ISO8601
            dateFormatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
            if let date = dateFormatter.date(from: dateString) {
                return date
            }

            // Try ISO8601 with Z
            let iso8601Formatter = ISO8601DateFormatter()
            iso8601Formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = iso8601Formatter.date(from: dateString) {
                return date
            }

            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode date string: \(dateString)")
        }
    }

    // MARK: - Generic Request Method
    private func makeRequest<T: Decodable>(
        endpoint: String,
        method: String = "GET",
        body: Data? = nil
    ) async throws -> T {
        guard let url = URL(string: "\(apiBaseURL)\(endpoint)") else {
            throw APIError(statusCode: nil, message: "Invalid URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30

        if let body = body {
            request.httpBody = body
        }

        do {
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                print("❌ Invalid HTTP response")
                throw APIError(statusCode: nil, message: "Invalid response")
            }

            print("📡 API Request: \(method) \(endpoint)")
            print("📊 Status Code: \(httpResponse.statusCode)")
            print("📦 Response Size: \(data.count) bytes")

            guard (200...299).contains(httpResponse.statusCode) else {
                let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
                print("❌ API Error: \(errorMessage)")
                throw APIError(statusCode: httpResponse.statusCode, message: errorMessage)
            }

            // Log raw JSON for debugging
            if let jsonString = String(data: data, encoding: .utf8) {
                print("📄 Raw JSON Response:")
                print(jsonString.prefix(500)) // First 500 chars
            }

            do {
                let decoded = try decoder.decode(T.self, from: data)
                print("✅ Successfully decoded \(T.self)")
                return decoded
            } catch let decodingError as DecodingError {
                print("❌ Decoding Error:")
                switch decodingError {
                case .keyNotFound(let key, let context):
                    print("   - Missing key: \(key.stringValue)")
                    print("   - Context: \(context.debugDescription)")
                    print("   - Coding path: \(context.codingPath.map { $0.stringValue }.joined(separator: " -> "))")
                case .typeMismatch(let type, let context):
                    print("   - Type mismatch: expected \(type)")
                    print("   - Context: \(context.debugDescription)")
                    print("   - Coding path: \(context.codingPath.map { $0.stringValue }.joined(separator: " -> "))")
                case .valueNotFound(let type, let context):
                    print("   - Value not found: \(type)")
                    print("   - Context: \(context.debugDescription)")
                    print("   - Coding path: \(context.codingPath.map { $0.stringValue }.joined(separator: " -> "))")
                case .dataCorrupted(let context):
                    print("   - Data corrupted")
                    print("   - Context: \(context.debugDescription)")
                    print("   - Coding path: \(context.codingPath.map { $0.stringValue }.joined(separator: " -> "))")
                @unknown default:
                    print("   - Unknown decoding error")
                }
                throw APIError(statusCode: nil, message: "Failed to decode response: \(decodingError.localizedDescription)")
            }
        } catch let error as APIError {
            throw error
        } catch {
            print("❌ Network error: \(error)")
            throw APIError(statusCode: nil, message: "Network error: \(error.localizedDescription)")
        }
    }

    // MARK: - Health Check
    func checkHealth() async throws -> HealthResponse {
        return try await makeRequest(endpoint: "/api/health")
    }

    // MARK: - Conversations
    func getConversations(
        limit: Int = 50,
        offset: Int = 0,
        excludeAds: Bool = false
    ) async throws -> ConversationsResponse {
        let endpoint = "/api/conversations?limit=\(limit)&offset=\(offset)&exclude_ads=\(excludeAds)"
        return try await makeRequest(endpoint: endpoint)
    }

    func getConversation(
        id: String,
        includeMessages: Bool = true,
        messageLimit: Int = 50
    ) async throws -> ConversationDetailResponse {
        let endpoint = "/api/conversations/\(id)?include_messages=\(includeMessages)&message_limit=\(messageLimit)"
        return try await makeRequest(endpoint: endpoint)
    }

    // MARK: - Messages
    func getMessages(
        conversationId: String? = nil,
        senderId: String? = nil,
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> MessagesResponse {
        var components = URLComponents(string: "\(apiBaseURL)/api/messages")!
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)")
        ]

        if let conversationId = conversationId {
            queryItems.append(URLQueryItem(name: "conversation_id", value: conversationId))
        }

        if let senderId = senderId {
            queryItems.append(URLQueryItem(name: "sender_id", value: senderId))
        }

        components.queryItems = queryItems

        guard let url = components.url else {
            throw APIError(statusCode: nil, message: "Invalid URL")
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 30

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError(statusCode: nil, message: "Invalid response")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw APIError(statusCode: httpResponse.statusCode, message: errorMessage)
        }

        return try decoder.decode(MessagesResponse.self, from: data)
    }

    // MARK: - Media
    func getMediaURL(mediaId: Int) -> URL? {
        return URL(string: "\(apiBaseURL)/api/media/\(mediaId)/file")
    }

    func downloadMedia(mediaId: Int) async throws -> Data {
        guard let url = getMediaURL(mediaId: mediaId) else {
            throw APIError(statusCode: nil, message: "Invalid media URL")
        }

        var request = URLRequest(url: url)
        request.timeoutInterval = 60

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError(statusCode: nil, message: "Invalid response")
        }

        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError(statusCode: httpResponse.statusCode, message: "Failed to download media")
        }

        return data
    }

    // MARK: - Users
    func getCurrentUser() async throws -> User {
        return try await makeRequest(endpoint: "/api/users/current")
    }

    func getUser(id: String) async throws -> User {
        return try await makeRequest(endpoint: "/api/users/\(id)")
    }
    
    // MARK: - Search
    func searchMessages(
        query: String,
        senderId: String? = nil,
        conversationId: String? = nil,
        limit: Int = 50,
        offset: Int = 0
    ) async throws -> SearchResponse {
        var components = URLComponents(string: "\(apiBaseURL)/api/search")!
        var queryItems: [URLQueryItem] = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)"),
            URLQueryItem(name: "offset", value: "\(offset)")
        ]
        
        if let senderId = senderId {
            queryItems.append(URLQueryItem(name: "sender_id", value: senderId))
        }
        
        if let conversationId = conversationId {
            queryItems.append(URLQueryItem(name: "conversation_id", value: conversationId))
        }
        
        components.queryItems = queryItems
        
        guard let url = components.url else {
            throw APIError(statusCode: nil, message: "Invalid URL")
        }
        
        var request = URLRequest(url: url)
        request.timeoutInterval = 30
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError(statusCode: nil, message: "Invalid response")
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw APIError(statusCode: httpResponse.statusCode, message: errorMessage)
        }
        
        return try decoder.decode(SearchResponse.self, from: data)
    }
    
    // MARK: - Device Registration (Push Notifications)
    
    func registerDeviceToken(_ token: String) async throws -> Bool {
        guard let url = URL(string: "\(apiBaseURL)/api/devices/register") else {
            throw APIError(statusCode: nil, message: "Invalid URL")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 30
        
        let body: [String: Any] = [
            "device_token": token,
            "platform": "ios",
            "app_version": Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
        ]
        
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError(statusCode: nil, message: "Invalid response")
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            let errorMessage = String(data: data, encoding: .utf8) ?? "Unknown error"
            throw APIError(statusCode: httpResponse.statusCode, message: errorMessage)
        }
        
        print("✅ Device token registered with backend")
        return true
    }
    
    func unregisterDeviceToken(_ token: String) async throws -> Bool {
        guard let url = URL(string: "\(apiBaseURL)/api/devices/unregister/\(token)") else {
            throw APIError(statusCode: nil, message: "Invalid URL")
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.timeoutInterval = 30
        
        let (_, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError(statusCode: nil, message: "Invalid response")
        }
        
        guard (200...299).contains(httpResponse.statusCode) else {
            throw APIError(statusCode: httpResponse.statusCode, message: "Failed to unregister")
        }
        
        print("✅ Device token unregistered from backend")
        return true
    }
}
