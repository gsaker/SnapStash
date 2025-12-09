//
//  ContactsManager.swift
//  SnapStashMobile
//
//  Created by George on 05/12/2025.
//

import SwiftUI
import Contacts
import Combine

// MARK: - Contact Model
struct MatchedContact: Identifiable {
    let id: String
    let fullName: String
    let thumbnailImage: UIImage?
    
    init(contact: CNContact) {
        self.id = contact.identifier
        self.fullName = CNContactFormatter.string(from: contact, style: .fullName) ?? ""
        self.thumbnailImage = contact.thumbnailImageData.flatMap { UIImage(data: $0) }
    }
}

// MARK: - Contacts Manager
class ContactsManager: ObservableObject {
    static let shared = ContactsManager()
    
    @Published var authorizationStatus: CNAuthorizationStatus = .notDetermined
    @Published var contacts: [CNContact] = []
    @Published var isLoading = false
    
    // Store manual contact mappings: conversationId -> contactIdentifier
    @AppStorage("manualContactMappings") private var manualContactMappingsData: Data = Data()
    
    private var manualContactMappings: [String: String] {
        get {
            (try? JSONDecoder().decode([String: String].self, from: manualContactMappingsData)) ?? [:]
        }
        set {
            manualContactMappingsData = (try? JSONEncoder().encode(newValue)) ?? Data()
        }
    }
    
    // Cache for matched contacts
    private var matchedContactsCache: [String: MatchedContact] = [:]
    
    private let store = CNContactStore()
    private let keysToFetch: [CNKeyDescriptor] = [
        CNContactGivenNameKey as CNKeyDescriptor,
        CNContactFamilyNameKey as CNKeyDescriptor,
        CNContactNicknameKey as CNKeyDescriptor,
        CNContactThumbnailImageDataKey as CNKeyDescriptor,
        CNContactIdentifierKey as CNKeyDescriptor,
        CNContactFormatter.descriptorForRequiredKeys(for: .fullName)
    ]
    
    init() {
        checkAuthorizationStatus()
    }
    
    // MARK: - Authorization
    
    func checkAuthorizationStatus() {
        authorizationStatus = CNContactStore.authorizationStatus(for: .contacts)
    }
    
    func requestAccess() async -> Bool {
        do {
            let granted = try await store.requestAccess(for: .contacts)
            await MainActor.run {
                checkAuthorizationStatus()
                if granted {
                    Task {
                        await fetchContacts()
                    }
                }
            }
            return granted
        } catch {
            print("Error requesting contacts access: \(error)")
            return false
        }
    }
    
    // MARK: - Fetch Contacts
    
    @MainActor
    func fetchContacts() async {
        guard authorizationStatus == .authorized else { return }
        
        isLoading = true
        defer { isLoading = false }
        
        let request = CNContactFetchRequest(keysToFetch: keysToFetch)
        request.sortOrder = .givenName
        
        var fetchedContacts: [CNContact] = []
        
        do {
            try store.enumerateContacts(with: request) { contact, _ in
                fetchedContacts.append(contact)
            }
            contacts = fetchedContacts
        } catch {
            print("Error fetching contacts: \(error)")
        }
    }
    
    // MARK: - Contact Matching
    
    /// Get matched contact for a conversation
    func getMatchedContact(for conversationId: String, displayName: String) -> MatchedContact? {
        // Check manual mapping first
        if let manualContactId = manualContactMappings[conversationId],
           let contact = contacts.first(where: { $0.identifier == manualContactId }) {
            return MatchedContact(contact: contact)
        }
        
        // Check cache
        if let cached = matchedContactsCache[conversationId] {
            return cached
        }
        
        // Try to auto-match by name
        if let matched = findBestMatch(for: displayName) {
            let matchedContact = MatchedContact(contact: matched)
            matchedContactsCache[conversationId] = matchedContact
            return matchedContact
        }
        
        return nil
    }
    
    /// Find best matching contact by name
    private func findBestMatch(for displayName: String) -> CNContact? {
        let normalizedDisplayName = displayName.lowercased().trimmingCharacters(in: .whitespaces)
        
        // Try exact full name match first
        for contact in contacts {
            let fullName = CNContactFormatter.string(from: contact, style: .fullName)?.lowercased() ?? ""
            if fullName == normalizedDisplayName {
                return contact
            }
        }
        
        // Try matching by parts
        let displayNameParts = normalizedDisplayName.components(separatedBy: " ").filter { !$0.isEmpty }
        
        for contact in contacts {
            let givenName = contact.givenName.lowercased()
            let familyName = contact.familyName.lowercased()
            let nickname = contact.nickname.lowercased()
            
            // Match if display name contains both first and last name
            if !givenName.isEmpty && !familyName.isEmpty {
                if normalizedDisplayName.contains(givenName) && normalizedDisplayName.contains(familyName) {
                    return contact
                }
            }
            
            // Match by nickname
            if !nickname.isEmpty && normalizedDisplayName.contains(nickname) {
                return contact
            }
            
            // Match if first name matches exactly
            if !givenName.isEmpty && displayNameParts.contains(givenName) {
                return contact
            }
        }
        
        return nil
    }
    
    // MARK: - Manual Mapping
    
    /// Set a manual contact mapping for a conversation
    func setManualMapping(conversationId: String, contactId: String?) {
        var mappings = manualContactMappings
        if let contactId = contactId {
            mappings[conversationId] = contactId
        } else {
            mappings.removeValue(forKey: conversationId)
        }
        manualContactMappings = mappings
        
        // Clear cache for this conversation
        matchedContactsCache.removeValue(forKey: conversationId)
    }
    
    /// Clear manual mapping for a conversation
    func clearManualMapping(conversationId: String) {
        setManualMapping(conversationId: conversationId, contactId: nil)
    }
    
    /// Check if a conversation has a manual mapping
    func hasManualMapping(conversationId: String) -> Bool {
        manualContactMappings[conversationId] != nil
    }
    
    /// Get all contacts for manual selection
    func getAllContacts() -> [MatchedContact] {
        contacts.map { MatchedContact(contact: $0) }
    }
    
    /// Get contact by identifier
    func getContact(byId identifier: String) -> CNContact? {
        contacts.first { $0.identifier == identifier }
    }
    
    /// Clear all caches
    func clearCache() {
        matchedContactsCache.removeAll()
    }
}

// MARK: - Contact Picker View
struct ContactPickerView: View {
    @Environment(\.dismiss) var dismiss
    @ObservedObject var contactsManager: ContactsManager
    let conversationId: String
    let conversationName: String
    let onSelect: (String?) -> Void
    
    @State private var searchText = ""
    
    var filteredContacts: [MatchedContact] {
        let allContacts = contactsManager.getAllContacts()
        if searchText.isEmpty {
            return allContacts
        }
        return allContacts.filter { contact in
            contact.fullName.localizedCaseInsensitiveContains(searchText)
        }
    }
    
    var body: some View {
        NavigationStack {
            List {
                // Option to clear manual selection
                Section {
                    Button(action: {
                        onSelect(nil)
                        dismiss()
                    }) {
                        HStack {
                            Image(systemName: "xmark.circle")
                                .foregroundColor(.red)
                                .frame(width: 40, height: 40)
                            Text("Use Auto-Match")
                                .foregroundColor(.primary)
                        }
                    }
                }
                
                // Contact list
                Section("Contacts") {
                    ForEach(filteredContacts) { contact in
                        Button(action: {
                            onSelect(contact.id)
                            dismiss()
                        }) {
                            HStack(spacing: 12) {
                                // Contact photo
                                if let image = contact.thumbnailImage {
                                    Image(uiImage: image)
                                        .resizable()
                                        .scaledToFill()
                                        .frame(width: 40, height: 40)
                                        .clipShape(Circle())
                                } else {
                                    ZStack {
                                        Circle()
                                            .fill(Color.gray.opacity(0.3))
                                            .frame(width: 40, height: 40)
                                        Text(String(contact.fullName.prefix(2)).uppercased())
                                            .font(.system(size: 14, weight: .medium))
                                            .foregroundColor(.gray)
                                    }
                                }
                                
                                Text(contact.fullName)
                                    .foregroundColor(.primary)
                            }
                        }
                    }
                }
            }
            .searchable(text: $searchText, prompt: "Search contacts")
            .navigationTitle("Select Contact")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") {
                        dismiss()
                    }
                }
            }
        }
    }
}

// MARK: - Contact Photo View
struct ContactPhotoView: View {
    let contact: MatchedContact?
    let fallbackInitials: String
    let fallbackColor: Color
    let size: CGFloat
    
    var body: some View {
        if let contact = contact, let image = contact.thumbnailImage {
            Image(uiImage: image)
                .resizable()
                .scaledToFill()
                .frame(width: size, height: size)
                .clipShape(Circle())
        } else {
            ZStack {
                Circle()
                    .fill(fallbackColor)
                    .frame(width: size, height: size)
                Text(fallbackInitials)
                    .font(.system(size: size * 0.32, weight: .semibold))
                    .foregroundColor(.white)
            }
        }
    }
}
