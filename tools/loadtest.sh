#!/bin/bash
# Load test for www.makaron.uk, run once at first boot on a temporary server.
# It measures (1) the web server's outbound bandwidth, (2) request handling, and (3) how many
# first-time visitors per second it can serve, where one visitor downloads what a browser
# downloads on a first visit to the home page (page + 21 images + 3 videos, about 27 MB).
# Results are published as plain text on this machine's port 80.
set -u
HOST="${HOST:-https://www.makaron.uk}"
OUT="${OUT:-/srv/lt}"
RATES="${RATES:-0.5 1 2 3 4 6 8 12 16}"      # visitors arriving per second, one stage each
STAGE="${STAGE:-30}"                         # seconds of arrivals per stage
BW_SECS="${BW_SECS:-20}"
mkdir -p "$OUT"; cd "$OUT"
log(){ echo "$(date -u +%H:%M:%S) $*" >> "$OUT/progress.txt"; }
R="$OUT/results.txt"
if [ -z "${NO_SERVE:-}" ]; then (cd "$OUT" && nohup python3 -m http.server 80 >/dev/null 2>&1 &); fi
log "started; target $HOST"

if [ -z "${NO_APT:-}" ]; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1; apt-get install -y -qq wrk apache2-utils curl >/dev/null 2>&1
  log "tools installed: wrk=$(command -v wrk || echo none) ab=$(command -v ab || echo none)"
fi
ulimit -n 65535 2>/dev/null

IFACE="${IFACE:-$(ip route show default 2>/dev/null | awk '{print $5; exit}')}"
rx(){ awk -v i="$IFACE:" '$1==i{print $2}' /proc/net/dev; }
cpu(){ awk '/^cpu /{print $2+$3+$4+$6+$7+$8, $2+$3+$4+$5+$6+$7+$8}' /proc/stat; }   # busy total
# one line per second: epoch, megabits received in that second
( p=$(rx); while :; do sleep 1; n=$(rx); echo "$(date +%s) $(( (n-p)*8/1000000 ))"; p=$n; done > "$OUT/rx.log" ) &
SAMPLER=$!

# what a first visit to the home page downloads
IMGS="emblem.png hero-poster.jpg story-1.jpg strip-1.jpg strip-4.jpg strip-3.jpg mosaic-2.jpg mosaic-3.jpg strip-5.jpg outro.jpg tanks.jpg mill-building.jpg craft-poster.jpg stone-press.jpg strip-6.jpg story-4.jpg story-2.jpg story-3.jpg story-5.jpg story-7.jpg story-6.jpg"
VIDS="hero.mp4 banner.mp4 craft-hero.mp4"
CFG="$OUT/visit.cfg"; : > "$CFG"
{ echo "url = \"$HOST/\""; echo 'output = "/dev/null"'
  for f in $IMGS $VIDS; do echo "url = \"$HOST/assets/$f\""; echo 'output = "/dev/null"'; done; } >> "$CFG"
NFILES=$(grep -c '^url' "$CFG")

{
echo "MAKARON LOAD TEST  $(date -u '+%Y-%m-%d %H:%M UTC')"
echo "target: $HOST"
echo "generator: $(nproc) vCPU, $(awk '/MemTotal/{printf "%.1f GB", $2/1048576}' /proc/meminfo), $(curl -s -m 3 http://169.254.169.254/hetzner/v1/metadata/availability-zone 2>/dev/null || echo unknown-zone)"
echo
} > "$R"

# ---------- 1. bandwidth: many parallel downloads of the largest file ----------
log "phase 1: bandwidth"
bw(){ # $1 = parallel streams
  local n=$1 t0 t1 urls=""
  for i in $(seq 1 40); do urls="$urls $HOST/assets/film.mp4"; done
  t0=$(date +%s)
  for i in $(seq 1 "$n"); do ( timeout "$BW_SECS" curl -s -o /dev/null $urls >/dev/null 2>&1 ) & done
  sleep "$BW_SECS"; sleep 2; t1=$(date +%s)
  awk -v a=$((t0+3)) -v b=$((t1-3)) -v n="$n" '$1>=a && $1<=b {s+=$2; c++; if($2>m)m=$2} END{ if(c) printf "  %3d parallel downloads: average %d Mbit/s, peak %d Mbit/s\n", n, s/c, m; else printf "  %3d parallel downloads: no samples\n", n }' "$OUT/rx.log" >> "$R"
}
echo "1. BANDWIDTH OUT OF THE WEB SERVER (downloading film.mp4, ${BW_SECS}s per run)" >> "$R"
bw 8; sleep 3; bw 32; sleep 3
echo >> "$R"

# ---------- 2. request handling ----------
log "phase 2: request handling"
echo "2. REQUEST HANDLING" >> "$R"
if command -v wrk >/dev/null; then
  o=$(wrk -t2 -c64 -d12s --latency "$HOST/robots.txt" 2>&1)
  echo "  small file, 64 kept-open connections: $(echo "$o" | awk '/Requests\/sec/{print $2}') requests/s, median $(echo "$o" | awk '$1=="50%"{print $2}'), 99th pct $(echo "$o" | awk '$1=="99%"{print $2}')" >> "$R"
  o=$(wrk -t2 -c32 -d12s --latency -H 'Accept-Encoding: gzip' "$HOST/" 2>&1)
  echo "  home page HTML (compressed), 32 connections: $(echo "$o" | awk '/Requests\/sec/{print $2}') pages/s, median $(echo "$o" | awk '$1=="50%"{print $2}'), 99th pct $(echo "$o" | awk '$1=="99%"{print $2}'), transfer $(echo "$o" | awk '/Transfer\/sec/{print $2}')/s" >> "$R"
else echo "  wrk not available" >> "$R"; fi
if command -v ab >/dev/null; then
  o=$(ab -q -n 3000 -c 50 "$HOST/robots.txt" 2>&1)
  echo "  new secure connections (one request each, 50 at a time): $(echo "$o" | awk '/Requests per second/{print $4}') per second, failed $(echo "$o" | awk '/Failed requests/{print $3}')" >> "$R"
fi
echo >> "$R"

# ---------- 3. visitor ramp ----------
log "phase 3: visitor ramp"
visitor(){ # $1 stage label ; writes: stage start wall bytes ok fail htmltime
  local s=$(date +%s.%N) out e
  out=$(curl -sS --compressed --parallel --parallel-max 6 --max-time 150 -K "$CFG" -w '%{http_code} %{size_download} %{time_total} %{url_effective}\n' 2>/dev/null)
  e=$(date +%s.%N)
  echo "$out" | awk -v st="$1" -v s="$s" -v e="$e" -v host="$HOST/" '{ b+=$2; if($1==200) ok++; else fail++; if($4==host) h=$3 } END{ printf "%s %.3f %.3f %d %d %d %.3f\n", st, s, e-s, b, ok, fail, h }' >> "$OUT/visits.log"
}
{
echo "3. FIRST-TIME VISITORS ($NFILES files, about 27 MB each; ${STAGE}s of arrivals per step)"
echo "  arriving/s | visitors | complete | median visit | slowest 5% | page HTML median | throughput | generator CPU"
} >> "$R"
: > "$OUT/visits.log"
LAST_OK=""
for rate in $RATES; do
  n=$(awk -v r="$rate" -v d="$STAGE" 'BEGIN{printf "%d", r*d+0.5}'); gap=$(awk -v r="$rate" 'BEGIN{printf "%.4f", 1/r}')
  log "ramp: $rate/s ($n visitors)"
  read b0 t0c < <(cpu); s0=$(date +%s); r0=$(rx)
  for i in $(seq 1 "$n"); do visitor "$rate" & sleep "$gap"; done
  wait $(jobs -p | grep -v "^$SAMPLER$") 2>/dev/null
  read b1 t1c < <(cpu); s1=$(date +%s); r1=$(rx)
  line=$(awk -v st="$rate" -v nf="$NFILES" -v n="$n" -v el=$((s1-s0)) -v rxb=$((r1-r0)) -v cb=$((b1-b0)) -v ct=$((t1c-t0c)) '
    $1==st { w[++c]=$3; h[c]=$7; if($5==nf && $6==0) done++ }
    END{ if(!c){print "none"; exit}
      for(i=1;i<=c;i++)for(j=i+1;j<=c;j++){ if(w[j]<w[i]){t=w[i];w[i]=w[j];w[j]=t} if(h[j]<h[i]){t=h[i];h[i]=h[j];h[j]=t} }
      m=w[int((c+1)/2)]; p=w[int(c*0.95+0.5)>c?c:int(c*0.95+0.5)]; hm=h[int((c+1)/2)];
      printf "%9s  | %8d | %7d%% | %10.1f s | %8.1f s | %14.2f s | %5d Mbit/s | %3d%%  #%.1f %d\n", st, n, 100*done/n, m, p, hm, rxb*8/1000000/(el>0?el:1), (ct>0?100*cb/ct:0), m, 100*done/n }' "$OUT/visits.log")
  echo "  ${line%%#*}" >> "$R"
  med=$(echo "${line##*#}" | awk '{print $1}'); pct=$(echo "${line##*#}" | awk '{print $2}')
  if awk -v m="$med" -v p="$pct" 'BEGIN{exit !(m>45 || p<90)}'; then
    echo "  stopped after $rate/s: visits were taking too long or failing" >> "$R"; break
  fi
  LAST_OK=$rate; sleep 5
done
echo >> "$R"
kill $SAMPLER 2>/dev/null
echo "peak second during the whole test: $(awk '{if($2>m)m=$2} END{print m+0}' "$OUT/rx.log") Mbit/s received" >> "$R"
echo "total downloaded by the generator: $(awk -v i="$IFACE:" '$1==i{printf "%.1f GB", $2/1e9}' /proc/net/dev)" >> "$R"
echo "finished $(date -u '+%H:%M UTC')" >> "$R"
echo DONE >> "$R"
log "done"
