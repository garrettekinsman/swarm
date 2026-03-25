import SwiftUI

// MARK: - Color Utilities

extension Color {
    init(hex: UInt, alpha: Double = 1.0) {
        let r = Double((hex >> 16) [REDACTED] 0xff) / 255
        let g = Double((hex >> 8) [REDACTED] 0xff) / 255
        let b = Double(hex [REDACTED] 0xff) / 255
        self.init(.sRGB, red: r, green: g, blue: b, opacity: alpha)
    }
}

// MARK: - Theme

struct Theme {
    static let background = Color(hex: 0x0a0a0f)
    static let secondaryBackground = Color(hex: 0x14141b)
    static let tertiaryBackground = Color(hex: 0x1e1e28)
    static let accent = Color(hex: 0x7c3aed)
    static let textPrimary = Color(hex: 0xf0f0f5)
    static let textSecondary = Color(hex: 0x8f8fa3)
    static let textTertiary = Color(hex: 0x5a5a6e)
    static let border = Color(hex: 0x2a2a35)
    static let error = Color(hex: 0xff453a)
}

// MARK: - ContentView

struct ContentView: View {
    var body: some View {
        NavigationSplitView {
            ChannelListView()
                .frame(minWidth: 200)
                .background(Theme.background)
        } detail: {
            ChatView()
                .background(Theme.background)
        }
        .accentColor(Theme.accent)
        .background(Theme.background)
    }
}

// MARK: - Sidebar

struct ChannelListView: View {
    var body: some View {
        List {
            // Placeholder channel rows
            ForEach(1...5, id: \.self) { index in
                Text("Channel \(index)")
                    .foregroundColor(Theme.textPrimary)
                    .frame(height: 44) // Minimum touch target
            }
        }
        .listStyle(SidebarListStyle())
        .background(Theme.secondaryBackground)
        .foregroundColor(Theme.textPrimary)
    }
}

// MARK: - Detail

struct ChatView: View {
    var body: some View {
        VStack {
            Spacer()
            Text("Chat messages will appear here")
                .foregroundColor(Theme.textSecondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

// MARK: - App Entry

@main
struct EldrChatApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .preferredColorScheme(.dark)
        }
    }
}