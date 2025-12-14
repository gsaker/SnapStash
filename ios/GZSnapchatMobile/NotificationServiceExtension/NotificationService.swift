import UserNotifications
import UniformTypeIdentifiers
import Intents
import UIKit

class NotificationService: UNNotificationServiceExtension {

    var contentHandler: ((UNNotificationContent) -> Void)?
    var bestAttemptContent: UNMutableNotificationContent?

    override func didReceive(_ request: UNNotificationRequest, withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void) {
        self.contentHandler = contentHandler
        bestAttemptContent = (request.content.mutableCopy() as? UNMutableNotificationContent)

        guard let bestAttemptContent = bestAttemptContent else {
            contentHandler(request.content)
            return
        }

        let userInfo = request.content.userInfo
        let userInfoKeys = userInfo.keys.map { "\($0)" }.sorted()
        print("📬 NotificationService didReceive. keys=\(userInfoKeys)")

        // Collect potential attachment URLs from the payload
        let imageUrlString: String? = {
            if let value = userInfo["image_url"] as? String { return value }
            if let value = userInfo["imageUrl"] as? String { return value }
            if let aps = userInfo["aps"] as? [String: Any] {
                if let value = aps["image_url"] as? String { return value }
                if let value = aps["imageUrl"] as? String { return value }
            }
            return nil
        }()

        let apiBaseURL = UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.string(forKey: "apiBaseURL")
        let senderAvatarUrlString: String? = {
            if let value = userInfo["sender_avatar_url"] as? String { return value }
            if let aps = userInfo["aps"] as? [String: Any] {
                if let value = aps["sender_avatar_url"] as? String { return value }
            }
            return nil
        }()

        let groupParticipants: [[String: Any]]? = {
            if let value = userInfo["group_participants"] as? [[String: Any]] { return value }
            return nil
        }()

        print("ℹ️ image_url=\(imageUrlString ?? "nil") sender_avatar_url=\(senderAvatarUrlString ?? "nil") group_participants=\(groupParticipants?.count ?? 0) apiBaseURL=\(apiBaseURL ?? "nil")")

        func resolveURL(_ value: String) -> URL? {
            if let absolute = URL(string: value), absolute.scheme != nil {
                return absolute
            }
            guard let apiBaseURL, let base = URL(string: apiBaseURL) else {
                return nil
            }
            return URL(string: value, relativeTo: base)?.absoluteURL
        }

        let imageURL = imageUrlString.flatMap(resolveURL)
        let avatarURL = senderAvatarUrlString.flatMap(resolveURL)

        if imageUrlString != nil && imageURL == nil {
            print("⚠️ Unable to construct image URL. image_url=\(imageUrlString ?? "nil") apiBaseURL=\(apiBaseURL ?? "nil")")
        }
        if senderAvatarUrlString != nil && avatarURL == nil {
            print("⚠️ Unable to construct sender avatar URL. sender_avatar_url=\(senderAvatarUrlString ?? "nil") apiBaseURL=\(apiBaseURL ?? "nil")")
        }

        // Parse group participant URLs
        var groupAvatarURLs: [URL] = []
        if let participants = groupParticipants {
            for participant in participants.prefix(3) {
                if let urlString = participant["bitmoji_url"] as? String,
                   let url = resolveURL(urlString) {
                    groupAvatarURLs.append(url)
                }
            }
            print("ℹ️ Parsed \(groupAvatarURLs.count) group participant avatar URLs")
        }

        if imageURL == nil && avatarURL == nil && groupAvatarURLs.isEmpty {
            contentHandler(bestAttemptContent)
            return
        }

        let group = DispatchGroup()
        var imageAttachment: UNNotificationAttachment?
        var avatarAttachment: UNNotificationAttachment?
        var avatarImageData: Data?

        if let imageURL {
            group.enter()
            print("📥 Downloading notification image from: \(imageURL)")
            downloadAttachment(from: imageURL, identifier: "image") { attachment in
                imageAttachment = attachment
                group.leave()
            }
        }

        // Handle group chat icons or individual avatar
        if !groupAvatarURLs.isEmpty {
            // Download all group participant avatars and generate composite icon
            group.enter()
            print("📥 Downloading \(groupAvatarURLs.count) group participant avatars")
            downloadGroupAvatars(from: groupAvatarURLs) { compositeData in
                avatarImageData = compositeData
                print("📥 Group icon generation result: \(compositeData != nil ? "success (\(compositeData!.count) bytes)" : "failed")")
                group.leave()
            }
        } else if let avatarURL {
            group.enter()
            print("📥 Downloading sender avatar from: \(avatarURL)")
            downloadAttachment(from: avatarURL, identifier: "avatar") { attachment in
                avatarAttachment = attachment
                print("📥 Avatar attachment result: \(attachment != nil ? "success" : "failed")")
                group.leave()
            }
            group.enter()
            downloadData(from: avatarURL) { data in
                avatarImageData = data
                print("📥 Avatar data download result: \(data != nil ? "success (\(data!.count) bytes)" : "failed")")
                group.leave()
            }
        }

        group.notify(queue: .global()) {
            var attachments: [UNNotificationAttachment] = []
            if let imageAttachment { attachments.append(imageAttachment) }
            if let avatarAttachment { attachments.append(avatarAttachment) }

            if !attachments.isEmpty {
                bestAttemptContent.attachments = attachments
                print("✅ Attached \(attachments.count) item(s) to notification")
            }

            // Set thread identifier for grouping (works for all notification types)
            if let conversationId = userInfo["conversation_id"] as? String {
                bestAttemptContent.threadIdentifier = conversationId
                print("✅ Set base threadIdentifier to: \(conversationId)")
            }

            let finalContent: UNNotificationContent = {
                guard #available(iOS 15.0, *) else {
                    print("⚠️ Communication notifications require iOS 15+")
                    return bestAttemptContent
                }

                guard let avatarImageData else {
                    print("⚠️ No avatar data available for communication notification. avatarURL was: \(avatarURL?.absoluteString ?? "nil")")
                    return bestAttemptContent
                }

                let handleValue = userInfo["sender_id"] as? String
                    ?? userInfo["senderId"] as? String
                    ?? bestAttemptContent.title

                let conversationId = userInfo["conversation_id"] as? String

                print("🔔 Creating communication notification - sender: \(bestAttemptContent.title), senderId: \(handleValue), conversationId: \(conversationId ?? "nil"), avatarSize: \(avatarImageData.count) bytes")

                let handle = INPersonHandle(value: handleValue, type: .unknown)

                // Add yellow background to Bitmoji avatar (only for individual DM avatars, not group icons)
                // Group icons already have yellow circles behind each participant
                let finalAvatarData: Data
                if !groupAvatarURLs.isEmpty {
                    // Group icon - use as-is (already has yellow circles for each participant)
                    finalAvatarData = avatarImageData
                } else {
                    // Individual DM avatar - add rounded rectangle yellow background
                    finalAvatarData = self.addCircularBackground(to: avatarImageData, color: UIColor(red: 1.0, green: 0.988, blue: 0.0, alpha: 1.0))
                }
                let image = INImage(imageData: finalAvatarData)

                let sender = INPerson(
                    personHandle: handle,
                    nameComponents: nil,
                    displayName: bestAttemptContent.title,
                    image: image,
                    contactIdentifier: nil,
                    customIdentifier: handleValue,
                    isMe: false,
                    suggestionType: .none
                )

                let intent = INSendMessageIntent(
                    recipients: nil,
                    outgoingMessageType: .outgoingMessageText,
                    content: bestAttemptContent.body,
                    speakableGroupName: nil,
                    conversationIdentifier: conversationId,
                    serviceName: nil,
                    sender: sender
                )

                do {
                    let updated = try bestAttemptContent.updating(from: intent)
                    print("✅ Successfully created communication notification content")
                    let mutable = (updated.mutableCopy() as? UNMutableNotificationContent) ?? bestAttemptContent
                    if !attachments.isEmpty {
                        mutable.attachments = attachments
                    }
                    // Ensure thread identifier is set for proper grouping
                    if let conversationId = conversationId {
                        mutable.threadIdentifier = conversationId
                        print("✅ Set threadIdentifier to: \(conversationId)")
                    }
                    return mutable
                } catch {
                    print("⚠️ Failed to apply communication intent: \(error.localizedDescription)")
                    return bestAttemptContent
                }
            }()

            contentHandler(finalContent)
        }
    }

    override func serviceExtensionTimeWillExpire() {
        // Called just before the extension will be terminated by the system.
        // Use this as an opportunity to deliver your "best attempt" at modified content.
        if let contentHandler = contentHandler, let bestAttemptContent = bestAttemptContent {
            contentHandler(bestAttemptContent)
        }
    }

    private func downloadAttachment(from url: URL, identifier: String, completion: @escaping (UNNotificationAttachment?) -> Void) {
        let task = URLSession.shared.downloadTask(with: url) { localURL, response, error in
            guard let localURL = localURL else {
                print("❌ Download failed: \(error?.localizedDescription ?? "Unknown error")")
                completion(nil)
                return
            }

            // Create a temporary file URL for the attachment
            let tempDirectory = FileManager.default.temporaryDirectory
            let suggestedFilenameExtension: String? = {
                if let suggested = response?.suggestedFilename {
                    let ext = (suggested as NSString).pathExtension
                    return ext.isEmpty ? nil : ext
                }
                return nil
            }()

            let mimeTypeExtension: String? = {
                guard let mimeType = response?.mimeType else { return nil }
                return UTType(mimeType: mimeType)?.preferredFilenameExtension
            }()

            let urlExtension: String? = {
                let ext = url.pathExtension
                if ext.isEmpty { return nil }
                if ext.lowercased() == "file" { return nil }
                return ext
            }()

            let fileExtension = suggestedFilenameExtension ?? mimeTypeExtension ?? urlExtension ?? "jpg"
            let tempFileURL = tempDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension(fileExtension)

            do {
                // Move the downloaded file to the temp location
                try FileManager.default.moveItem(at: localURL, to: tempFileURL)

                // Create the attachment
                let attachment = try UNNotificationAttachment(identifier: identifier, url: tempFileURL, options: nil)
                completion(attachment)
            } catch {
                if let http = response as? HTTPURLResponse {
                    print("❌ Attachment error (HTTP \(http.statusCode)) mimeType=\(response?.mimeType ?? "nil") suggestedFilename=\(response?.suggestedFilename ?? "nil")")
                } else {
                    print("❌ Attachment error mimeType=\(response?.mimeType ?? "nil") suggestedFilename=\(response?.suggestedFilename ?? "nil")")
                }
                print("❌ Error creating attachment: \(error.localizedDescription)")
                completion(nil)
            }
        }

        task.resume()
    }

    private func downloadData(from url: URL, completion: @escaping (Data?) -> Void) {
        let task = URLSession.shared.dataTask(with: url) { data, _, _ in
            completion(data)
        }
        task.resume()
    }

    private func addCircularBackground(to imageData: Data, color: UIColor) -> Data {
        guard let image = UIImage(data: imageData) else {
            return imageData
        }

        let size = image.size
        let diameter = max(size.width, size.height)
        let targetSize = CGSize(width: diameter, height: diameter)

        let renderer = UIGraphicsImageRenderer(size: targetSize)
        let resultImage = renderer.image { context in
            let rect = CGRect(origin: .zero, size: targetSize)

            // Draw rounded rectangle background (app icon shape)
            // iOS uses approximately 22.5% corner radius for app icons
            let cornerRadius = diameter * 0.225
            color.setFill()
            let backgroundPath = UIBezierPath(roundedRect: rect, cornerRadius: cornerRadius)
            backgroundPath.fill()

            // Draw Bitmoji centered on the background
            let imageRect = CGRect(
                x: (diameter - size.width) / 2,
                y: (diameter - size.height) / 2,
                width: size.width,
                height: size.height
            )
            image.draw(in: imageRect)
        }

        return resultImage.pngData() ?? imageData
    }

    private func downloadGroupAvatars(from urls: [URL], completion: @escaping (Data?) -> Void) {
        let group = DispatchGroup()
        var downloadedImages: [UIImage] = []
        var imageLock = NSLock()

        for url in urls {
            group.enter()
            downloadData(from: url) { data in
                defer { group.leave() }
                guard let data = data, let image = UIImage(data: data) else {
                    print("❌ Failed to download/decode group avatar from: \(url)")
                    return
                }
                imageLock.lock()
                downloadedImages.append(image)
                imageLock.unlock()
            }
        }

        group.notify(queue: .global()) {
            guard !downloadedImages.isEmpty else {
                print("❌ No group avatars downloaded successfully")
                completion(nil)
                return
            }

            // Generate composite icon
            let compositeImage = self.generateGroupIcon(from: downloadedImages, size: 300)
            completion(compositeImage?.pngData())
        }
    }

    private func generateGroupIcon(from images: [UIImage], size: CGFloat) -> UIImage? {
        guard !images.isEmpty else { return nil }

        let count = min(images.count, 3)
        let avatarSize = size * 0.6
        let adjustedAvatarSize = count == 3 ? avatarSize * 0.85 : avatarSize

        let renderer = UIGraphicsImageRenderer(size: CGSize(width: size, height: size))
        return renderer.image { context in
            // Transparent background
            UIColor.clear.setFill()
            context.fill(CGRect(origin: .zero, size: CGSize(width: size, height: size)))

            // Calculate positions
            let positions = calculatePositions(count: count, canvasSize: size, avatarSize: adjustedAvatarSize)

            // Draw each avatar
            for (index, image) in images.prefix(count).enumerated() {
                guard index < positions.count else { break }
                let position = positions[index]

                // Create circular Bitmoji with yellow background
                let circularImage = createCircularBitmoji(image: image, size: adjustedAvatarSize)
                circularImage.draw(at: position)
            }
        }
    }

    private func calculatePositions(count: Int, canvasSize: CGFloat, avatarSize: CGFloat) -> [CGPoint] {
        let center = canvasSize / 2

        switch count {
        case 1:
            // Centered
            let x = center - avatarSize / 2
            let y = center - avatarSize / 2
            return [CGPoint(x: x, y: y)]

        case 2:
            // Top-left and bottom-right
            let offset = canvasSize * 0.15
            return [
                CGPoint(x: center - avatarSize / 2 - offset, y: center - avatarSize / 2 - offset),
                CGPoint(x: center - avatarSize / 2 + offset, y: center - avatarSize / 2 + offset)
            ]

        default: // 3
            // Top-left, top-right, bottom-center
            let xOffset = canvasSize * 0.18
            let yOffset = canvasSize * 0.12
            let bottomYOffset = canvasSize * 0.18

            return [
                CGPoint(x: center - avatarSize / 2 - xOffset, y: center - avatarSize / 2 - yOffset),
                CGPoint(x: center - avatarSize / 2 + xOffset, y: center - avatarSize / 2 - yOffset),
                CGPoint(x: center - avatarSize / 2, y: center - avatarSize / 2 + bottomYOffset)
            ]
        }
    }

    private func createCircularBitmoji(image: UIImage, size: CGFloat) -> UIImage {
        let targetSize = CGSize(width: size, height: size)

        let renderer = UIGraphicsImageRenderer(size: targetSize)
        return renderer.image { context in
            let rect = CGRect(origin: .zero, size: targetSize)

            // Draw yellow circular background (Snapchat yellow)
            let yellowColor = UIColor(red: 1.0, green: 0.988, blue: 0.0, alpha: 1.0)
            yellowColor.setFill()
            context.cgContext.fillEllipse(in: rect)

            // Clip to circle for Bitmoji
            context.cgContext.addEllipse(in: rect)
            context.cgContext.clip()

            // Draw Bitmoji image on top of yellow background
            image.draw(in: rect, blendMode: .normal, alpha: 1.0)

            // Reset clip
            context.cgContext.resetClip()

            // Draw white stroke around the circle (matches main UI)
            let strokeWidth: CGFloat = 2.0
            let strokeRect = rect.insetBy(dx: strokeWidth / 2, dy: strokeWidth / 2)
            UIColor.white.setStroke()
            context.cgContext.setLineWidth(strokeWidth)
            context.cgContext.strokeEllipse(in: strokeRect)
        }
    }
}
