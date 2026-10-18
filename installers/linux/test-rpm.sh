#!/bin/bash
# Executed only inside the disposable Fedora CI container.
set -euo pipefail
dnf -y install python3 "/src/dist/$1"
useradd --uid "$2" --create-home app-test
su -s /bin/bash app-test -c \
  'cd /src && python3 scripts/smoke.py --target linux-x64 --base /opt/notebooklm-studio --label installed-rpm'
dnf -y reinstall "/src/dist/$1"
dnf -y remove notebooklm-studio
test ! -e /opt/notebooklm-studio
test ! -e /usr/share/applications/io.github.astudilloalex.NotebookLMStudio.desktop
test ! -e /usr/bin/notebooklm-studio
test -f /src/.build/smoke/installed-rpm-linux-x64/Downloads/videos.zip
