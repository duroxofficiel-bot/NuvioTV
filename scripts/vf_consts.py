# Constantes du patch VF (Kotlin snippets + ancres).
TMDB_HELPERS = '''
    private val preferredDubTokens = mapOf(
        "fr" to listOf("VF", "VFF", "VFQ"),
        "de" to listOf("DEUTSCH", "GERMAN"),
        "es" to listOf("CASTELLANO", "LATINO"),
        "it" to listOf("ITALIANO"),
        "pt" to listOf("DUBLADO"),
        "ru" to listOf("\\u0414\\u0423\\u0411\\u041b\\u042f\\u0416"),
    )

    private val preferredSubTokens = mapOf(
        "fr" to listOf("VOST", "VOSTFR", "STF"),
        "de" to listOf("OMU", "UNTERTITEL"),
        "es" to listOf("SUBTITULADO"),
        "it" to listOf("SOTTOTITOLATO"),
        "pt" to listOf("LEGENDADO"),
        "ru" to listOf("\\u0421\\u0423\\u0411\\u0422\\u0418\\u0422\\u0420"),
    )

    /** 0 = doublage, 1 = neutre, 2 = sous-titre (nom explicite). */
    private fun preferredDubRank(video: TmdbVideoResult): Int {
        val language = java.util.Locale.getDefault().language.lowercase().take(2)
        val name = video.name.orEmpty().uppercase(java.util.Locale.ROOT)
        if (preferredSubTokens[language].orEmpty().any { name.contains(it) }) return 2
        if (preferredDubTokens[language].orEmpty().any { name.contains(it) }) return 0
        return 1
    }

'''

SORT_ANCHOR = "compareBy<TmdbVideoResult> { typePriority(it.type) }"
SORT_REPLACEMENT = (
    "compareBy<TmdbVideoResult> { preferredDubRank(it) }\n"
    "                    .thenBy { typePriority(it.type) }"
)
RANK_ANCHOR = "private fun rankTmdbTrailers("

MERGE_ANCHOR = (
    "            val mergedTrailers = mergeTrailers(\n"
    "                existing = updated.trailers,\n"
    "                incoming = enrichment.trailers\n"
    "            )"
)
MERGE_REPLACEMENT = (
    "            val mergedTrailers = mergeTrailers(\n"
    "                existing = enrichment.trailers,\n"
    "                incoming = updated.trailers\n"
    "            )"
)

FALLBACK_A_ANCHOR = (
    "                ) ?: meta.trailerYtIds.firstOrNull()?.let { ytId ->\n"
    "                    trailerService.getTrailerPlaybackSourceFromYouTubeUrl("
)
FALLBACK_A_REPLACEMENT = (
    "                ) ?: preferredTrailerYtId(meta.trailers, meta.trailerYtIds)?.let { ytId ->\n"
    "                    trailerService.getTrailerPlaybackSourceFromYouTubeUrl("
)
FALLBACK_B_ANCHOR = (
    "                    ) ?: meta.trailerYtIds.firstOrNull()?.let { ytId ->\n"
    '                        "https://www.youtube.com/watch?v=$ytId"'
)
FALLBACK_B_REPLACEMENT = (
    "                    ) ?: preferredTrailerYtId(meta.trailers, meta.trailerYtIds)?.let { ytId ->\n"
    '                        "https://www.youtube.com/watch?v=$ytId"'
)

DETAIL_HELPERS = '''
    /**
     * Repli dependant de la langue : choisit un trailer de l'addon en preferant
     * la langue de l'app, et en repoussant les versions explicitement sous-titrees
     * (VOST/VOSTFR/OMU...). Evite de jouer une BA VOSTFR quand une VF existe.
     */
    private fun preferredTrailerYtId(
        trailers: List<MetaTrailer>,
        fallbackIds: List<String>
    ): String? {
        if (trailers.isNotEmpty()) {
            val appLanguage = java.util.Locale.getDefault().language.lowercase().take(2)
            fun rank(trailer: MetaTrailer): Int {
                val name = trailer.name.orEmpty().uppercase(java.util.Locale.ROOT)
                val subTokens = mapOf(
                    "fr" to listOf("VOST", "VOSTFR", "STF"),
                    "de" to listOf("OMU", "UNTERTITEL"),
                    "es" to listOf("SUBTITULADO"),
                    "it" to listOf("SOTTOTITOLATO"),
                    "pt" to listOf("LEGENDADO"),
                )[appLanguage].orEmpty()
                if (subTokens.any { name.contains(it) }) return 3
                val trailerLanguage = trailer.lang.orEmpty().lowercase().take(2)
                if (trailerLanguage.isNotBlank() && trailerLanguage == appLanguage) return 0
                if (trailerLanguage.isBlank()) return 1
                return 2
            }
            trailers
                .filter { !it.ytId.isNullOrBlank() }
                .sortedBy { rank(it) }
                .firstOrNull()
                ?.ytId
                ?.let { return it }
        }
        return fallbackIds.firstOrNull()
    }

'''

SVC_ANCHOR = '''            val response = tmdbApi.findByExternalId(
                externalId = imdbId,
                apiKey = TMDB_API_KEY,
                externalSource = "imdb_id"
            )
            
            if (!response.isSuccessful) {
                Log.e(TAG, "TMDB API error: ${response.code()} - ${response.message()}")'''

SVC_REPLACEMENT = '''            var response = tmdbApi.findByExternalId(
                externalId = imdbId,
                apiKey = TMDB_API_KEY,
                externalSource = "imdb_id"
            )
            var tmdbAttempt = 0
            while (!response.isSuccessful &&
                (response.code() == 401 || response.code() == 429) &&
                tmdbAttempt < 2
            ) {
                tmdbAttempt++
                kotlinx.coroutines.delay(800L * tmdbAttempt)
                response = tmdbApi.findByExternalId(
                    externalId = imdbId,
                    apiKey = TMDB_API_KEY,
                    externalSource = "imdb_id"
                )
            }

            if (!response.isSuccessful) {
                Log.e(
                    TAG,
                    "TMDB API error: ${response.code()} - ${response.message()} " +
                        "(key length=${TMDB_API_KEY.length})"
                )'''


