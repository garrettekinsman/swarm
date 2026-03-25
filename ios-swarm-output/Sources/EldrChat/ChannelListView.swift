import SwiftUI

// MARK: - ChannelListView
/// EldrChat Sidebar: Channel List
/// Maintains state for search, selection, and channel list rendering.
/// Pulls from MessageStore for channel metadata and last message.
struct ChannelListView: View {
    @ObservedObject var store: MessageStore
    
    @State private var searchQuery: String = ""
    
    // GARRO Design: 4pt grid[REDACTED] all margins/padding multiples of 4
    private let gridUnit: CGFloat = 4
    private let cornerRadius: CGFloat = 8
    private let avatarSize: CGFloat = 40
    private let headerHeight: CGFloat = 56
    
    var filteredChannels: [Conversation] {
        guard !searchQuery.isEmpty else { return store.conversations.sorted(by: { [REDACTED]0.timestamp > [REDACTED]1.timestamp }) }
        let lower = searchQuery.lowercased()
        return store.conversations.filter { [REDACTED]0.title.lowercased().contains(lower) [REDACTED][REDACTED] ([REDACTED]0.participants.first?.name.lowercased().contains(lower) == true) }.sorted(by: { [REDACTED]0.timestamp > [REDACTED]1.timestamp })
    }
    
    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            channelList
        }
        .background(Color(hex: 0x0a0a0f)) // #0a0a0f — void background
        .environmentObject(store)
    }
    
    private var header: some View {
        VStack(spacing: 0) {
            HStack(spacing: 2 * gridUnit) {
                Text("EldrChat")
                    .font(.headline)
                    .foregroundColor(Color(hex: 0xf0f0f5)) // #f0f0f5 — primary text
                    .padding(.top, gridUnit * 2)
                Spacer()
                Button(action: { /* TODO: Settings */ }) {
                    Image(systemName: "gearshape") // Placeholder icon
                        .font(.body)
                        .foregroundColor(Color(hex: 0xf0f0f5))
                        .frame(width: 20, height: 20)
                }
                .padding(.top, gridUnit * 2)
            }
            .padding(.horizontal, 4 * gridUnit)
            .padding(.bottom, 2 * gridUnit)
            
            HStack {
                Text("Conversations")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundColor(Color(hex: 0x8f8fa3)) // #8f8fa3 — secondary text
                    .padding(.leading, 2 * gridUnit)
            }
            .padding(.bottom, gridUnit * 2)
        }
        .background(Color(hex: 0x14141b)) // #14141b — secondary background
    }
    
    private var channelList: some View {
        ZStack {
            List {
                ForEach(filteredChannels) { conversation in
                    ConversationRow(conversation: conversation)
                        .listRowBackground(Color.clear)
                        .listRowSeparatorColor(Color.clear)
                        .listRowInsets(EdgeInsets())
                }
                .listRowSpacing(0)
            }
            .listStyle(.sidebar)
            .background(Color.clear)
            
            if store.conversations.isEmpty {
                emptyState
            }
        }
        .background(Color(hex: 0x0a0a0f))
    }
    
    private var emptyState: some View {
        VStack(spacing: 2 * gridUnit) {
            Image(systemName: "envelope.open") // Placeholder icon
                .font(.title2)
                .foregroundColor(Color(hex: 0x5a5a6e)) // #5a5a6e — tertiary text
                .frame(width: avatarSize, height: avatarSize)
                .background(Color(hex: 0x1e1e28)) // #1e1e28 — tertiary background
                .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
                .shadow(radius: gridUnit * 2)
            
            Text("No conversations yet")
                .font(.subheadline)
                .foregroundColor(Color(hex: 0xf0f0f5))
            
            Button(action: { /* TODO: Add contact */ }) {
                Text("Add Contact")
                    .font(.body)
                    .foregroundColor(Color(hex: 0x7c3aed)) // #7c3aed — violet
                    .padding(.horizontal, 3 * gridUnit)
                    .padding(.vertical, 2 * gridUnit)
            }
            .buttonStyle(PlainButtonStyle())
        }
        .padding(.vertical, 2 * gridUnit)
    }
}

// MARK: - ConversationRow
/// One row in the sidebar channel/contact list.
/// Displays contact avatar, name, last message preview, and timestamp.
struct ConversationRow: View {
    let conversation: Conversation
    
    private let gridUnit: CGFloat = 4
    private let cornerRadius: CGFloat = 8
    private let avatarSize: CGFloat = 40
    
    var body: some View {
        HStack(spacing: 2 * gridUnit) {
            avatar
            content
            Spacer()
            metadata
        }
        .padding(.horizontal, 2 * gridUnit)
        .padding(.vertical, 2 * gridUnit)
        .frame(height: avatarSize)
        .contentShape(RoundedRectangle(cornerRadius: cornerRadius))
        .onTapGesture {
            conversation.markAsRead()
        }
    }
    
    private var avatar: some View {
        Image(conversation.participants.first?.avatar ?? "user-circle") // Fallback
            .resizable()
            .scaledToFill()
            .frame(width: avatarSize - gridUnit * 2, height: avatarSize - gridUnit * 2)
            .clipShape(RoundedRectangle(cornerRadius: cornerRadius))
            .background(Color(hex: 0x1e1e28))
            .shadow(radius: gridUnit)
    }
    
    private var content: some View {
        VStack(alignment: .leading, spacing: gridUnit) {
            Text(conversation.title)
                .font(.body)
                .fontWeight(.semibold)
                .foregroundColor(Color(hex: 0xf0f0f5))
                .lineLimit(1)
            Text(conversation.lastMessageText ?? "Start a message")
                .font(.caption)
                .foregroundColor(Color(hex: 0x8f8fa3))
                .lineLimit(1)
        }
    }
    
    private var metadata: some View {
        VStack(spacing: gridUnit) {
            Text(conversation.timestamp, style: .time)
                .font(.caption)
                .foregroundColor(
                    conversation.unreadCount > 0 ? Color(hex: 0x7c3aed) : Color(hex: 0xf0f0f5)
                )
            if conversation.unreadCount > 0 {
                Text("\(conversation.unreadCount)")
                    .font(.caption)
                    .foregroundColor(Color(hex: 0x7c3aed))
                    .fontWeight(.bold)
                    .padding(.horizontal, gridUnit)
                    .padding(.vertical, gridUnit * 0)
                    .background(Color(hex: 0x1e1e28))
                    .clipShape(Circle())
            }
        }
        .frame(width: 50)
        .frame(height: avatarSize)
    }
}

// MARK: - Conversation
/// Represents one conversation/thread
struct Conversation: Identifiable {
    let id: String
    let title: String
    let timestamp: Date
    let lastMessageText: String?
    let unreadCount: Int
    
    var participants: [User] {
        [User(name: title, avatar: id)] // Simplified
    }
}

struct User: Identifiable {
    let id: String
    let name: String
    let avatar: String
}

// MARK: - MessageStore
/// Mock store pulling conversations
@MainActor
class MessageStore: ObservableObject {
    @Published var conversations: [Conversation]
    
    init() {
        // Placeholder data — *only* used if caller doesn't inject mock
        self.conversations = [
            Conversation(id: "1", title: "General", timestamp: .now, lastMessageText: "Hello, world", unreadCount: 2)
        ]
    }
}