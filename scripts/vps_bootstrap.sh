#!/usr/bin/env bash
# Dung mot VPS trong (Ubuntu 22.04/24.04) thanh may deploy duoc.
# Chay MOT LAN, tren VPS, bang root hoac user thuong co sudo:
#   bash vps_bootstrap.sh
#
# Script nay KHONG dung app. No chi lo: docker, swap, tuong lua, nginx,
# thu muc deploy va khoa SSH cho GitHub Actions. Deploy that do workflow lam.
set -euo pipefail

# Chay bang root thi khong can sudo — va nhieu image VPS toi gian khong cai san
# sudo, nen goi thang `sudo` se chet ngay o buoc dau. Dinh nghia SUDO rong khi
# da la root.
if [ "$(id -u)" -eq 0 ]; then
  SUDO=""
else
  command -v sudo >/dev/null || { echo "Can sudo, hoac chay bang root." >&2; exit 1; }
  SUDO="sudo"
fi

# `ssh host 'bash script'` khong phai login shell; USER thuong co nhung khong
# chac, ma `set -u` se giet script neu thieu.
USER="${USER:-$(id -un)}"
HOME="${HOME:-$(getent passwd "$USER" | cut -d: -f6)}"

echo "==> 1/6 Docker"
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | $SUDO sh
  if [ -n "$SUDO" ]; then
    $SUDO usermod -aG docker "$USER"
    echo "    Da them $USER vao group docker — phai dang xuat/vao lai moi an."
  fi
else
  echo "    Da co, bo qua."
fi

echo "==> 2/6 Swap 2GB"
# VPS 4GB chay Postgres + MinIO + Python(langchain,pandas) + Next. Luc parse PDF
# hay batch embedding, Python phinh dot ngot. Swap la cai dem giua "cham mot
# nhip" va "OOM kill container giua luot chat cua khach".
if ! $SUDO swapon --show | grep -q /swapfile; then
  $SUDO fallocate -l 2G /swapfile
  $SUDO chmod 600 /swapfile
  $SUDO mkswap /swapfile
  $SUDO swapon /swapfile
  echo '/swapfile none swap sw 0 0' | $SUDO tee -a /etc/fstab >/dev/null
  # Mac dinh 60 la qua han: nhan xuong 10 de kernel chi cham swap khi that su can.
  echo 'vm.swappiness=10' | $SUDO tee /etc/sysctl.d/99-swap.conf >/dev/null
  $SUDO sysctl -p /etc/sysctl.d/99-swap.conf >/dev/null
else
  echo "    Da co, bo qua."
fi

echo "==> 3/6 Tuong lua"
# Chi 22/80/443. Postgres va MinIO khong publish cong ra host, backend/frontend
# chi bind 127.0.0.1 — nhung van dong o tang tuong lua cho chac.
$SUDO ufw allow 22/tcp
$SUDO ufw allow 80/tcp
$SUDO ufw allow 443/tcp
$SUDO ufw --force enable

echo "==> 4/6 Thu muc deploy"
mkdir -p ~/p150-prod ~/p150-staging ~/backups

echo "==> 5/6 Nginx + certbot"
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq nginx certbot python3-certbot-nginx

echo "==> 6/6 Khoa SSH cho GitHub Actions"
if [ ! -f ~/.ssh/gh_deploy ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/gh_deploy -N '' -C 'github-actions-deploy'
  cat ~/.ssh/gh_deploy.pub >> ~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
fi

cat <<EOF

=========================================================
XONG. Chep khoa duoi day vao GitHub secret VPS_SSH_KEY
(ca hai moi truong staging va production):
=========================================================
EOF
cat ~/.ssh/gh_deploy
echo "========================================================="
echo "VPS_HOST = $(curl -fsS ifconfig.me || echo '<tu tra IP>')"
echo "VPS_USER = $USER"
echo "DEPLOY_PATH prod    = $HOME/p150-prod"
echo "DEPLOY_PATH staging = $HOME/p150-staging"
echo "========================================================="
echo "Buoc tiep: tao .env trong ~/p150-prod (xem docs/DEPLOY.md muc 2)."
echo "Sinh secret: openssl rand -base64 48"
