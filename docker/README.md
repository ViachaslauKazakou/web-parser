# Browser sandbox profile

`seccomp_profile.json` is a small Linux allowlist used for the Chromium process that parses public forum pages. The Playwright package is pinned to v1.64.1 so this browser/security pairing stays reproducible. The profile is based on the Playwright Python Docker profile for v1.64.1 and the current Moby/Docker default seccomp rules:

- <https://github.com/microsoft/playwright/blob/v1.64.1/utils/docker/seccomp_profile.json>
- <https://github.com/moby/profiles/blob/main/seccomp/default.json>

The profile allows the user-namespace operations required by Chromium's unprivileged sandbox, plus `chroot` inside that user namespace. It does not add `SYS_ADMIN`, `SYS_CHROOT`, or another Linux capability. Socket families are allowlisted; AF_ALG and AF_VSOCK are not permitted. The profile targets the Docker-supported x86_64/ARM64 architectures used by this stack. WebRTC is disabled for parsed pages, and Chromium is configured to disallow unproxied UDP.

`Dockerfile` installs only the Debian 13 Chromium runtime library list from Playwright 1.64.1's `nativeDeps` registry, not its test-only Xvfb/font/tool packages. The browser download uses Playwright's headless-shell-only mode because the app never launches a visible browser.

When updating Playwright or the Linux base image, re-run the browser startup and parser egress tests before changing the allowlist.
