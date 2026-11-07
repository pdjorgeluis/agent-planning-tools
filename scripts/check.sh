#!/usr/bin/env bash
# Runs every check. Exit 0 and print ALL CHECKS PASSED only if all pass.
# Set APT_TERMS_FILE to a terms file to include the private-strings test and
# the term scan; without it only the pattern checks run.
set -u
cd "$(dirname "$0")/.." || exit 2
fail=0
step() { printf '== %s\n' "$1"; }
bad() { printf 'FAILED: %s\n' "$1"; fail=1; }

for d in lib/aptlib/tests tools/metis/tests tools/momus/tests tests; do
  step "unittest $d"
  out=$(python3 -I -m unittest discover -s "$d" -t . 2>&1); rc=$?
  printf '%s\n' "$out" | tail -3
  [ $rc -eq 0 ] || bad "unittest $d"
done

step "privacy scan"
scan_args=()
[ -n "${APT_TERMS_FILE:-}" ] && scan_args+=(--terms-file "$APT_TERMS_FILE")
python3 -I scripts/privacy-scan.py "${scan_args[@]}" || bad "privacy scan"

step "momus offline (deterministic layer)"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
printf 'A spec that cites no files.\n' > "$tmp/spec.md"
out=$(HOME="$tmp/home" APT_LOG_DIR="$tmp/logs" python3 -I tools/momus/momus.py --backend none "$tmp/spec.md"); rc=$?
printf '%s\n' "$out" | head -2
{ [ $rc -eq 0 ] && printf '%s\n' "$out" | head -1 | grep -q '^\[momus\]'; } || bad "momus offline"

step "installer round trip (scratch prefix)"
p="$tmp/prefix"
for t in metis momus all; do
  m=$(python3 -I install.py --tools "$t" --target generic --prefix "$p" --dry-run --yes) || bad "dry-run $t"
  case $t in
    metis) printf '%s\n' "$m" | grep -qi momus && bad "metis dry-run lists momus";;
    momus) printf '%s\n' "$m" | grep -qi metis && bad "momus dry-run lists metis";;
  esac
done
python3 -I install.py --tools all --target hermes --prefix "$p" --yes >/dev/null || bad "install"
python3 -I install.py --uninstall --prefix "$p" >/dev/null || bad "uninstall"
left=$(find "$p" -type f 2>/dev/null | wc -l)
[ "$left" -eq 0 ] || bad "uninstall left $left file(s)"

if grep -rIl "PLACEHOLDER" tools/*/prompt.md >/dev/null 2>&1; then
  echo "NOTE: prompt placeholders still present (the prose card has not landed)"
fi

if [ $fail -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "CHECKS FAILED"; exit 1; fi
