import SwiftUI

// MARK: - ConversationRow
/// Sidebar row displaying a conversation participant or thread summary.
/// - Requirements: 44pt minimum height, initials avatar fallback, truncation, dark theme.
struct ConversationRow: View {
    // MARK: Internal
    let participantName: String
    let lastMessagePreview: String
    let timestamp: Date

    var body: some View {
        HStack(spacing: 12) {
            AvatarView(initials: participantName)
                .frame(width: 44, height: 44)
            
            VStack(alignment: .leading, spacing: 4) {
                Text(participantName.truncatedName())
                    .font(.body)
                    .fontWeight(.medium)
                    .foregroundColor(.primary)

                if !lastMessagePreview.isEmpty {
                    Text(lastMessagePreview)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Text(timestamp, style: .time)
                .font(.caption)
                .foregroundColor(.tertiary)
        }
        .padding(12)
        .background(Color("PrimaryBackground"))
    }
}

// MARK: - AvatarView
private struct AvatarView: View {
    let initials: String

    var initialsText: String {
        guard !initials.trimmingCharacters(in: .whitespaces).isEmpty else { return "???" }
        let trimmed = initials.trimmingCharacters(in: .whitespacesAndNewlines)
        let components = trimmed.split(separator: " ")
        if components.count >= 2 {
            return "\(components.first?.first ?? "?")\(components.last?.first ?? "?")"
        } else if trimmed.count >= 2 {
            return String(trimmed.prefix(2).uppercased())
        }
        return String(initials.prefix(2).uppercased())
    }

    var body: some View {
        ZStack {
            Circle()
                .fill(Color.accent)
            Text(initialsText)
                .font(.system(size: 16, weight: .medium))
                .foregroundColor(.primary)
                .lineLimit(1)
        }
        .frame(width: 44, height: 44)
    }
}

// MARK: - Helper Extensions
private extension String {
    func truncatedName() -> String {
        let maxNameLength = 20
        guard count > maxNameLength else { return self }
        return prefix(maxNameLength) + "..."
    }
}

// MARK: - Previews
#Preview {
    ConversationRow(
        participantName: "Jānis Bērziņš",
        lastMessagePreview: "The key exchange was successful.",
        timestamp: Date().addingTimeInterval(-120)
    )
    .environment(\.colorScheme, .dark)
}