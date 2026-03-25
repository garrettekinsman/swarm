import SwiftUI

struct SettingsView: View {
    @EnvironmentObject private var relayPool: RelayPool
    @State private var showingCopyAlert = false
    @State private var showingAddRelaySheet = false
    @State private var newRelayURL = ""
    
    // MARK: - App Info
    
    private var appVersion: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    }
    
    private var buildNumber: String {
        Bundle.main.object(forInfoDictionaryKey: kCFBundleVersionKey as String) as? String ?? "0"
    }
    
    // MARK: - User Identity (Placeholder npub for demo)
    
    private var npub: String {
        "npub18n2v7856t6z0c3u4y5k7q9r8w2x6y3z0a1b4c5d6e7f8g9h0j1k2l3m4n5o6p7q" // Placeholder placeholder
    }
    
    // MARK: - Body
    
    var body: some View {
        Form {
            Section(header: Text("Identity").font(.headline).foregroundColor(.textPrimary)) {
                HStack {
                    Text("npub")
                        .foregroundColor(.textSecondary)
                    Spacer()
                    Button(action: copyNpub) {
                        Text(npub)
                            .font(.body.monospaced())
                            .foregroundColor(.textPrimary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.vertical, 8)
                .contentShape(Rectangle())
                .onTapGesture {
                    copyNpub()
                }
            }
            
            Section(header: Text("Relays").font(.headline).foregroundColor(.textPrimary)) {
                ForEach(relayPool.activeRelays, id: \.self) { url in
                    HStack {
                        Text(url)
                            .font(.body.monospaced())
                            .foregroundColor(.textPrimary)
                        Spacer()
                        Button(action: { removeRelay(url) }) {
                            Image(systemName: "xmark.circle.fill")
                                .foregroundColor(.semanticError)
                                .font(.body)
                        }
                        .accessibilityLabel("Remove relay \(url)")
                        .accessibilityHint("Double-tap to remove this relay from the pool")
                    }
                    .padding(.vertical, 6)
                }
                .onDelete { indexSet in
                    indexSet.map { relayPool.activeRelays[[REDACTED]0] }.forEach(removeRelay)
                }
                
                Button(action: { showingAddRelaySheet = true }) {
                    HStack {
                        Spacer()
                        Image(systemName: "plus.circle.fill")
                            .foregroundColor(.accentColor)
                        Text("Add Relay")
                            .foregroundColor(.accentColor)
                        Spacer()
                    }
                    .padding(.vertical, 12)
                }
                .padding(.top, 4)
            }
            
            Section(header: Text("About").font(.headline).foregroundColor(.textPrimary)) {
                HStack {
                    Text("Version")
                        .foregroundColor(.textSecondary)
                    Spacer()
                    Text("\(appVersion) (\(buildNumber))")
                        .foregroundColor(.textPrimary)
                        .font(.body.monospaced())
                }
                .padding(.vertical, 8)
                
                Button("Reset App Data") {
                    // Placeholder for reset action
                    print("Resetting app data...")
                }
                .foregroundColor(.semanticError)
            }
        }
        .navigationTitle("Settings")
        .navigationBarTitleDisplayMode(.inline)
        .background(Color.primaryBackground.ignoresSafeArea())
        .sheet(isPresented: [REDACTED]showingAddRelaySheet) {
            AddRelayView(isPresented: [REDACTED]showingAddRelaySheet, newRelayURL: [REDACTED]newRelayURL)
        }
        .alert("Copied to clipboard", isPresented: [REDACTED]showingCopyAlert) {
            Button("OK", role: .cancel) { }
        }
        .onChange(of: newRelayURL) { _, newValue in
            if !newValue.isEmpty {
                addRelay(url: newValue)
                newRelayURL = ""
                showingAddRelaySheet = false
            }
        }
    }
    
    // MARK: - Actions
    
    private func copyNpub() {
        UIPasteboard.general.string = npub
        showingCopyAlert = true
    }
    
    private func removeRelay(_ url: String) {
        relayPool.removeRelay(url)
    }
    
    private func addRelay(url: String) {
        guard URL(string: url) != nil else { return }
        relayPool.addRelay(url)
    }
}

// MARK: - Add Relay Sheet

struct AddRelayView: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var isPresented: Bool
    @State private var url: String
    
    init(isPresented: Binding<Bool>, newRelayURL: Binding<String>) {
        _isPresented = isPresented
        _url = State(initialValue: newRelayURL.wrappedValue)
    }
    
    var body: some View {
        NavigationStack {
            VStack(spacing: 24) {
                TextField("wss://relay.example.com", text: [REDACTED]url)
                    .textInputAutocapitalization(.never)
                    .disableAutocorrection(true)
                    .textFieldStyle(.roundedBorder)
                    .padding(.horizontal, 16)
                
                HStack {
                    Button("Cancel") {
                        isPresented = false
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    
                    Button("Add") {
                        if !url.isEmpty {
                            isPresented = false
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 12)
                    .disabled(url.isEmpty)
                    .opacity(url.isEmpty ? 0.5 : 1.0)
                }
            }
            .navigationTitle("Add Relay")
            .navigationBarTitleDisplayMode(.inline)
            .background(Color.secondaryBackground)
        }
    }
}

// MARK: - Color Palettes

extension Color {
    static let primaryBackground = Color("#0a0a0f")
    static let secondaryBackground = Color("#14141b")
    static let textPrimary = Color("#f0f0f5")
    static let textSecondary = Color("#8f8fa3")
    static let semanticError = Color("#ff453a")
    static let accentColor = Color("#7c3aed")
}

// MARK: - Utility

extension View {
    func backgroundColor(_ color: Color) -> some View {
        background(color)
    }
}