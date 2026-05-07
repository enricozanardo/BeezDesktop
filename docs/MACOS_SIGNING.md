# macOS Code Signing & Notarization

This document describes how the **BeezDesktop** macOS build is signed and
notarized in CI, what GitHub secrets are required, and how to rotate them.

The signing logic lives in [`.github/workflows/build.yml`](../.github/workflows/build.yml)
in the `build-macos` job and is **opt-in**: if any of the required secrets
is missing, the workflow falls back to `briefcase package macOS --adhoc-sign`
so PR/branch builds keep working.

---

## TL;DR

| Secret | Where it comes from | Example |
| --- | --- | --- |
| `APPLE_CERTIFICATE` | base64 of your `Developer ID Application` `.p12` | `base64 -i cert.p12` |
| `APPLE_CERTIFICATE_PASSWORD` | The password you set when exporting the `.p12` from Keychain | `s3cr3t` |
| `APPLE_SIGNING_IDENTITY` | Common Name of the cert | `Developer ID Application: Enrico Zanardo (3W276Y84C2)` |
| `APPLE_TEAM_ID` | Your Apple Developer Team ID | `3W276Y84C2` |
| `APPLE_API_KEY_ID` | App Store Connect API Key ID | `Z136IJH0TJ9C` |
| `APPLE_API_ISSUER` | App Store Connect API Issuer (UUID) | `b12cf364-e2c9-405d-9e87-a724a19cb8cc` |
| `APPLE_API_KEY_BASE64` | base64 of `AuthKey_<KEYID>.p8` | `base64 -i AuthKey_*.p8` |

Set them on the GitHub repo (`enricozanardo/BeezDesktop`) using `gh secret set`.
The CI job creates an **ephemeral** keychain per run, imports the cert, stores
the notarytool credentials under the profile name `briefcase-macOS-<TEAM_ID>`,
then deletes the keychain in an `if: always()` cleanup step. The cert is never
written to disk for longer than the import call needs it.

---

## 1. Create the Developer ID Application certificate (one-time)

You only need to do this once per developer account. Apple limits the number
of Developer ID Application certs per team to 5, so **export and back up the
`.p12` immediately**.

### 1.1 Generate a Certificate Signing Request (CSR) on a Mac

1. Open **Keychain Access**.
2. Top menu: `Keychain Access → Certificate Assistant → Request a Certificate From a Certificate Authority`.
3. Fill in:
   - **User Email Address**: the email on your Apple Developer account.
   - **Common Name**: your name as registered (e.g. `Enrico Zanardo`).
   - **CA Email Address**: leave empty.
   - **Request is**: select **Saved to disk** (do *not* "Let me specify key pair information").
4. Click **Continue** and save `CertificateSigningRequest.certSigningRequest` somewhere safe.

This *also* creates the matching private key in the **login** keychain on your
Mac. **Do not delete that key** — without it the resulting cert is useless.

### 1.2 Generate the cert on the Apple Developer portal

1. Go to <https://developer.apple.com/account/resources/certificates/list>.
2. Click the **+** button.
3. Under **Software**, choose **Developer ID Application** (NOT "Mac App Distribution",
   NOT "Apple Distribution"). This is the only certificate type that lets you
   distribute a Mac app outside the App Store with notarization.
4. Click **Continue**, upload the `.certSigningRequest` from step 1.1.
5. Download the resulting `developerID_application.cer`.
6. Double-click the `.cer` file to install it into Keychain Access.

### 1.3 Verify the cert is installed

In a Mac Terminal:

```sh
security find-identity -v -p codesigning
```

You should see at least one line like:

```
1) ABCDEF1234567890... "Developer ID Application: Enrico Zanardo (3W276Y84C2)"
```

The string after the hex thumbprint is the value you want for
`APPLE_SIGNING_IDENTITY`.

### 1.4 Export the cert as a `.p12` (for CI)

In Keychain Access:

1. Select the **login** keychain on the left, then the **My Certificates** tab.
2. Right-click the `Developer ID Application: ...` entry.
3. Choose **Export "Developer ID Application: ..."**.
4. File format: **Personal Information Exchange (.p12)**.
5. Save as e.g. `BeezDesktop-DeveloperID.p12`.
6. Set an export password — this becomes `APPLE_CERTIFICATE_PASSWORD`.

> The `.p12` file MUST contain BOTH the certificate AND its private key.
> If the export only writes the public cert, the private key was missing
> from the keychain (see 1.1). Do *not* try to base64-encode a `.cer` file
> for `APPLE_CERTIFICATE` — that's the public half only.

Drop the resulting `.p12` into `AppleCertificates/` (the folder is gitignored)
or wherever you keep credentials offline. You'll never need to re-export it
unless the cert expires or is revoked.

---

## 2. Create the App Store Connect API key (for notarization)

Notarization requires an App Store Connect API key, NOT an app-specific
password. The key is also reusable for `xcrun notarytool` from your laptop.

1. Go to <https://appstoreconnect.apple.com/access/integrations/api>.
2. Click **Generate API Key** (Team Keys, not Individual).
3. **Name**: e.g. `BeezDesktop CI`.
4. **Access**: `Developer` is enough for notarization.
5. After creating, **download the `.p8` immediately** — Apple only lets you
   download it once. Filename will be `AuthKey_<KEYID>.p8`.
6. Note the **Key ID** (10 chars) and the **Issuer ID** (UUID at the top of
   the page) — they become `APPLE_API_KEY_ID` and `APPLE_API_ISSUER`.

---

## 3. Push the secrets into GitHub

Run these from your local machine (you'll need `gh auth login` once):

```sh
cd /path/to/BeezDesktop  # the BeezDesktop submodule, not BeezMaster

# --- Cert ---------------------------------------------------------------
gh secret set APPLE_CERTIFICATE          < <(base64 -w0 /path/to/BeezDesktop-DeveloperID.p12)
gh secret set APPLE_CERTIFICATE_PASSWORD <<< 'YOUR_P12_EXPORT_PASSWORD'
gh secret set APPLE_SIGNING_IDENTITY     <<< 'Developer ID Application: Enrico Zanardo (3W276Y84C2)'
gh secret set APPLE_TEAM_ID              <<< '3W276Y84C2'

# --- App Store Connect API key (for notarization) -----------------------
gh secret set APPLE_API_KEY_ID           <<< 'YOUR_KEY_ID'
gh secret set APPLE_API_ISSUER           <<< 'YOUR_ISSUER_UUID'
gh secret set APPLE_API_KEY_BASE64       < <(base64 -w0 /path/to/AuthKey_YOUR_KEY_ID.p8)
```

> On macOS, replace `base64 -w0` with `base64 -i FILE` (BSD `base64` has no
> `-w0` flag and adds line wraps that GitHub strips, but it's cleaner to be
> explicit). On Linux (your dev box) the `-w0` form is required.

Verify:

```sh
gh secret list
```

You should see all 7 names.

---

## 4. Trigger a signed build

Any of these will trigger the `build-macos` job to produce a **signed +
notarized** artifact (the workflow auto-detects the secrets):

- Push a tag: `git tag v0.6.4 && git push origin v0.6.4` — also creates a
  GitHub Release with the `.dmg` / `.pkg` attached.
- Manual run: go to the `Build Desktop Apps` workflow on GitHub → `Run
  workflow`.

For PR builds (no secrets) the job stays at `--adhoc-sign` and produces an
unsigned artifact, so the workflow still passes.

---

## 5. Verify the resulting artifact

After downloading the signed `.dmg` or `.pkg` from a GitHub release:

```sh
# Verify the app bundle was signed by your Developer ID
codesign --verify --deep --strict --verbose=2 /Volumes/Beez\ Desktop/Beez\ Desktop.app

# Verify it was successfully notarized (and stapled)
spctl --assess --type execute --verbose /Volumes/Beez\ Desktop/Beez\ Desktop.app
```

Expected outputs:

```
... satisfies its Designated Requirement
... source=Notarized Developer ID
```

A user with no special setup can then double-click the `.dmg` / `.pkg` and
run the app — Gatekeeper will not block it.

---

## 6. Rotation / troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `errSecInternalComponent` during `codesign` | The `.p12` was exported without its private key | Re-export from Keychain on the Mac that generated the CSR (see 1.1) |
| `notarytool: 401 Unauthenticated` | API key revoked or wrong Issuer ID | Regenerate the App Store Connect key; rerun step 3 |
| `User interaction is not allowed` | `set-key-partition-list` step in CI didn't run / wrong password | Check that the `Import signing certificate` step succeeded; secrets may have changed |
| `The signature of the binary is invalid` from Gatekeeper | Cert expired (Developer ID Application certs last 5 years) | Generate a new cert (steps 1.1–1.4), rerun step 3 |
| Workflow says `falling back to --adhoc-sign` | One or more secrets are missing | `gh secret list` + diff against the table at the top |

To rotate any single secret, just run `gh secret set <NAME>` again with the
new value and re-trigger the workflow. There is no caching — every run
imports the cert fresh into a brand-new ephemeral keychain.
