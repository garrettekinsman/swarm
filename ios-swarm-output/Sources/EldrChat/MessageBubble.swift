import SwiftUI

struct MessageBubble: View {
    enum MessageDirection {
        case incoming, outgoing
    }

    let text: String
    let timestamp: Date
    let direction: MessageDirection

    var body: some View {
        HStack(alignment: .lastTextBaseline, spacing: 8) {
            if direction == .incoming {
                Spacer()
                bubbleContent
            } else {
                bubbleContent
                Spacer()
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 4)
    }

    @ViewBuilder
    private var bubbleContent: some View {
        VStack(alignment: direction == .incoming ? .leading : .trailing, spacing: 4) {
            Text(text)
                .font(.body)
                .foregroundColor(.primary)
                .lineLimit(0)
                .fixedSize(horizontal: false, vertical: true)

            timestampText
        }
        .padding(12)
        .background(
            direction == .outgoing ? Color(.sRGB, red: 124/255, green: 58/255, blue: 237/255) : Color(.sRGB, red: 26/255, green: 26/255, blue: 46/255)
        )
        .cornerRadius(16)
    }

    @ViewBuilder
    private var timestampText: some View {
        Text(timestamp, style: .timer)
            .font(.caption)
            .foregroundColor(.secondary)
            .minimumScaleFactor(0.7)
            .lineLimit(1)
            .frame(maxWidth: .infinity, alignment: direction == .incoming ? .leading : .trailing)
    }
}

// MARK: - Previews
#Preview {
    MessageBubble(text: "Hello, this is a secure message.", timestamp: Date(), direction: .outgoing)
        .background(Color(.sRGB, red: 10/255, green: 10/255, blue: 15/255))
}

#Preview {
    MessageBubble(text: "Incoming encrypted message received.", timestamp: Date().addingTimeInterval(-60), direction: .incoming)
        .background(Color(.sRGB, red: 10/255, green: 10/255, blue: 15/255))
}