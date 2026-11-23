#!/bin/sh
# Run on the release host. Only publisher.cer leaves this machine.
set -eu
umask 077
test "$(id -u)" -eq 0 || { echo 'release host root required' >&2; exit 1; }
state=/var/lib/multica-workspace-signing
install -d -m 0700 -o root -g root "$state"
exec 9>"$state/.init.lock"
flock -x 9
if [ -e "$state/key.pem" ] || [ -e "$state/cert.pem" ]; then
    test -s "$state/key.pem" && test -s "$state/cert.pem" || {
        echo 'incomplete publisher identity; recover it before re-enrollment' >&2; exit 1;
    }
else
    tmp=$(mktemp -d "$state/.identity.XXXXXX")
    trap 'rm -f "$tmp/key.pem" "$tmp/cert.pem"; rmdir "$tmp"' EXIT
    openssl req -x509 -newkey rsa:3072 -noenc -sha256 -days 365 \
        -subj '/CN=Multica cloud-work Internal PowerShell Publisher' \
        -addext 'basicConstraints=critical,CA:FALSE' \
        -addext 'keyUsage=critical,digitalSignature' \
        -addext 'extendedKeyUsage=critical,codeSigning' \
        -keyout "$tmp/key.pem" -out "$tmp/cert.pem"
    chmod 0600 "$tmp/key.pem" "$tmp/cert.pem"
    mv "$tmp/key.pem" "$state/key.pem"
    mv "$tmp/cert.pem" "$state/cert.pem"
fi
private_public=$(openssl pkey -in "$state/key.pem" -pubout)
cert_public=$(openssl x509 -in "$state/cert.pem" -pubkey -noout)
test "$private_public" = "$cert_public" || { echo 'publisher key mismatch' >&2; exit 1; }
openssl x509 -in "$state/cert.pem" -checkend 0 -noout
openssl x509 -in "$state/cert.pem" -outform DER -out "$state/publisher.cer"
openssl x509 -in "$state/cert.pem" -noout -enddate -fingerprint -sha256
