#!/bin/sh
# Explicit opt-in only. Default gateway CMD never invokes this file.
set -eu
reject() { printf '%s\n' 'OTLP public configuration rejected' >&2; exit 64; }
ipv4() {
    scope=$2
    case "$1" in ''|*[!0-9.]*|.*|*.|*..*) reject ;; esac
    saved_ifs=$IFS
    IFS=.
    # Deliberate splitting of an already digits/dots-only public IPv4.
    set -- $1
    IFS=$saved_ifs
    [ "$#" -eq 4 ] || reject
    for octet in "$@"; do
        case "$octet" in ''|0[0-9]*) reject ;; esac
        [ "${#octet}" -le 3 ] && [ "$octet" -le 255 ] || reject
    done
    [ "$scope" = fixed ] && return
    case "$1.$2" in
        10.*|192.168) return ;;
        172.*) [ "$2" -ge 16 ] && [ "$2" -le 31 ] && return ;;
    esac
    reject
}
[ "$#" -le 1 ] || reject
ipv4 "${AI_DATABASE_FORWARD_IP:-}" fixed
ipv4 "${AI_OTLP_BIND_IP:-}" private
ipv4 "${AI_OTLP_COLLECTOR_IP:-}" private
[ "$AI_OTLP_BIND_IP" != "$AI_OTLP_COLLECTOR_IP" ] || reject
if [ "${1:-}" = '--check' ]; then
    printf '%s\n' 'OTLP public configuration valid'
    exit 0
fi
[ "$#" -eq 0 ] || reject
exec /usr/bin/env -i PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    AI_DATABASE_FORWARD_IP="$AI_DATABASE_FORWARD_IP" \
    AI_OTLP_BIND_IP="$AI_OTLP_BIND_IP" \
    AI_OTLP_COLLECTOR_IP="$AI_OTLP_COLLECTOR_IP" \
    /usr/local/sbin/haproxy -W -db \
    -f /usr/local/etc/haproxy/haproxy.cfg -f /usr/local/etc/haproxy/otlp.cfg
