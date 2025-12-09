//
//  MediaViewer.swift
//  SnapStashMobile
//
//  Created by George on 13/11/2025.
//

import SwiftUI
import AVKit

struct MediaViewer: View {
    @EnvironmentObject var apiService: APIService
    @Environment(\.dismiss) var dismiss

    let media: MediaAsset
    @State private var mediaData: Data?
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var showShareSheet = false
    @State private var shareURL: URL?

    var body: some View {
        NavigationView {
            ZStack {
                Color.black.ignoresSafeArea()

                if isLoading {
                    ProgressView("Loading media...")
                        .progressViewStyle(.circular)
                        .tint(.white)
                } else if let errorMessage = errorMessage {
                    VStack(spacing: 16) {
                        Image(systemName: "exclamationmark.triangle")
                            .font(.system(size: 50))
                            .foregroundColor(.red)
                        Text("Error")
                            .font(.headline)
                            .foregroundColor(.white)
                        Text(errorMessage)
                            .font(.subheadline)
                            .foregroundColor(.white.opacity(0.7))
                            .multilineTextAlignment(.center)
                            .padding(.horizontal)
                        Button("Retry") {
                            Task {
                                await loadMedia()
                            }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                } else if let mediaData = mediaData {
                    if media.isImage {
                        ImageViewer(imageData: mediaData)
                    } else if media.isVideo {
                        VideoViewer(videoData: mediaData)
                    } else if media.isAudio {
                        AudioViewer(audioData: mediaData, media: media)
                    } else {
                        UnsupportedMediaView(media: media)
                    }
                } else {
                    Text("No media data")
                        .foregroundColor(.white)
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button(action: { dismiss() }) {
                        Image(systemName: "xmark.circle.fill")
                            .foregroundColor(.white)
                            .font(.title2)
                    }
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: prepareShare) {
                        Image(systemName: "square.and.arrow.up")
                            .foregroundColor(.white)
                            .font(.title2)
                    }
                    .disabled(mediaData == nil)
                }
            }
            .sheet(isPresented: $showShareSheet) {
                if let shareURL = shareURL {
                    ShareSheet(activityItems: [shareURL])
                }
            }
            .task {
                await loadMedia()
            }
        }
    }

    private func loadMedia() async {
        // Check for preloaded media first
        if let cachedData = MessagePreloader.shared.getCachedMedia(for: media.id) {
            print("📦 Using preloaded media for ID: \(media.id)")
            mediaData = cachedData
            return
        }
        
        isLoading = true
        errorMessage = nil

        do {
            let data = try await apiService.downloadMedia(mediaId: media.id)
            mediaData = data
            
            // Update the preloader cache
            MessagePreloader.shared.updateMediaCache(mediaId: media.id, data: data)
        } catch let error as APIError {
            errorMessage = error.message
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func prepareShare() {
        guard let mediaData = mediaData else { return }
        
        // Determine proper file extension
        let fileExtension: String
        if media.isImage {
            fileExtension = media.mimeType.contains("png") ? "png" : "jpg"
        } else if media.isVideo {
            fileExtension = "mp4"
        } else if media.isAudio {
            fileExtension = "m4a"
        } else {
            fileExtension = media.fileType
        }
        
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("share_\(media.id).\(fileExtension)")
        do {
            try mediaData.write(to: tempURL)
            shareURL = tempURL
            showShareSheet = true
        } catch {
            print("Failed to prepare share: \(error)")
        }
    }
}

// UIKit wrapper for share sheet
struct ShareSheet: UIViewControllerRepresentable {
    let activityItems: [Any]
    
    func makeUIViewController(context: Context) -> UIActivityViewController {
        let controller = UIActivityViewController(activityItems: activityItems, applicationActivities: nil)
        return controller
    }
    
    func updateUIViewController(_ uiViewController: UIActivityViewController, context: Context) {}
}

struct ImageViewer: View {
    let imageData: Data

    var body: some View {
        if let uiImage = UIImage(data: imageData) {
            ZoomableScrollView {
                Image(uiImage: uiImage)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
            }
        } else {
            Text("Failed to load image")
                .foregroundColor(.white)
        }
    }
}

struct ZoomableScrollView<Content: View>: UIViewRepresentable {
    let content: Content
    
    init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }
    
    func makeUIView(context: Context) -> UIScrollView {
        let scrollView = UIScrollView()
        scrollView.delegate = context.coordinator
        scrollView.maximumZoomScale = 5.0
        scrollView.minimumZoomScale = 1.0
        scrollView.bouncesZoom = true
        scrollView.showsHorizontalScrollIndicator = false
        scrollView.showsVerticalScrollIndicator = false
        scrollView.backgroundColor = .clear
        
        let hostedView = context.coordinator.hostingController.view!
        hostedView.translatesAutoresizingMaskIntoConstraints = false
        hostedView.backgroundColor = .clear
        
        scrollView.addSubview(hostedView)
        
        // Double tap gesture
        let doubleTap = UITapGestureRecognizer(target: context.coordinator, action: #selector(Coordinator.handleDoubleTap(_:)))
        doubleTap.numberOfTapsRequired = 2
        scrollView.addGestureRecognizer(doubleTap)
        
        return scrollView
    }
    
    func updateUIView(_ scrollView: UIScrollView, context: Context) {
        context.coordinator.hostingController.rootView = content
        
        DispatchQueue.main.async {
            let hostedView = context.coordinator.hostingController.view!
            let size = context.coordinator.hostingController.sizeThatFits(in: scrollView.bounds.size)
            
            hostedView.frame = CGRect(origin: .zero, size: size)
            scrollView.contentSize = size
            
            context.coordinator.centerContent(in: scrollView)
        }
    }
    
    func makeCoordinator() -> Coordinator {
        Coordinator(hostingController: UIHostingController(rootView: content))
    }
    
    class Coordinator: NSObject, UIScrollViewDelegate {
        let hostingController: UIHostingController<Content>
        
        init(hostingController: UIHostingController<Content>) {
            self.hostingController = hostingController
        }
        
        func viewForZooming(in scrollView: UIScrollView) -> UIView? {
            return hostingController.view
        }
        
        func scrollViewDidZoom(_ scrollView: UIScrollView) {
            centerContent(in: scrollView)
        }
        
        func centerContent(in scrollView: UIScrollView) {
            guard let hostedView = hostingController.view else { return }
            
            let scrollViewSize = scrollView.bounds.size
            let contentSize = hostedView.frame.size
            
            let horizontalInset = max(0, (scrollViewSize.width - contentSize.width * scrollView.zoomScale) / 2)
            let verticalInset = max(0, (scrollViewSize.height - contentSize.height * scrollView.zoomScale) / 2)
            
            scrollView.contentInset = UIEdgeInsets(
                top: verticalInset,
                left: horizontalInset,
                bottom: verticalInset,
                right: horizontalInset
            )
        }
        
        @objc func handleDoubleTap(_ gesture: UITapGestureRecognizer) {
            guard let scrollView = gesture.view as? UIScrollView else { return }
            
            if scrollView.zoomScale > scrollView.minimumZoomScale {
                scrollView.setZoomScale(scrollView.minimumZoomScale, animated: true)
            } else {
                let location = gesture.location(in: hostingController.view)
                let zoomScale: CGFloat = 2.5
                
                let width = scrollView.bounds.width / zoomScale
                let height = scrollView.bounds.height / zoomScale
                let x = location.x - width / 2
                let y = location.y - height / 2
                
                let zoomRect = CGRect(x: x, y: y, width: width, height: height)
                scrollView.zoom(to: zoomRect, animated: true)
            }
        }
    }
}

struct VideoViewer: View {
    let videoData: Data
    @State private var player: AVPlayer?

    var body: some View {
        Group {
            if let player = player {
                VideoPlayer(player: player)
                    .ignoresSafeArea()
                    .onAppear {
                        player.play()
                    }
            } else {
                ProgressView("Preparing video...")
                    .tint(.white)
            }
        }
        .task {
            await prepareVideo()
        }
    }

    private func prepareVideo() async {
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("video_\(UUID().uuidString).mp4")
        do {
            try videoData.write(to: tempURL)
            player = AVPlayer(url: tempURL)
        } catch {
            print("Failed to prepare video: \(error)")
        }
    }
}

struct AudioViewer: View {
    let audioData: Data
    let media: MediaAsset
    @State private var player: AVPlayer?
    @State private var isPlaying = false

    var body: some View {
        VStack(spacing: 30) {
            Image(systemName: "waveform.circle.fill")
                .font(.system(size: 100))
                .foregroundColor(.yellow)

            VStack(spacing: 8) {
                Text("Audio Message")
                    .font(.title2)
                    .fontWeight(.semibold)
                    .foregroundColor(.white)

                if let sender = media.sender {
                    Text("From: \(sender.displayName)")
                        .font(.subheadline)
                        .foregroundColor(.white.opacity(0.7))
                }

                Text(formatFileSize(media.fileSize))
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.5))
            }

            Button(action: togglePlayback) {
                Image(systemName: isPlaying ? "pause.circle.fill" : "play.circle.fill")
                    .font(.system(size: 60))
                    .foregroundColor(.yellow)
            }
        }
        .task {
            await prepareAudio()
        }
    }

    private func prepareAudio() async {
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent("audio_\(UUID().uuidString).m4a")
        do {
            try audioData.write(to: tempURL)
            player = AVPlayer(url: tempURL)
        } catch {
            print("Failed to prepare audio: \(error)")
        }
    }

    private func togglePlayback() {
        guard let player = player else { return }

        if isPlaying {
            player.pause()
        } else {
            player.play()
        }
        isPlaying.toggle()
    }

    private func formatFileSize(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB]
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

struct UnsupportedMediaView: View {
    let media: MediaAsset

    var body: some View {
        VStack(spacing: 20) {
            Image(systemName: "doc.fill")
                .font(.system(size: 80))
                .foregroundColor(.gray)

            Text("Unsupported Media Type")
                .font(.title2)
                .fontWeight(.semibold)
                .foregroundColor(.white)

            VStack(spacing: 8) {
                Text("File Type: \(media.fileType)")
                Text("MIME Type: \(media.mimeType)")
                Text("Size: \(formatFileSize(media.fileSize))")
            }
            .font(.caption)
            .foregroundColor(.white.opacity(0.7))
        }
    }

    private func formatFileSize(_ bytes: Int) -> String {
        let formatter = ByteCountFormatter()
        formatter.allowedUnits = [.useKB, .useMB]
        formatter.countStyle = .file
        return formatter.string(fromByteCount: Int64(bytes))
    }
}

#Preview {
    MediaViewer(media: MediaAsset(
        id: 1,
        originalFilename: "test.jpg",
        filePath: "/test/path",
        fileHash: "abc123",
        fileSize: 1024000,
        fileType: "image",
        mimeType: "image/jpeg",
        cacheKey: "key",
        cacheId: "cache123",
        category: "shared",
        timestampSource: "file",
        mappingMethod: "hash",
        fileTimestamp: ISO8601DateFormatter().string(from: Date()),
        senderId: "user123",
        createdAt: ISO8601DateFormatter().string(from: Date()),
        updatedAt: ISO8601DateFormatter().string(from: Date()),
        sender: nil
    ))
    .environmentObject(APIService())
}
