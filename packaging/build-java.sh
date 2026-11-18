#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p build/java-classes build/java
find src -type f -name '*.java' > build/java/sources.txt
javac -encoding UTF-8 -source 17 -target 17 -cp 'lib/*' -d build/java-classes @build/java/sources.txt
# Bundle source-loaded resources in their package paths.
find src -type f \( -name '*.properties' -o -name '*.png' -o -name '*.gif' -o -name '*.xml' \) |
while IFS= read -r f; do
    dest="build/java-classes/${f#src/}"
    mkdir -p "$(dirname "$dest")"
    cp "$f" "$dest"
done
