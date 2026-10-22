package `in`.tryvanta.laylavoice

/** Same sentence chunking as the web face page (splitForSpeech), so the first audio can start after one short /tts call. */
object Speech {
    private const val SPEAK_MAX = 900
    private const val SINGLE_BELOW = 140
    private val boundary = Regex("""([.!?।]+)(\s+)(?=[A-Z"'“0-9ఀ-౿])""")
    private val abbrev = setOf("dr", "mr", "mrs", "ms", "rs", "st", "no", "vs", "etc", "e.g", "i.e")

    fun split(text: String): List<String> {
        var t = text.trim()
        if (t.isEmpty()) return emptyList()
        var capped = false
        if (t.length > SPEAK_MAX) {
            t = t.substring(0, SPEAK_MAX).substringBeforeLast(' ')
            capped = true
        }
        if (t.length < SINGLE_BELOW) return listOf(t) + (if (capped) listOf(REST) else emptyList())

        val parts = ArrayList<String>()
        var start = 0
        for (m in boundary.findAll(t)) {
            val word = t.substring(start, m.range.first).substringAfterLast(' ').lowercase().trimEnd('.')
            if (word in abbrev) continue
            parts.add(t.substring(start, m.range.last + 1).trim().let { it })
            start = m.range.last + 1
        }
        if (start < t.length) parts.add(t.substring(start).trim())

        val out = ArrayList<String>()
        var cur = ""
        for (p in parts) {
            cur = if (cur.isEmpty()) p else "$cur $p"
            if (cur.length >= 40) { out.add(cur); cur = "" }
        }
        if (cur.isNotEmpty()) {
            if (out.isNotEmpty() && cur.length < 25) out[out.size - 1] = out.last() + " " + cur else out.add(cur)
        }
        if (capped) out.add(REST)
        return out
    }

    private const val REST = "The rest is on your screen."
}
