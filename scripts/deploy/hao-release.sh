#!/usr/bin/env bash
# Chạy TRÊN hao, làm lệnh bắt buộc (forced command) của khóa SSH deploy. Chỉ đổi release của app:
# không migration, không chạm DB. Cài đặt và gate: docs/hao-auto-deploy.md.
#
#   current            in SHA đang chạy (hoặc "none")
#   deploy <sha40>     nhận tar của gói mã từ stdin, chuyển symlink, restart, kiểm sống, lỗi thì quay lại
set -euo pipefail

CONF=${WEBDEBIT_DEPLOY_CONF:-/etc/webdebit-deploy.conf}
# shellcheck source=/dev/null
. "$CONF"
: "${RELEASES_DIR:?}" "${CURRENT_LINK:?}" "${UNIT:?}" "${HEALTH_URL:?}"
KEEP=${KEEP:-5}

read -r -a args <<< "${SSH_ORIGINAL_COMMAND:-$*}"
action=${args[0]:-}
sha=${args[1]:-}

current_sha() { cat "$CURRENT_LINK/.release-sha" 2>/dev/null || echo none; }

alive() {
  # 200 hoặc 403 đều là dịch vụ sống (GET loopback không có danh tính Tailscale nên có thể 403, runbook mục 6).
  local code
  code=$(curl --silent --output /dev/null --max-time 5 --write-out '%{http_code}' "$HEALTH_URL" || true)
  [[ $code == 200 || $code == 403 ]] && systemctl is-active --quiet "$UNIT"
}

case $action in
  current) current_sha ;;
  deploy)
    [[ $sha =~ ^[0-9a-f]{40}$ ]] || { echo "sha không hợp lệ" >&2; exit 2; }
    exec 9>"$RELEASES_DIR/.deploy.lock"
    flock -n 9 || { echo "đang có lượt deploy khác" >&2; exit 3; }

    new="$RELEASES_DIR/$sha"
    prev=
    [[ -f $CURRENT_LINK/.release-sha ]] && prev=$(readlink -f "$CURRENT_LINK")
    if [[ $(current_sha) == "$sha" ]]; then echo "đã chạy $sha, bỏ qua"; exit 0; fi

    rm -rf "$new.tmp"
    install -d -m 755 "$new.tmp"
    # Từ chối đường dẫn tuyệt đối, '..' và liên kết; gói chỉ gồm file thường.
    tar -x --no-same-owner --no-same-permissions -C "$new.tmp"
    if find "$new.tmp" \( -type l -o -name '..' \) | grep -q .; then
      rm -rf "$new.tmp"; echo "gói có liên kết, từ chối" >&2; exit 4
    fi
    printf '%s\n' "$sha" > "$new.tmp/.release-sha"
    rm -rf "$new"; mv "$new.tmp" "$new"

    switch() { ln -sfn "$1" "$CURRENT_LINK.new" && mv -T "$CURRENT_LINK.new" "$CURRENT_LINK" && sudo -n systemctl restart "$UNIT"; }
    switch "$new"
    ok=0
    for _ in $(seq 1 15); do sleep 2; if alive; then ok=1; break; fi; done
    if [[ $ok != 1 ]]; then
      echo "kiểm sống thất bại, quay lại ${prev:-không có bản cũ}" >&2
      [[ -n $prev ]] && switch "$prev"
      exit 5
    fi
    echo "đã chạy $sha (trước đó: $(basename "${prev:-none}"))"
    # Giữ $KEEP release mới nhất và release đang chạy.
    ls -1dt "$RELEASES_DIR"/*/ 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
      [[ $(readlink -f "$old") == $(readlink -f "$CURRENT_LINK") ]] || rm -rf "$old"
    done
    ;;
  *) echo "lệnh không hỗ trợ" >&2; exit 2 ;;
esac
