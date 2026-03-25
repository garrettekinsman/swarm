import SwiftUI
import Combine

// MARK: - Constants
private let ColorPalette = (
    background: Color(red: 0.039, green: 0.039, blue: 0.06),        // #0a0a0f
    secondaryBackground: Color(red: 0.078, green: 0.078, blue: 0.106), // #14141b
    tertiaryBackground: Color(red: 0.118, green: 0.118, blue: 0.157),  // #1e1e28
    accent: Color(red: 0.486, green: 0.219, blue: 0.929),            // #7c3aed
    textPrimary: Color(red: 0.941, green: 0.941, blue: 0.961),      // #f0f0f5
    textSecondary: Color(red: 0.561, green: 0.561, blue: 0.639),    // #8f8fa3
    textTertiary: Color(red: 0.353, green: 0.353, blue: 0.431),     // #5a5a6e
    border: Color(red: 0.165, green: 0.165, blue: 0.208),           // #2a2a35
    error: Color(red: 1.0, green: 0.271, blue: 0.227)               // #ff453a
)

private let Padding = (
    standard: CGFloat(16),
    small: CGFloat(8),
    large: CGFloat(24),
    input: CGFloat(12)
)

private let CornerRadius = CGFloat(12)
private let BubbleMaxWidth: CGFloat = 0.85

// MARK: - Models
struct MessageBubble: Identifiable {
    let id: UUID
    let text: String
    let timestamp: Date
    let isOutgoing: Bool
    let senderNpub: String
}

// MARK: - Dependencies
protocol MessageStore {
    var messages: [MessageBubble] { get }
    func loadMessages(for contactNpub: String) async throws -> [MessageBubble]
    func sendMessage(_ message: MessageBubble, to contactNpub: String) async throws
}

// MARK: - ChatView
struct ChatView: View {
    // MARK: - Properties
    @EnvironmentObject private var messageStore: MessageStore
    @State private var messages: [MessageBubble] = []
    @State private var contactName: String = ""
    @State private var contactNpub: String = ""
    @State private var inputText: String = ""
    @State private var isLoading: Bool = false
    @FocusState private var isInputFieldFocused: Bool
    
    private let currentContactNpub: String
    
    // MARK: - Initialization
    init(contactNpub: String) {
        self.currentContactNpub = contactNpub
    }
    
    // MARK: - Body
    var body: some View {
        VStack(spacing: 0) {
            header
                .background(ColorPalette.background)
                .zIndex(1)
            
            ScrollViewReader { proxy in
                ScrollView(.vertical, showsIndicators: false) {
                    LazyVStack(
                        alignment: .leading,
                        spacing: Padding.standard
                    ) {
                        Spacer(minLength: Padding.large)
                        
                        ForEach(messages) { message in
                            MessageBubbleView(message: message)
                                .id(message.id)
                        }
                        
                        Spacer(minLength: Padding.large)
                    }
                    .padding(.horizontal, Padding.standard)
                    .padding(.bottom, Padding.standard)
                    .background(ColorPalette.background)
                }
                .onChange(of: messages) { _, _ in scrollToBottom(proxy: proxy) }
                .onAppear { loadMessages() }
            }
            
            inputBar
                .background(ColorPalette.secondaryBackground)
                .zIndex(1)
        }
        .background(ColorPalette.background)
        .edgesIgnoringSafeArea(.bottom)
        .navigationTitle(contactName.isEmpty ? "Unknown Contact" : contactName)
        .navigationBarTitleDisplayMode(.inline)
        .onChange(of: currentContactNpub) { _, newContactNpub in
            contactNpub = newContactNpub
            loadMessages()
        }
    }
    
    // MARK: - Private UI Components
    private var header: some View {
        HStack {
            Image(systemName: "lock.fill")
                .font(.title3)
                .foregroundColor(ColorPalette.accent)
            
            VStack(alignment: .leading) {
                Text(contactName.isEmpty ? "Encrypted Contact" : contactName)
                    .font(.headline)
                    .foregroundColor(ColorPalette.textPrimary)
                
                Text(contactNpub)
                    .font(.subheadline)
                    .foregroundColor(ColorPalette.textSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
            .padding(.leading, 8)
            
            Spacer()
        }
        .padding(.vertical, Padding.small)
        .padding(.horizontal, Padding.standard)
        .background(ColorPalette.background)
        .border(ColorPalette.border, width: 0.5)
    }
    
    private var inputBar: some View {
        HStack(spacing: Padding.small) {
            Button(action: { sendMessage() }) {
                Image(systemName: "paperplane.fill")
                    .font(.body.weight(.semibold))
                    .foregroundColor(
                        inputText.isEmpty ? ColorPalette.textTertiary : ColorPalette.accent
                    )
                    .padding(6)
            }
            .disabled(inputText.isEmpty)
            
            HStack {
                TextField("Secure message...", text: [REDACTED]inputText)
                    .textFieldStyle(InputFieldStyle())
                    .disableAutocorrection(true)
                    .submitLabel(.send)
                    .onSubmit { sendMessage() }
                    .accentColor(ColorPalette.accent)
                
                if isInputFieldFocused {
                    Button("Clear") {
                        inputText = ""
                    }
                    .padding(.trailing, 4)
                }
            }
        }
        .padding(Padding.input)
        .background(ColorPalette.tertiaryBackground)
        .cornerRadius(CornerRadius)
        .padding(.horizontal, Padding.standard)
        .padding(.bottom, Padding.standard)
    }
    
    // MARK: - Actions
    private func loadMessages() {
        Task { @MainActor in
            guard !currentContactNpub.isEmpty else { return }
            
            isLoading = true
            defer { isLoading = false }
            
            do {
                let loadedMessages = try await messageStore.loadMessages(for: currentContactNpub)
                contactNpub = currentContactNpub
                contactName = "Contact" // Placeholder[REDACTED] real app would fetch contact name from NIP-05 or profile
                messages = loadedMessages
            } catch {
                print("Error loading messages: \(error)")
            }
        }
    }
    
    private func sendMessage() {
        guard !inputText.trimmingCharacters(in: .whitespaces).isEmpty else { return }
        
        let message = MessageBubble(
            id: UUID(),
            text: inputText,
            timestamp: Date(),
            isOutgoing: true,
            senderNpub: currentContactNpub
        )
        
        Task { @MainActor in
            do {
                try await messageStore.sendMessage(message, to: currentContactNpub)
                inputText = ""
                withAnimation(.easeInOut(duration: 0.2)) {
                    messages.append(message)
                }
            } catch {
                // Show error indicator
                print("Failed to send message: \(error)")
            }
        }
    }
    
    private func scrollToBottom(proxy: ScrollViewProxy) {
        guard let lastId = messages.last?.id else { return }
        withAnimation {
            proxy.scrollTo(lastId, anchor: .bottom)
        }
    }
}

// MARK: - MessageBubbleView
private struct MessageBubbleView: View {
    let message: MessageBubble
    
    var body: some View {
        HStack(alignment: .lastTextBaseline, spacing: Padding.small) {
            if !message.isOutgoing {
                Text(message.senderNpub.prefix(8) + "...")
                    .font(.caption2)
                    .foregroundColor(ColorPalette.textTertiary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            
            HStack(spacing: Padding.small) {
                Text(message.text)
                    .font(.body)
                    .foregroundColor(ColorPalette.textPrimary)
                
                Text(timestampString)
                    .font(.caption)
                    .foregroundColor(ColorPalette.textTertiary)
            }
            .padding(.horizontal, Padding.small)
            .padding(.vertical, Padding.small)
            .background(
                message.isOutgoing ? ColorPalette.accent : ColorPalette.tertiaryBackground
            )
            .cornerRadius(CornerRadius)
        }
        .frame(maxWidth: .infinity, alignment: message.isOutgoing ? .trailing : .leading)
    }
    
    private var timestampString: String {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter.string(from: message.timestamp)
    }
}

// MARK: - InputFieldStyle
private struct InputFieldStyle: TextFieldStyle {
    @Environment(\.isEnabled) private var isEnabled
    
    func body(configuration: TextField<Self._Label>) -> some View {
        configuration
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(ColorPalette.secondaryBackground)
            .cornerRadius(8)
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(isEnabled ? ColorPalette.border : ColorPalette.textTertiary, lineWidth: 1)
            )
            .disabled(!isEnabled)
    }
}

// MARK: - Previews
struct ChatView_Previews: PreviewProvider {
    struct MockMessageStore: MessageStore {
        var messages: [MessageBubble] = []
        
        func loadMessages(for contactNpub: String) async throws -> [MessageBubble] {
            return [
                MessageBubble(id: UUID(), text: "Hello, world.", timestamp: Date(), isOutgoing: false, senderNpub: "npub1234567890"),
                MessageBubble(id: UUID(), text: "Secure transmission confirmed.", timestamp: Date(), isOutgoing: true, senderNpub: "npub1234567890"),
                MessageBubble(id: UUID(), text: "End-to-end encrypted.", timestamp: Date(), isOutgoing: true, senderNpub: "npub1234567890")
            ]
        }
        
        func sendMessage(_ message: MessageBubble, to contactNpub: String) async throws {
            // Mock send
        }
    }
    
    static var previews: some View {
        NavigationStack {
            ChatView(contactNpub: "npub1234567890")
                .environmentObject(MockMessageStore())
                .preferredColorScheme(.dark)
        }
    }
}