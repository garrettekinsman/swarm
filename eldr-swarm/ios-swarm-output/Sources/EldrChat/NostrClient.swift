import Foundation
import Combine

// MARK: - Nostr Constants (GARRO-compliant)

private struct Constants {
    static let backgroundColor = Color(red: 10/255, green: 10/255, blue: 15/255)   // #0a0a0f
    static let secondaryBackgroundColor = Color(red: 20/255, green: 20/255, blue: 27/255) // #14141b
    static let tertiaryBackgroundColor = Color(red: 30/255, green: 30/255, blue: 40/255)  // #1e1e28
    static let accentColor = Color(red: 124/255, green: 58/255, blue: 237/255) // #7c3aed
    static let textColorPrimary = Color(red: 240/255, green: 240/255, blue: 245/255) // #f0f0f5
    static let textColorSecondary = Color(red: 143/255, green: 143/255, blue: 163/255) // #8f8fa3
    static let textColorTertiary = Color(red: 90/255, green: 90/255, blue: 110/255) // #5a5a6e
    static let borderColor = Color(red: 42/255, green: 42/255, blue: 53/255) // #2a2a35
    static let errorColor = Color(red: 255/255, green: 69/255, blue: 58/255) // #ff453a
    static let minimumTouchTarget = CGFloat(44)
    static let standardPadding = CGFloat(8)
}

// MARK: - Nostr Events

public struct NostrEvent: Identifiable, Equatable, Sendable {
    public let id: String
    public let publicKey: String
    public let content: String
    public let createdAt: UInt64
    public let kind: Int
    public let tags: [[String]]
    public let signature: String
    
    // NIP-04 stub: unencrypted DM content placeholder
    // Full encryption handled by separate crypto module in v1.1
    public var decryptedContent: String {
        content // Placeholder — actual decryption in v1.1
    }
    
    public init(id: String = "",
                publicKey: String = "",
                content: String = "",
                createdAt: UInt64 = 0,
                kind: Int = 0,
                tags: [[String]] = [],
                signature: String = "") {
        self.id = id
        self.publicKey = publicKey
        self.content = content
        self.createdAt = createdAt
        self.kind = kind
        self.tags = tags
        self.signature = signature
    }
}

// MARK: - Nostr Client

@MainActor
public actor NostrClient: Sendable {
    public enum ConnectionState: Equatable, Sendable {
        case disconnected
        case connecting
        case connected
        case error(String)
    }
    
    private var socketTask: URLSessionWebSocketTask?
    private let urlSession: URLSession
    private let relayURLs: [URL]
    private var pendingSubscriptions: [String: ((NostrEvent) -> Void)] = [:]
    private var currentConnectionState: ConnectionState = .disconnected
    
    public var connectionState: ConnectionState {
        get { currentConnectionState }
        set { currentConnectionState = newValue }
    }
    
    public init(relayURLs: [URL]) {
        let configuration = URLSessionConfiguration.default
        configuration.timeoutIntervalForRequest = 15.0
        self.urlSession = URLSession(configuration: configuration)
        self.relayURLs = relayURLs
    }
    
    public func connect() async {
        guard !relayURLs.isEmpty else {
            currentConnectionState = .error("No relays configured")
            return
        }
        
        currentConnectionState = .connecting
        
        guard let url = relayURLs.first else {
            currentConnectionState = .error("No valid relay URL")
            return
        }
        
        do {
            let (bytes, _) = try await urlSession.webSocketTask(with: url).upgrade { task in
                self.socketTask = task
                await self.handleSocket(task)
            }
            
            currentConnectionState = .connected
            
            // Send subscriptions for all pending ones
            for (subscriptionID, _) in pendingSubscriptions {
                try? await send REQ(subscriptionID: subscriptionID)
            }
            
        } catch {
            currentConnectionState = .error("Connection failed: \(error.localizedDescription)")
        }
    }
    
    public func disconnect() {
        socketTask?.cancel()
        socketTask = nil
        currentConnectionState = .disconnected
        pendingSubscriptions = [:]
    }
    
    // MARK: - Subscription
    
    public func subscribe(to subscriptionID: String, onEvent: @escaping (NostrEvent) -> Void) async {
        pendingSubscriptions[subscriptionID] = onEvent
        if case .connected = currentConnectionState {
            try? await send REQ(subscriptionID: subscriptionID)
        }
    }
    
    public func unsubscribe(from subscriptionID: String) async {
        pendingSubscriptions.removeValue(forKey: subscriptionID)
        if case .connected = currentConnectionState {
            try? await send CLOSE(subscriptionID: subscriptionID)
        }
    }
    
    // MARK: - Sending Messages
    
    public func sendEvent(_ event: NostrEvent) async throws {
        guard case .connected = currentConnectionState else {
            throw NostrError.notConnected
        }
        
        let payload = try JSONEncoder().encode(event)
        let message = try JSONSerialization.jsonObject(with: payload) as? [String: Any]
        let json = try JSONSerialization.data(withJSONObject: message ?? [:], options: [])
        let jsonString = String(data: json, encoding: .utf8) ?? "event"
        
        try await socketTask?.sendString("EVENT \(jsonString)") { error in
            if let error = error {
                // Handle error in closure
            }
        }
    }
    
    private func send REQ(subscriptionID: String) async throws {
        try await socketTask?.sendString("REQ \(subscriptionID)") { _ in }
    }
    
    private func send CLOSE(subscriptionID: String) async throws {
        try await socketTask?.sendString("CLOSE \(subscriptionID)") { _ in }
    }
    
    // MARK: - Socket Handling
    
    private func handleSocket(_ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            Task { [weak self] in
                guard let self = self else { return }
                
                switch result {
                case .success(let message):
                    switch message {
                    case .string(let text):
                        await self.parseMessage(text)
                    case .data(let data):
                        if let text = String(data: data, encoding: .utf8) {
                            await self.parseMessage(text)
                        }
                    @unknown default:
                        break
                    }
                    
                case .failure(let error):
                    self.currentConnectionState = .error("Socket error: \(error.localizedDescription)")
                }
                
                // Continue receiving
                self.handleSocket(task)
            }
        }
    }
    
    private func parseMessage(_ message: String) async {
        let components = message.components(separatedBy: " ", maxSplits: 2)
        guard components.count >= 2 else { return }
        
        switch components[0] {
        case "EVENT":
            guard let json = components.last?.data(using: .utf8),
                  let dict = try? JSONSerialization.jsonObject(with: json, options: []) as? [String: Any],
                  let event = NostrEvent(from: dict) else {
                return
            }
            // Dispatch to subscribed handlers
            for (_, handler) in pendingSubscriptions {
                handler(event)
            }
            
        case "OK":
            // Event acknowledgment — no-op for this stub
            break
            
        case "EOSE":
            // End of Substream — no-op for this stub
            break
            
        default:
            break
        }
    }
}

// MARK: - Nostr Event JSON Decoding

extension NostrEvent {
    init?(from dict: [String: Any]) {
        guard
            let id = dict["id"] as? String,
            let pubKey = dict["pubkey"] as? String,
            let contentStr = dict["content"] as? String,
            let createdAt = dict["created_at"] as? UInt64,
            let kind = dict["kind"] as? Int,
            let tags = dict["tags"] as? [[String]],
            let signature = dict["sig"] as? String
        else {
            return nil
        }
        
        self.id = id
        publicKey = pubKey
        content = contentStr
        self.createdAt = createdAt
        self.kind = kind
        self.tags = tags
        self.signature = signature
    }
}

// MARK: - Errors

enum NostrError: LocalizedError, Sendable {
    case notConnected
    case parsingError
    
    var errorDescription: String? {
        switch self {
        case .notConnected:
            return "Client is not connected to a relay"
        case .parsingError:
            return "Failed to parse response"
        }
    }
}

// MARK: - SwiftUI Preview Helpers (for reference)

#if canImport(SwiftUI) [REDACTED][REDACTED] DEBUG
import SwiftUI

@available(iOS 17.0, macOS 14.0, *)
struct NostrClient_Previews: PreviewProvider {
    static var previews: some View {
        Color.clear
            .background(Constants.backgroundColor)
            .previewLayout(.sizeThatFits)
    }
}
#endif