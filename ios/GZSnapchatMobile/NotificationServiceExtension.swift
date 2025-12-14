import UserNotifications

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

        // Check if there's an image URL in the notification payload
        guard let imageUrlString = request.content.userInfo["image_url"] as? String else {
            // No image URL, just deliver the notification as-is
            contentHandler(bestAttemptContent)
            return
        }

        // Construct full URL using the API base URL from UserDefaults
        let apiBaseURL = UserDefaults(suiteName: "group.com.georgesaker147.snapstash")?.string(forKey: "apiBaseURL") ?? ""
        let fullImageURL: URL?

        if imageUrlString.hasPrefix("http://") || imageUrlString.hasPrefix("https://") {
            // Already a full URL
            fullImageURL = URL(string: imageUrlString)
        } else {
            // Relative URL, construct full URL
            fullImageURL = URL(string: apiBaseURL + imageUrlString)
        }

        guard let imageURL = fullImageURL else {
            print("⚠️ Invalid image URL: \(imageUrlString)")
            contentHandler(bestAttemptContent)
            return
        }

        print("📥 Downloading notification image from: \(imageURL)")

        // Download the image
        downloadImage(from: imageURL) { [weak self] attachment in
            guard let self = self else { return }

            if let attachment = attachment {
                bestAttemptContent.attachments = [attachment]
                print("✅ Image attached to notification")
            } else {
                print("❌ Failed to attach image to notification")
            }

            contentHandler(bestAttemptContent)
        }
    }

    override func serviceExtensionTimeWillExpire() {
        // Called just before the extension will be terminated by the system.
        // Use this as an opportunity to deliver your "best attempt" at modified content.
        if let contentHandler = contentHandler, let bestAttemptContent = bestAttemptContent {
            contentHandler(bestAttemptContent)
        }
    }

    private func downloadImage(from url: URL, completion: @escaping (UNNotificationAttachment?) -> Void) {
        let task = URLSession.shared.downloadTask(with: url) { localURL, response, error in
            guard let localURL = localURL else {
                print("❌ Download failed: \(error?.localizedDescription ?? "Unknown error")")
                completion(nil)
                return
            }

            // Create a temporary file URL for the attachment
            let tempDirectory = FileManager.default.temporaryDirectory
            let fileExtension = url.pathExtension.isEmpty ? "jpg" : url.pathExtension
            let tempFileURL = tempDirectory.appendingPathComponent(UUID().uuidString).appendingPathExtension(fileExtension)

            do {
                // Move the downloaded file to the temp location
                try FileManager.default.moveItem(at: localURL, to: tempFileURL)

                // Create the attachment
                let attachment = try UNNotificationAttachment(identifier: "image", url: tempFileURL, options: nil)
                completion(attachment)
            } catch {
                print("❌ Error creating attachment: \(error.localizedDescription)")
                completion(nil)
            }
        }

        task.resume()
    }
}
