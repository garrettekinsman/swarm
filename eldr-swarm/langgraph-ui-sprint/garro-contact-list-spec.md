# GARRO Contact List Design Spec

# EldrChat — Contact List (Column 1) Design Spec

---

## 1. Sidebar Dimensions & Constraints

```swift
NavigationSplitView(columnVisibility: $columnVisibility) {
    ContactListView(...)
        .navigationSplitViewColumnWidth(min: 260, ideal: 320, max: 400)
}
```

**iPad:** ideal 320px, collapses to overlay below 744px screen width  
**macOS:** min 260px, resizable to 400px, respects system sidebar resize handle  
**Background:** `#0D0D0D` — not `#1A1A1A`. The sidebar is the darkest layer. Content column steps up to `#1A1A1A`.

---

## 2. Contact Row Layout

```
┌─────────────────────────────────────────────────────────┐
│  [16]  [AVATAR 44px]  [12]  [TEXT BLOCK]  [8]  [META]  [16] │
└─────────────────────────────────────────────────────────┘
         Total row height: 72px
```

**Exact row anatomy:**

```swift
HStack(alignment: .top, spacing: 12) {
    // Avatar — 44×44
    AvatarView(pubkey: contact.pubkey)
        .frame(width: 44, height: 44)

    // Text block — fills remaining width
    VStack(alignment: .leading, spacing: 3) {
        HStack(alignment: .firstTextBaseline, spacing: 0) {
            Text(contact.displayName)        // primary name
                .lineLimit(1)
            Spacer()
            Text(timestamp)                  // relative time
                .lineLimit(1)
        }
        Text(lastMessagePreview)             // preview
            .lineLimit(2)
    }
}
.padding(.horizontal, 16)
.padding(.vertical, 14)
// Row height lands at 72px: 14 + 20 + 3 + 17×2 + 14 = 71px ≈ 72px grid snap
.frame(minHeight: 72)
```

**Why 72px?** 8px grid: 72 = 9×8. Avatar 44px vertically centered in 72px = 14px top/bottom padding. Clean.

---

## 3. Avatar Appearance

### Size
`44×44px` — exactly one touch target. `cornerRadius: 22` (circle).

### Fallback Construction (no profile picture)

```swift
struct AvatarView: View {
    let pubkey: String  // raw hex

    // Deterministic color from pubkey — pick hue from first 3 bytes
    private var avatarColor: Color {
        let hue = Double(pubkey.prefix(6)
            .unicodeScalars
            .reduce(0) { $0 + $1.value } % 360) / 360.0
        return Color(hue: hue, saturation: 0.45, brightness: 0.55)
    }

    // 2-char initials from npub truncation: first 4 hex chars → display as "3f·a1"
    private var initials: String {
        let p = pubkey
        guard p.count >= 4 else { return "??" }
        return String(p.prefix(2)).uppercased()
    }

    var body: some View {
        ZStack {
            Circle()
                .fill(avatarColor)
                .frame(width: 44, height: 44)

            Text(initials)
                .font(.system(size: 15, weight: .semibold, design: .monospaced))
                .foregroundStyle(.white.opacity(0.9))
        }
    }
}
```

**Deterministic color:** same pubkey = same avatar color across all sessions. No randomness.  
**No emoji fallback** — emoji renders inconsistently across macOS/iOS. Monospaced hex initials are clean and on-brand.

### Online Indicator Dot

```swift
// Overlay on AvatarView — bottom-right quadrant
.overlay(alignment: .bottomTrailing) {
    Circle()
        .fill(#0D0D0D)          // border matches sidebar bg — no hardcoded white ring
        .frame(width: 14, height: 14)
        .overlay(
            Circle()
                .fill(onlineColor)
                .frame(width: 10, height: 10)
        )
        // Position: offset so dot center sits at avatar edge
        .offset(x: 2, y: 2)
}
```

**Dot sizes:**
- Outer ring (bg punch-out): 14×14px
- Inner status dot: 10×10px
- Offset: x:2 y:2 (pushes into corner without clipping)

**Status colors:**
```
Online/connected:  #23A55A  (Green online token)
Away/idle:         #F0A500  (Amber warning token)  
Offline:           #949BA4  (Text muted — not a colored dot, just grey)
No data:           hidden entirely — don't show a dot if status unknown
```

---

## 4. Typography

```swift
// Contact display name — or truncated npub if no name
// Row title: line 1
.font(.system(size: 15, weight: .semibold))
.foregroundStyle(Color(hex: "#F5F5F7"))  // Text primary

// Timestamp — top right, same baseline as name
.font(.system(size: 12, weight: .regular))
.foregroundStyle(Color(hex: "#949BA4"))  // Text muted

// Last message preview — line 2
.font(.system(size: 13, weight: .regular))
.foregroundStyle(Color(hex: "#949BA4"))  // Text muted
// lineLimit(2) — max 2 lines, truncationMode: .tail

// Unread badge count (if unread > 0)
.font(.system(size: 11, weight: .bold))
.foregroundStyle(.white)
// Badge replaces timestamp when unread count > 0
```

**Npub truncation display format:**  
When no display name: `"npub1 3f7a…c91b"` — show `npub1` prefix + 4 chars + ellipsis + 4 chars.

```swift
private func displayName(_ pubkey: String) -> String {
    guard pubkey.count >= 8 else { return pubkey }
    let short = "\(pubkey.prefix(4))…\(pubkey.suffix(4))"
    return "npub1 \(short)"
}
```

---

## 5. Color Usage

### Background Layers
```
Sidebar column bg:          #0D0D0D   ← darkest
Row default:                #0D0D0D   ← same, no stripe
Row hover (macOS pointer):  #1A1A1A   ← Surface, +1 elevation
Row selected (active):      #2C2C2E   ← Surface raised, +2 elevation
Row selected bg accent:     5865F2 at 15% opacity over #2C2C2E
```

```swift
// Selected row implementation
.listRowBackground(
    isSelected
        ? Color(hex: "#2C2C2E").overlay(Color(hex: "#5865F2").opacity(0.15))
        : Color(hex: "#0D0D0D")
)
```

### Separators
```swift
// NO default List separators — they add visual noise
.listStyle(.plain)
// Implicit separation comes from 72px row rhythm alone
// If you need a separator: 1px line at #2C2C2E, inset left 72px (avatar width + padding)
Divider()
    .background(Color(hex: "#2C2C2E"))
    .padding(.leading, 72)  // 16 padding + 44 avatar + 12 gap
```

### Unread Badge
```swift
ZStack {
    Capsule()
        .fill(Color(hex: "#5865F2"))  // Blurple CTA
        .frame(height: 18)
    Text("\(unreadCount)")
        .font(.system(size: 11, weight: .bold))
        .foregroundStyle(.white)
        .padding(.horizontal, 6)
}
.frame(minWidth: 18)
```

---

## 6. Empty State Design

```swift
private var emptyState: some View {
    VStack(spacing: 0) {
        Spacer()

        VStack(spacing: 16) {
            Image(systemName: "lock.shield")
                .font(.system(size: 48, weight: .ultraLight))
                .foregroundStyle(Color(hex: "#2C2C2E"))
                .symbolRenderingMode(.hierarchical)

            VStack(spacing: 6) {
                Text("No conversations")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundStyle(Color(hex: "#F5F5F7"))

                Text("Add a contact by their\nnpub or public key.")
                    .font(.system(size: 13, weight: .regular))
                    .foregroundStyle(Color(hex: "#949BA4"))
                    .multilineTextAlignment(.center)
                    .lineSpacing(2)
            }

            Button(action: { /* show add contact sheet */ }) {
                Label("Add Contact", systemImage: "plus")
                    .font(.system(size: 14, weight: .semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(Color(hex: "#5865F2"))
                    .clipShape(RoundedRectangle(cornerRadius: 8))
            }
            .buttonStyle(.plain)
        }
        .padding(32)

        Spacer()
    }
    .frame(maxWidth: .infinity, maxHeight: .infinity)
    .background(Color(hex: "#0D0D0D"))
}
```

**Grid check:** Icon 48px → not grid-aligned (acceptable for icon size). VStack spacing 16px = 2×8. Padding 32px = 4×8. Button padding 10px vertical → round to 8px or 12px in final impl — use 12px.

---

## 7. Header: Search + Title

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  EldrChat                              [+]  [···]       │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │  🔍  Search conversations...                    │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

```swift
.toolbar {
    ToolbarItem(placement: .navigationBarLeading) {
        Text("EldrChat")
            .font(.system(size: 20, weight: .bold))
            .foregroundStyle(Color(hex: "#F5F5F7"))
    }
    ToolbarItem(placement: .navigationBarTrailing) {
        HStack(spacing: 8) {
            Button(action: { /* add contact */ }) {
                Image(systemName: "square.and.pencil")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(Color(hex: "#5865F2"))
            }
            .frame(width: 44, height: 44)  // iPad touch target
        }
    }
}
.searchable(
    text: $searchText,
    placement: .sidebar,          // pins search to top of sidebar
    prompt: "Search conversations"
)
```

**Search bar:**  
Use `.searchable()` with `placement: .sidebar`. This renders natively correct on both iPad and