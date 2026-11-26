#!/usr/bin/env python3
"""
Applique le patch "bandes-annonces VF d'abord" sur une copie du code upstream NuvioTV.

Deux modifications :
  1. TmdbMetadataService.kt : ajoute un rang de préférence doublage/sous-titrage
     par langue (approx. via Locale.getDefault()) et l'insère en tête du tri.
  2. app/build.gradle.kts : pointe l'updater vers ce fork (GITHUB_OWNER / GITHUB_REPO).

Le script échoue (exit 1) si une ancre est introuvable -> le workflow passe au rouge
et l'utilisateur est prévenu, au lieu de publier un build sans le patch.
"""
import os
import re
import sys

OWNER = os.environ.get("FORK_OWNER", "")
REPO = os.environ.get("FORK_REPO", "")

TMDB_PATH = "app/src/main/java/com/nuvio/tv/core/tmdb/TmdbMetadataService.kt"
GRADLE_PATH = "app/build.gradle.kts"

HELPERS = '''
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


def patch_tmdb():
    with open(TMDB_PATH, encoding="utf-8") as fh:
        src = fh.read()

    if "preferredDubRank" in src:
        print("TmdbMetadataService.kt : patch déjà présent, rien à faire")
        return True

    if RANK_ANCHOR not in src:
        print(f"ERREUR: ancre '{RANK_ANCHOR}' introuvable dans {TMDB_PATH}")
        return False
    if SORT_ANCHOR not in src:
        print(f"ERREUR: ancre '{SORT_ANCHOR}' introuvable dans {TMDB_PATH}")
        return False

    src = src.replace(RANK_ANCHOR, HELPERS + "    " + RANK_ANCHOR, 1)
    src = src.replace(SORT_ANCHOR, SORT_REPLACEMENT, 1)

    with open(TMDB_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("TmdbMetadataService.kt : patch appliqué")
    return True


def patch_gradle():
    if not OWNER or not REPO:
        print("ERREUR: FORK_OWNER / FORK_REPO non définis")
        return False
    with open(GRADLE_PATH, encoding="utf-8") as fh:
        src = fh.read()
    new = re.sub(
        r'buildConfigField\("String",\s*"GITHUB_OWNER",\s*"[^"]*"\)',
        f'buildConfigField("String", "GITHUB_OWNER", "\\"{OWNER}\\"")',
        src,
    )
    new = re.sub(
        r'buildConfigField\("String",\s*"GITHUB_REPO",\s*"[^"]*"\)',
        f'buildConfigField("String", "GITHUB_REPO", "\\"{REPO}\\"")',
        new,
    )
    if new == src:
        print("ERREUR: GITHUB_OWNER/GITHUB_REPO non remplacés")
        return False
    with open(GRADLE_PATH, "w", encoding="utf-8") as fh:
        fh.write(new)
    print(f"build.gradle.kts : updater -> {OWNER}/{REPO}")
    return True


def main():
    ok = patch_tmdb() and patch_gradle()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
