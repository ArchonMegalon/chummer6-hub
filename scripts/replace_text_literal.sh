#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <file>" >&2
    echo "requires OLD_TEXT and NEW_TEXT environment variables" >&2
    exit 64
fi

file="$1"

if [ ! -f "$file" ]; then
    echo "file not found: $file" >&2
    exit 66
fi

: "${OLD_TEXT:?OLD_TEXT is required}"
: "${NEW_TEXT:?NEW_TEXT is required}"

perl -0pi -e '
my $old = $ENV{"OLD_TEXT"};
my $new = $ENV{"NEW_TEXT"};
my $count = s/\Q$old\E/$new/g;
if (($ENV{"REPLACE_ALL"} // q{}) eq q{1}) {
    die "pattern not found\n" if $count == 0;
}
else {
    die "expected exactly one replacement, got $count\n" if $count != 1;
}
' "$file"
