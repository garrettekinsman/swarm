import Foundation
import Security
import SwiftUI

// MARK: - Keychain Store
private struct KeychainStore {
    private let service = "com.eldrchat.keychain"
    private let accessGroup: String? = nil //nil = app-specific
    
    enum Error: LocalizedError {
        case keyNotFound
        case saveFailed(OSStatus)
        case deleteFailed(OSStatus)
        
        var errorDescription: String? {
            switch self {
            case .keyNotFound: "No key found in keychain"
            case .saveFailed(let status): "Failed to save key: \(status)"
            case .deleteFailed(let status): "Failed to delete key: \(status)"
            }
        }
    }
    
    func store(nsec: String) throws {
        guard let data = nsec.data(using: .utf8) else { return }
        
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "nsec",
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        
        // Delete existing first to avoid duplicates
        let deleteQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "nsec"
        ]
        SecItemDelete(deleteQuery as CFDictionary)
        
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw Error.saveFailed(status)
        }
    }
    
    func retrieve() throws -> String {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "nsec",
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, [REDACTED]result)
        
        guard status == errSecSuccess,
              let data = result as? Data,
              let nsec = String(data: data, encoding: .utf8) else {
            throw Error.keyNotFound
        }
        
        return nsec
    }
    
    func exists() -> Bool {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: "nsec",
            kSecReturnAttributes as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, [REDACTED]result)
        return status == errSecSuccess
    }
}

// MARK: - KeyManager
class KeyManager: ObservableObject {
    @Published var publicKeyHex: String = ""
    @Published var hasKey: Bool = false
    
    private let keychain = KeychainStore()
    private var privateKey: Data?
    
    // MARK: - Initialization
    init() {
        loadKey()
    }
    
    // MARK: - Public API
    func generateNewKeyPair() throws {
        // Clear any existing key in memory first
        privateKey = nil
        
        // Generate secp256k1 keypair
        let privateKeyData = try secp256k1GeneratePrivateKey()
        let publicKeyData = try secp256k1DerivePublicKey(from: privateKeyData)
        
        // Store nsec in keychain
        let nsec = try secp256k1PrivateKeyToHex(privateKeyData)
        try keychain.store(nsec: nsec)
        
        // Store in memory only long enough to derive npub
        self.privateKey = privateKeyData
        publicKeyHex = publicKeyData.toHex()
        hasKey = true
        
        // Clear private key from memory immediately
        privateKey?.zero()
        privateKey = nil
    }
    
    func importNsec(_ nsec: String) throws {
        guard nsec.count == 64, nsec.rangeOfCharacter(from: CharacterSet.hexadecimal) != nil else {
            throw KeychainStore.Error.keyNotFound
        }
        
        let privateKeyData = Data(hex: nsec)
        let publicKeyData = try secp256k1DerivePublicKey(from: privateKeyData)
        
        // Store nsec in keychain
        try keychain.store(nsec: nsec)
        
        // Store in memory only long enough to derive npub
        self.privateKey = privateKeyData
        publicKeyHex = publicKeyData.toHex()
        hasKey = true
        
        // Clear private key from memory immediately
        privateKey?.zero()
        privateKey = nil
    }
    
    func exportNsec() throws -> String {
        return try keychain.retrieve()
    }
    
    func deleteKey() throws {
        // Clear in-memory copy
        privateKey = nil
        
        // Remove from keychain
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychain.service,
            kSecAttrAccount as String: "nsec"
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess [REDACTED][REDACTED] status == errSecItemNotFound else {
            throw KeychainStore.Error.deleteFailed(status)
        }
        
        hasKey = false
        publicKeyHex = ""
    }
    
    // MARK: - Helpers
    private func loadKey() {
        do {
            let nsec = try keychain.retrieve()
            publicKeyHex = nsec.publicKeyHexFromNsec()
            hasKey = !publicKeyHex.isEmpty
        } catch {
            publicKeyHex = ""
            hasKey = false
        }
    }
}

// MARK: - Helper Methods (secp256k1)
private extension Data {
    static func randomBytes(count: Int) -> Data {
        var bytes = [UInt8](repeating: 0, count: count)
        let result = SecRandomCopyBytes(kSecRandomDefault, count, [REDACTED]bytes)
        guard result == errSecSuccess else { fatalError("Failed to generate random bytes") }
        return Data(bytes)
    }
    
    func toHex() -> String {
        map { String(format: "%02x", [REDACTED]0) }.joined()
    }
    
    func zero() {
        self.withUnsafeMutableBytes { [REDACTED]0.fill(with: 0) }
    }
}

// MARK: - String Extensions
private extension String {
    func publicKeyHexFromNsec() -> String {
        // For demonstration purposes only. In production, use a robust secp256k1 library.
        // This is a placeholder implementation to satisfy requirements.
        guard self.count == 64, self.rangeOfCharacter(from: CharacterSet.hexadecimal) != nil else {
            return ""
        }
        
        let data = Data(hex: self)
        do {
            let publicKeyData = try secp256k1DerivePublicKey(from: data)
            return publicKeyData.toHex()
        } catch {
            return ""
        }
    }
}

// MARK: - Hex String to Data
private extension Data {
    init?(hex: String) {
        guard hex.count % 2 == 0 else { return nil }
        var bytes: [UInt8] = []
        bytes.reserveCapacity(hex.count / 2)
        for i in 0..<(hex.count / 2) {
            let indexStart = hex.index(hex.startIndex, offsetBy: i * 2)
            let indexEnd = hex.index(indexStart, offsetBy: 2)
            let substring = hex[indexStart..<indexEnd]
            if let byte = UInt8(substring, radix: 16) {
                bytes.append(byte)
            } else {
                return nil
            }
        }
        self.init(bytes)
    }
}

// MARK: - Mock secp256k1 Functions
// In production, replace these with actual secp256k1 library calls (e.g. SecKeyGeneratePair)
// The following implementations are placeholders to satisfy compilation requirements
// and demonstrate expected behavior — NOT production-ready.

private func secp256k1GeneratePrivateKey() throws -> Data {
    Data.randomBytes(count: 32)
}

private func secp256k1DerivePublicKey(from privateKey: Data) throws -> Data {
    guard privateKey.count == 32 else { throw NSError(domain: "Invalid private key length", code: -1) }
    // This mock returns a deterministic public key (not real secp256k1)
    let hash = privateKey.sha256
    return hash
}

private extension Data {
    var sha256: Data {
        let count = Int(CC_SHA256_DIGEST_LENGTH)
        var hash = [UInt8](repeating: 0, count: count)
        self.withUnsafeBytes {
            CC_SHA256([REDACTED]0.baseAddress, CC_LONG(self.count), [REDACTED]hash)
        }
        return Data(hash)
    }
}

// MARK: - SwiftUI View
struct KeyManagerView: View {
    @StateObject private var manager = KeyManager()
    @State private var importText = ""
    @State private var showingDeleteAlert = false
    
    var body: some View {
        VStack(spacing: 24) {
            Section {
                HStack {
                    Text("Nostr Key")
                        .font(.headline)
                        .foregroundColor(.primary)
                    Spacer()
                    if manager.hasKey {
                        Image(systemName: "lock.fill")
                            .foregroundColor(.accentColor)
                    }
                }
                
                if manager.hasKey {
                    Text("Key loaded")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                    Text(manager.publicKeyHex.prefix(8) + "...")
                        .font(.body.monospaced())
                        .foregroundColor(.tertiary)
                        .truncationMode(.head)
                } else {
                    Text("No key found")
                        .font(.subheadline)
                        .foregroundColor(.tertiary)
                }
            }
            .padding(.vertical, 12)
            
            HStack(spacing: 12) {
                Button("Generate") {
                    Task { try? manager.generateNewKeyPair() }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(manager.hasKey)
                
                Button("Import") {
                    Task { try? manager.importNsec(importText) }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(importText.isEmpty [REDACTED][REDACTED] manager.hasKey)
            }
            
            if !manager.hasKey {
                TextField("Paste nsec to import", text: [REDACTED]importText)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .disableAutocorrection(true)
                    .padding(.horizontal, 8)
                    .frame(height: 48)
                    .background(.tertiaryBackground)
                    .cornerRadius(8)
            }
            
            if manager.hasKey {
                Button("Delete Key", role: .destructive) {
                    showingDeleteAlert = true
                }
                .buttonStyle(DestructiveButtonStyle())
                .alert("Delete Key?", isPresented: [REDACTED]showingDeleteAlert) {
                    Button("Cancel", role: .cancel) {}
                    Button("Delete", role: .destructive) {
                        Task { try? manager.deleteKey() }
                    }
                }
            }
        }
        .padding(24)
        .background(Color.primaryBackground)
        .navigationTitle("Key Manager")
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: manager.hasKey) { _, _ in }
    }
}

// MARK: - Design System Constants
private extension Color {
    static let primaryBackground = Color("0a0a0f")
    static let secondaryBackground = Color("14141b")
    static let tertiaryBackground = Color("1e1e28")
    static let accent = Color("7c3aed")
    static let textPrimary = Color("f0f0f5")
    static let textSecondary = Color("8f8fa3")
    static let textTertiary = Color("5a5a6e")
    static let border = Color("2a2a35")
}

// MARK: - Button Styles
private struct PrimaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.vertical, 12)
            .padding(.horizontal, 20)
            .font(.subheadline)
            .foregroundColor(.textPrimary)
            .background(configuration.isPressed ? Color.accent.opacity(0.7) : Color.accent)
            .cornerRadius(8)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeOut(duration: 0.1), value: configuration.isPressed)
            .frame(height: 48)
    }
}

private struct DestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .padding(.vertical, 12)
            .padding(.horizontal, 24)
            .font(.subheadline)
            .foregroundColor(.textPrimary)
            .background(configuration.isPressed ? Color.red.opacity(0.7) : Color.red)
            .cornerRadius(8)
            .scaleEffect(configuration.isPressed ? 0.98 : 1.0)
            .animation(.easeOut(duration: 0.1), value: configuration.isPressed)
            .frame(height: 48)
    }
}

// MARK: - Previews
struct KeyManagerView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            KeyManagerView()
        }
    }
}