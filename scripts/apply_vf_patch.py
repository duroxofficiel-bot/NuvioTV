#!/usr/bin/env python3
"""
Applique le patch "bandes-annonces VF d'abord" sur une copie du code upstream NuvioTV.

Deux modifications :
  1. TmdbMetadataService.kt : ajoute un rang de preference doublage/sous-titrage
     par langue (approx. via Locale.getDefault()) et l'insere en tete du tri.
  2. app/build.gradle.kts : pointe l'updater vers ce fork (GITHUB_OWNER / GITHUB_REPO)
     et force le type de keystore PKCS12.

Le script echoue (exit 1) si une ancre est introuvable -> le workflow passe au rouge
et l'utilisateur est prevenu, au lieu de publier un build sans le patch.
"""
import os
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
        print("TmdbMetadataService.kt : patch deja present")
    elif RANK_ANCHOR not in src or SORT_ANCHOR not in src:
        print(f"ERREUR: ancres introuvables dans {TMDB_PATH}")
        return False
    else:
        src = src.replace(RANK_ANCHOR, HELPERS + "    " + RANK_ANCHOR, 1)
        src = src.replace(SORT_ANCHOR, SORT_REPLACEMENT, 1)
        with open(TMDB_PATH, "w", encoding="utf-8") as fh:
            fh.write(src)
        print("TmdbMetadataService.kt : patch applique")
    return True


def rewrite_buildconfig_line(src, key, value):
    out = []
    changed = False
    for line in src.splitlines(keepends=True):
        if "buildConfigField" in line and f'"{key}"' in line:
            indent = line[: len(line) - len(line.lstrip())]
            newline = f'{indent}buildConfigField("String", "{key}", "\\"{value}\\"")'
            out.append(newline + ("\r\n" if line.endswith("\r\n") else "\n"))
            changed = True
        else:
            out.append(line)
    return "".join(out), changed


def ensure_pkcs12(src):
    if 'storeType' in src:
        print("build.gradle.kts : storeType deja present")
        return src, True
    marker = 'create("release") {'
    if marker not in src:
        print("ERREUR: bloc signingConfigs.create(\"release\") introuvable")
        return src, False
    src = src.replace(marker, marker + '\n            storeType = "PKCS12"', 1)
    print('build.gradle.kts : storeType = "PKCS12" ajoute')
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
    if not (patch_tmdb() and patch_gradle()):
        sys.exit(1)


if __name__ == "__main__":
    main()
