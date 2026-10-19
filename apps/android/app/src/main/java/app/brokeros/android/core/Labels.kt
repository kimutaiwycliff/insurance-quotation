package app.brokeros.android.core

/** Plain names for the API's codes, matching the web app's wording. Unknown codes fall back to [humanize]. */
object Labels {
    private val names = mapOf(
        // client and lead
        "individual" to "Individual", "corporate" to "Company",
        "national_id" to "National ID", "passport" to "Passport", "alien_id" to "Alien ID",
        "business_registration" to "Business registration",
        "female" to "Female", "male" to "Male", "other" to "Other",
        "whatsapp" to "WhatsApp", "sms" to "SMS", "email" to "Email", "call" to "Phone call",
        "walk_in" to "Walk-in", "referral" to "Referral", "lead" to "From a lead", "social" to "Social media",
        "website" to "Website", "facebook" to "Facebook", "event" to "Event", "existing_client" to "Existing client",
        "new" to "New", "contacted" to "Contacted", "quoted" to "Quoted", "won" to "Won", "lost" to "Lost",
        "motor" to "Motor", "medical" to "Medical", "life" to "Life", "home" to "Home", "business" to "Business",
        "travel" to "Travel", "education" to "Education",
        // activities
        "note" to "Note", "meeting" to "Meeting", "visit" to "Visit",
        // tasks
        "low" to "Low", "normal" to "Normal", "high" to "High", "open" to "Open", "done" to "Done",
        // documents
        "kyc_id" to "ID or passport copy", "kyc_pin" to "KRA PIN certificate", "kyc_other" to "Other KYC document",
        "policy_schedule" to "Policy schedule", "certificate" to "Certificate", "vehicle_logbook" to "Vehicle logbook",
        "claim" to "Claim document", "generated" to "Generated document", "branding" to "Branding",
        // billing
        "draft" to "Draft", "issued" to "Unpaid", "part_paid" to "Part paid", "paid" to "Paid", "void" to "Void",
        "overdue" to "Overdue", "sent" to "Sent", "accepted" to "Accepted", "declined" to "Declined", "expired" to "Expired",
        "withdrawn" to "Withdrawn", "converted" to "Invoiced", "invoice" to "Invoice", "sales_quote" to "Sales quote",
        "credit_note" to "Credit note", "unmatched" to "To match", "matched" to "Matched", "ignored" to "Set aside",
        "mpesa" to "M-Pesa", "bank" to "Bank", "cash" to "Cash", "cheque" to "Cheque", "card" to "Card",
        // policies
        "active" to "Active", "pending" to "Waiting for insurer", "cancelled" to "Cancelled",
        "due" to "To contact", "renewed" to "Renewed",
    )

    fun of(code: String?): String = code?.let { names[it] ?: humanize(it) } ?: ""

    val activityKinds = listOf("call", "whatsapp", "meeting", "visit", "note", "sms", "email")
    val leadStages = listOf("new", "contacted", "quoted", "won", "lost")
    val leadSources = listOf("referral", "walk_in", "whatsapp", "facebook", "website", "event", "existing_client", "other")
    val interests = listOf("motor", "medical", "life", "home", "business", "travel", "education", "other")
    val clientSources = listOf("walk_in", "referral", "lead", "social", "website", "other")
    val channels = listOf("whatsapp", "call", "sms", "email")
    val idTypes = listOf("national_id", "passport", "alien_id", "business_registration")
    val documentCategories = listOf("kyc_id", "kyc_pin", "vehicle_logbook", "policy_schedule", "certificate", "claim", "kyc_other", "other")
}
