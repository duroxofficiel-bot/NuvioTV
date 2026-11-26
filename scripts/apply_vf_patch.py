#!/usr/bin/env python3
"""
Applique le patch "bandes-annonces VF d'abord" sur une copie du code upstream NuvioTV.

Trois modifications :
  1. TmdbMetadataService.kt : rang de preference doublage/sous-titrage par langue
     (approx. via Locale.getDefault()) insere en tete du tri des trailers TMDB.
  2. MetaDetailsViewModel.kt : les trailers TMDB (tries) passent AVANT les trailers
     fournis par l'addon de metadonnees, sinon l'ordre de l'addon (VOST en premier) gagne.
  3. app/build.gradle.kts : updater -> ce fork + storeType PKCS12.

Echoue (exit 1) si une ancre est introuvable -> workflow rouge, pas de build silencieux.
"""
import os
import sys

OWNER = os.environ.get("FORK_OWNER", "")
REPO = os.environ.get("FORK_REPO", "")

TMDB_PATH = "app/src/main/java/com/nuvio/tv/core/tmdb/TmdbMetadataService.kt"
DETAIL_PATH = "app/src/main/java/com/nuvio/tv/ui/screens/detail/MetaDetailsViewModel.kt"
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


def patch_tmdb():
    with open(TMDB_PATH, encoding="utf-8") as fh:
        src = fh.read()
    if "preferredDubRank" in src:
        print("TmdbMetadataService.kt : deja patche")
        return True
    if RANK_ANCHOR not in src or SORT_ANCHOR not in src:
        print(f"ERREUR: ancres introuvables dans {TMDB_PATH}")
        return False
    src = src.replace(RANK_ANCHOR, HELPERS + "    " + RANK_ANCHOR, 1)
    src = src.replace(SORT_ANCHOR, SORT_REPLACEMENT, 1)
    with open(TMDB_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("TmdbMetadataService.kt : tri VF applique")
    return True


def patch_detail():
    with open(DETAIL_PATH, encoding="utf-8") as fh:
        src = fh.read()
    if MERGE_REPLACEMENT in src:
        print("MetaDetailsViewModel.kt : deja patche")
        return True
    if MERGE_ANCHOR not in src:
        print(f"ERREUR: ancre mergeTrailers introuvable dans {DETAIL_PATH}")
        return False
    src = src.replace(MERGE_ANCHOR, MERGE_REPLACEMENT, 1)
    with open(DETAIL_PATH, "w", encoding="utf-8") as fh:
        fh.write(src)
    print("MetaDetailsViewModel.kt : trailers TMDB prioritaires")
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
    ok = patch_tmdb() and patch_detail() and patch_gradle()
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
