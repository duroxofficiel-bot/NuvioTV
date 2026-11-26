#!/usr/bin/env python3
"""
Patch "bandes-annonces VF d'abord" pour le fork NuvioTV.

Modifications :
  1. TmdbMetadataService.kt : ranking des trailers TMDB par langue (doublage avant
     sous-titrage), insere en tete du tri.
  2. MetaDetailsViewModel.kt :
       - les trailers TMDB (tries) passent avant ceux de l'addon (merge),
       - le repli "trailerYtIds.firstOrNull()" devient dependant de la langue
         (fr d'abord, VOST en dernier) au lieu de prendre le premier venu.
  3. TmdbService.kt : retry/backoff sur 401/429 (TMDB rejette par salves) +
     log de la longueur de cle.
  4. app/build.gradle.kts : updater -> ce fork + storeType PKCS12.

Echoue (exit 1) si une ancre est introuvable.
"""
import os
import sys

OWNER = os.environ.get("FORK_OWNER", "")
REPO = os.environ.get("FORK_REPO", "")

TMDB_PATH = "app/src/main/java/com/nuvio/tv/core/tmdb/TmdbMetadataService.kt"
SVC_PATH = "app/src/main/java/com/nuvio/tv/core/tmdb/TmdbService.kt"
DETAIL_PATH = "app/src/main/java/com/nuvio/tv/ui/screens/detail/MetaDetailsViewModel.kt"
GRADLE_PATH = "app/build.gradle.kts"

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


def patch_tmdb():
    with open(TMDB_PATH, encoding="utf-8") as fh:
        src = fh.read()
    if "preferredDubRank" in src:
        print("TmdbMetadataService.kt : deja patche")
        return True
    if RANK_ANCHOR not in src or SORT_ANCHOR not in src:
        print(f"ERREUR: ancres introuvables dans {TMDB_PATH}")
        return False
    src = src.replace(RANK_ANCHOR, TMDB_HELPERS + "    " + RANK_ANCHOR, 1)
    src = src.replace(SORT_ANCHOR, SORT_REPLACEMENT, 1)
    with open(TMDB_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("TmdbMetadataService.kt : tri VF applique")
    return True


def patch_detail():
    with open(DETAIL_PATH, encoding="utf-8") as fh:
        src = fh.read()
    if "preferredTrailerYtId" in src:
        print("MetaDetailsViewModel.kt : deja patche")
        return True
    if MERGE_ANCHOR not in src:
        print(f"ERREUR: ancre mergeTrailers introuvable dans {DETAIL_PATH}")
        return False
    if FALLBACK_A_ANCHOR not in src or FALLBACK_B_ANCHOR not in src:
        print(f"ERREUR: ancres trailerYtIds introuvables dans {DETAIL_PATH}")
        return False
    src = src.replace(MERGE_ANCHOR, MERGE_REPLACEMENT, 1)
    src = src.replace(FALLBACK_A_ANCHOR, FALLBACK_A_REPLACEMENT, 1)
    src = src.replace(FALLBACK_B_ANCHOR, FALLBACK_B_REPLACEMENT, 1)
    marker = "    private fun fetchTrailerUrl() {"
    if marker not in src:
        print("ERREUR: fetchTrailerUrl introuvable")
        return False
    src = src.replace(marker, DETAIL_HELPERS + marker, 1)
    with open(DETAIL_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("MetaDetailsViewModel.kt : merge + repli langue appliques")
    return True


def patch_service():
    with open(SVC_PATH, encoding="utf-8") as fh:
        src = fh.read()
    if "tmdbAttempt" in src:
        print("TmdbService.kt : deja patche")
        return True
    if SVC_ANCHOR not in src:
        print(f"ERREUR: ancre findByExternalId introuvable dans {SVC_PATH}")
        return False
    src = src.replace(SVC_ANCHOR, SVC_REPLACEMENT, 1)
    with open(SVC_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("TmdbService.kt : retry/backoff 401-429 applique")
    return True


def rewrite_buildconfig_line(src, key, value):
    out, changed = [], False
    for line in src.splitlines(keepends=True):
        if "buildConfigField" in line and f'"{key}"' in line:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(
                f'{indent}buildConfigField("String", "{key}", "\\"{value}\\"")'
                + ("\r\n" if line.endswith("\r\n") else "\n")
            )
            changed = True
        else:
            out.append(line)
    return "".join(out), changed


def ensure_pkcs12(src):
    if "storeType" in src:
        print("build.gradle.kts : storeType deja present")
        return src, True
    marker = 'create("release") {'
    if marker not in src:
        print('ERREUR: bloc create("release") introuvable')
        return src, False
    src = src.replace(marker, marker + '\n            storeType = "PKCS12"', 1)
    print('build.gradle.kts : storeType PKCS12 ajoute')
    return src, True


def patch_gradle():
    if not OWNER or not REPO:
        print("ERREUR: FORK_OWNER / FORK_REPO non definis")
        return False
    with open(GRADLE_PATH, encoding="utf-8") as fh:
        src = fh.read()
    src, ok1 = rewrite_buildconfig_line(src, "GITHUB_OWNER", OWNER)
    src, ok2 = rewrite_buildconfig_line(src, "GITHUB_REPO", REPO)
    if not (ok1 and ok2):
        print("ERREUR: GITHUB_OWNER/GITHUB_REPO non remplaces")
        return False
    src, ok3 = ensure_pkcs12(src)
    if not ok3:
        return False
    with open(GRADLE_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print(f"build.gradle.kts : updater -> {OWNER}/{REPO}")
    return True


def main():
    ok = patch_tmdb() and patch_detail() and patch_service() and patch_gradle()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
