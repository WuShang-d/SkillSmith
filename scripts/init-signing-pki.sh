#!/usr/bin/env bash
# Create a local enterprise trust chain for signing skills with OpenSSF model signing:
#   root CA (trust anchor, published to agent hosts)  ->  code-signing certificate (used by SkillSmith)
# Private keys stay in the PKI directory (default ~/.skillsmith-pki, mode 700), never in the repo.
# This mirrors NVIDIA's skill.oms.sig + nv-agent-root-cert.pem flow for an organisation's own skills.
set -euo pipefail

pki="${SKILLSMITH_PKI_DIR:-$HOME/.skillsmith-pki}"
org="${SKILLSMITH_PKI_ORG:-SkillSmith Demo Org}"
days="${SKILLSMITH_PKI_DAYS:-365}"

if [[ -f "$pki/signing-key.pem" && "${SKILLSMITH_PKI_FORCE:-0}" != "1" ]]; then
  echo "PKI already exists in $pki (set SKILLSMITH_PKI_FORCE=1 to recreate)"
  exit 0
fi
mkdir -p "$pki"
chmod 700 "$pki"
cd "$pki"
umask 077

openssl ecparam -name prime256v1 -genkey -noout -out root-key.pem
openssl req -x509 -new -key root-key.pem -sha256 -days "$days" -out root-cert.pem \
  -subj "/O=$org/CN=$org Skills Root CA" \
  -addext "basicConstraints=critical,CA:TRUE" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -addext "subjectKeyIdentifier=hash"

openssl ecparam -name prime256v1 -genkey -noout -out signing-key.pem
openssl req -new -key signing-key.pem -out signing.csr -subj "/O=$org/CN=$org Skill Release Signer"
cat > signing.ext <<EOF
basicConstraints=critical,CA:FALSE
keyUsage=critical,digitalSignature
extendedKeyUsage=codeSigning
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid
EOF
openssl x509 -req -in signing.csr -CA root-cert.pem -CAkey root-key.pem -CAcreateserial \
  -days "$days" -sha256 -extfile signing.ext -out signing-cert.pem
rm -f signing.csr signing.ext
chmod 644 root-cert.pem signing-cert.pem

echo "Trust anchor (publish to agent hosts): $pki/root-cert.pem"
echo "Signer certificate:                     $pki/signing-cert.pem"
echo "Signer private key (keep private):      $pki/signing-key.pem"
openssl x509 -in root-cert.pem -noout -fingerprint -sha256
