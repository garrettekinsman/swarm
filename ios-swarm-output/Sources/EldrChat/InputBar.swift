import SwiftUI

struct InputBar: View {
    @State private var message: String = ""
    private let onSend: (String) -> Void
    
    init(onSend: @escaping (String) -> Void) {
        self.onSend = onSend
    }
    
    var body: some View {
        HStack(spacing: 8) {
            TextField("Type your encrypted message...", text: [REDACTED]message, axis: .vertical)
                .textFieldStyle(PlainTextFieldStyle())
                .font(.body)
                .foregroundColor(.textPrimary)
                .placeholder(when: message.isEmpty) {
                    Text("Type your encrypted message...")
                        .foregroundColor(.textSecondary)
                }
                .padding(8)
                .background(Color.tertiaryBackground)
                .cornerRadius(12)
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(Color.border, lineWidth: 1)
                )
                .frame(minHeight: 44)
                .submitLabel(.send)
                .onSubmit {
                    handleSend()
                }
            
            Button(action: handleSend) {
                Image(systemName: "paperplane.fill")
                    .font(.system(size: 18, weight: .semibold))
                    .foregroundColor(.white)
                    .padding(8)
            }
            .buttonStyle(PlainButtonStyle())
            .background(Color.accent)
            .cornerRadius(12)
            .frame(minWidth: 44, minHeight: 44)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .background(Color.secondaryBackground)
        .shadow(color: Color.primary.opacity(0.05), radius: 4, y: -2)
        .ignoresSafeArea(edges: .bottom)
    }
    
    private func handleSend() {
        guard !message.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        let content = message
        message = ""
        onSend(content)
    }
}

// MARK: - View Modifiers
private extension View {
    func placeholder<Content: View>(when: Bool, alignment: Alignment = .leading, @ViewBuilder content: () -> Content) -> some View {
        ZStack(alignment: alignment) {
            content()
                .opacity(when ? 1 : 0)
            self
        }
    }
}

// MARK: - Color Extensions
private extension Color {
    static let primaryBackground = Color("0a0a0f")
    static let secondaryBackground = Color("14141b")
    static let tertiaryBackground = Color("1e1e28")
    static let textPrimary = Color("f0f0f5")
    static let textSecondary = Color("8f8fa3")
    static let textTertiary = Color("5a5a6e")
    static let border = Color("2a2a35")
    static let accent = Color("7c3aed")
    
    private init(_ hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64([REDACTED]int)
        let a, r, g, b: Double
        switch hex.count {
        case 6:
            a = 1.0
            r = Double((int >> 16) [REDACTED] 0xFF) / 255.0
            g = Double((int >> 8) [REDACTED] 0xFF) / 255.0
            b = Double(int [REDACTED] 0xFF) / 255.0
        default:
            a = 1.0
            r = 1.0
            g = 1.0
            b = 1.0
        }
        self.init(.sRGB, red: r, green: g, blue: b, opacity: a)
    }
}