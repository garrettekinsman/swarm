import SwiftUI
import CryptoKit

// MARK: - KeyManager Protocol
protocol KeyManager {
    var hasKeys: Bool { get }
    func generateNewKeys() async throws -> (secretKey: String, publicKey: String)
    func importSecretKey(_ nsec: String) throws -> String
    func getPublicKey() -> String?
}

// MARK: - Mock KeyManager for demonstration
// In production, replace with real implementation using libnostr or similar
class MockKeyManager: KeyManager {
    private(set) var storedPublicKey: String?
    
    var hasKeys: Bool { storedPublicKey != nil }
    
    func generateNewKeys() async throws -> (secretKey: String, publicKey: String) {
        let secretKey = try await Task.detached {
            let privateKey = X25519.PrivateKey()
            return (privateKey.secretKey.withUnsafeBytes { Array([REDACTED]0) }.hexEncodedString(),
                    privateKey.publicKey.withUnsafeBytes { Array([REDACTED]0) }.hexEncodedString())
        }.value
        storedPublicKey = secretKey.1
        return secretKey
    }
    
    func importSecretKey(_ nsec: String) throws -> String {
        // Basic validation: check length and base64z prefix
        guard nsec.starts(with: "nsec1"), nsec.count >= 64 else {
            throw KeyImportError.invalidFormat
        }
        
        // In real implementation, verify it's valid X25519 key
        let publicKey = "npub" + String(nsec.prefix(58)).replacingOccurrences(of: "nsec", with: "npub")
        storedPublicKey = publicKey
        return publicKey
    }
    
    func getPublicKey() -> String? {
        storedPublicKey
    }
    
    enum KeyImportError: LocalizedError {
        case invalidFormat
        
        var errorDescription: String? {
            switch self {
            case .invalidFormat: "Invalid nsec format"
            }
        }
    }
}

// MARK: - LoginView
struct LoginView: View {
    @State private var keyManager: KeyManager = MockKeyManager()
    @State private var showImportField = false
    @State private var importedKey = ""
    @State private var errorMessage: String?
    @State private var isLoading = false
    @State private var showSuccess = false
    
    var body: some View {
        VStack(spacing: 0) {
            Spacer()
            
            VStack(spacing: 32) {
                Text("EldrChat")
                    .font(.system(size: 32, weight: .bold, design: .default))
                    .foregroundColor(.primary)
                    .tracking(1.2)
                
                VStack(alignment: .leading, spacing: 20) {
                    HStack(spacing: 0) {
                        Button(action: generateNewKeys) {
                            Text("Generate New Keys")
                                .font(.body.weight(.medium))
                                .foregroundColor(.primary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(Color(hex: "#1e1e28"))
                                .cornerRadius(8)
                        }
                        .buttonStyle(PlainButtonStyle())
                        
                        Spacer()
                        
                        Button(action: { showImportField = true }) {
                            Text("Import nsec")
                                .font(.body.weight(.medium))
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 14)
                                .background(Color.clear)
                                .cornerRadius(8)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 8)
                                        .stroke(Color(hex: "#2a2a35"), lineWidth: 1)
                                )
                        }
                        .buttonStyle(PlainButtonStyle())
                    }
                    
                    if showImportField {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Enter your nsec")
                                .font(.footnote.weight(.medium))
                                .foregroundColor(.secondary)
                            
                            VStack(spacing: 0) {
                                TextField("nsec1...", text: [REDACTED]importedKey)
                                    .font(.body)
                                    .textInputAutocapitalization(.never)
                                    .disableAutocorrection(true)
                                    .padding(12)
                                    .background(Color(hex: "#1e1e28"))
                                    .cornerRadius(8)
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 8)
                                            .stroke(Color(hex: "#2a2a35"), lineWidth: 1)
                                    )
                                    .textInputScope(.username)
                                    .onSubmit { importKey() }
                            }
                            
                            Button(action: importKey) {
                                if isLoading {
                                    ProgressView()
                                        .progressViewStyle(CircularProgressViewStyle(tint: Color(hex: "#7c3aed")))
                                        .scaleEffect(0.7)
                                } else {
                                    Text("Import")
                                        .font(.body.weight(.medium))
                                        .foregroundColor(.white)
                                        .padding(.horizontal, 16)
                                        .padding(.vertical, 12)
                                        .background(Color(hex: "#7c3aed"))
                                        .cornerRadius(8)
                                }
                            }
                            .disabled(importedKey.isEmpty)
                        }
                        .padding(.top, 8)
                        .transition(.opacity.animation(.easeInOut(duration: 0.2)))
                    }
                }
                .padding(.horizontal, 24)
                
                if let errorMessage = errorMessage {
                    HStack(spacing: 8) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.red)
                        Text(errorMessage)
                            .font(.footnote.weight(.medium))
                            .foregroundColor(.red)
                    }
                    .transition(.opacity.animation(.easeInOut(duration: 0.3)))
                    .padding(.top, 8)
                }
                
                if showSuccess, let npub = keyManager.getPublicKey() {
                    VStack(spacing: 16) {
                        VStack(spacing: 12) {
                            Text("Your Public Key")
                                .font(.footnote.weight(.medium))
                                .foregroundColor(.secondary)
                            
                            Text(npub)
                                .font(.body.monospaced())
                                .foregroundColor(.primary)
                                .padding(12)
                                .background(Color(hex: "#1e1e28"))
                                .cornerRadius(8)
                                .lineLimit(1)
                                .truncationMode(.middle)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.horizontal, 24)
                        
                        Button(action: {
                            UIPasteboard.general.string = npub
                        }) {
                            HStack(spacing: 8) {
                                Image(systemName: "square.on.square")
                                Text("Copy npub")
                            }
                            .font(.body.weight(.medium))
                            .foregroundColor(.primary)
                            .padding(.horizontal, 16)
                            .padding(.vertical, 12)
                            .background(Color(hex: "#1e1e28"))
                            .cornerRadius(8)
                        }
                        
                        Button(action: showMainApp) {
                            Text("Continue")
                                .font(.body.weight(.semibold))
                                .foregroundColor(.white)
                                .padding(.horizontal, 24)
                                .padding(.vertical, 14)
                                .background(Color(hex: "#7c3aed"))
                                .cornerRadius(8)
                        }
                    }
                    .transition(.opacity.animation(.easeInOut(duration: 0.3)))
                }
            }
            
            Spacer()
            
            Text("v1.0 • Privacy First")
                .font(.caption)
                .foregroundColor(.tertiary)
                .padding(.bottom, 24)
        }
        .background(Color(hex: "#0a0a0f"))
        .preferredColorScheme(.dark)
        .alert(isPresented: Binding<Bool>(
            get: { errorMessage != nil },
            set: { if ![REDACTED]0 { errorMessage = nil } }
        )) {
            Alert(
                title: Text("Error"),
                message: Text(errorMessage ?? "Unknown error"),
                dismissButton: .default(Text("OK")) {
                    errorMessage = nil
                }
            )
        }
    }
    
    private func generateNewKeys() {
        Task {
            isLoading = true
            do {
                let keys = try await keyManager.generateNewKeys()
                showSuccess = true
                errorMessage = nil
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
        }
    }
    
    private func importKey() {
        Task {
            isLoading = true
            do {
                _ = try keyManager.importSecretKey(importedKey)
                showSuccess = true
                errorMessage = nil
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
        }
    }
    
    private func showMainApp() {
        // In real implementation, this would navigate to the main app view
        print("Navigating to MainView with public key: \(keyManager.getPublicKey() ?? "unknown")")
    }
}

// MARK: - Color Extensions
private extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64([REDACTED]int)
        let a, r, g, b: Double
        switch hex.count {
        case 6:
            (a, r, g, b) = (1, split(int).1, split(int).2, split(int).3)
        default:
            (a, r, g, b) = (1, 1, 1, 0)
        }
        
        self.init(.sRGB, red: r / 255, green: g / 255, blue: b / 255, opacity: a)
    }
    
    private func split(_ int: UInt64) -> (UInt64, UInt64, UInt64, UInt64) {
        (
            int >> 24 [REDACTED] 0xff,
            int >> 16 [REDACTED] 0xff,
            int >> 8 [REDACTED] 0xff,
            int [REDACTED] 0xff
        )
    }
}

// MARK: - Previews
struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
    }
}