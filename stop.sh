#!/bin/bash
# ============================================================
# Digital WBS 대시보드 - 서버 종료 스크립트
# 사용법: ./stop.sh [--force]
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$SCRIPT_DIR/.server.pid"

FORCE=false
if [[ "$1" == "--force" || "$1" == "-f" ]]; then
    FORCE=true
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "사용법: ./stop.sh [옵션]"
    echo ""
    echo "옵션:"
    echo "  -f, --force    강제 종료 (SIGKILL)"
    echo "  -h, --help     도움말"
    exit 0
fi

echo "============================================================"
echo "🛑 Digital WBS 대시보드 서버 종료"
echo "============================================================"

# ----- PID 파일 기반 종료 -----
if [[ -f "$PID_FILE" ]]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "📌 PID $PID 프로세스 종료 중..."
        if [[ "$FORCE" == true ]]; then
            kill -9 "$PID" 2>/dev/null || true
            echo "⚡ 강제 종료 완료 (SIGKILL)"
        else
            kill "$PID" 2>/dev/null || true
            # Graceful shutdown 대기 (최대 10초)
            echo -n "⏳ 종료 대기 중"
            for i in {1..20}; do
                sleep 0.5
                echo -n "."
                if ! kill -0 "$PID" 2>/dev/null; then
                    echo ""
                    echo "✅ 서버가 정상 종료되었습니다. (PID: $PID)"
                    rm -f "$PID_FILE"
                    exit 0
                fi
            done
            echo ""
            echo "⚠️  정상 종료 시간 초과. 강제 종료 중..."
            kill -9 "$PID" 2>/dev/null || true
            echo "⚡ 강제 종료 완료"
        fi
        rm -f "$PID_FILE"
    else
        echo "⚠️  PID $PID 프로세스가 이미 종료되었습니다."
        rm -f "$PID_FILE"
    fi
else
    echo "ℹ️  PID 파일이 없습니다."
fi

# ----- http.server 프로세스 잔여 확인 -----
REMAINING_PIDS=$(pgrep -f "python3 -m http.server" 2>/dev/null || true)
if [[ -n "$REMAINING_PIDS" ]]; then
    echo ""
    echo "🔍 잔여 http.server 프로세스 발견:"
    echo "   PIDs: $REMAINING_PIDS"
    if [[ "$FORCE" == true ]]; then
        echo "$REMAINING_PIDS" | xargs kill -9 2>/dev/null || true
        echo "⚡ 잔여 프로세스 강제 종료 완료"
    else
        echo "$REMAINING_PIDS" | xargs kill 2>/dev/null || true
        sleep 1
        STILL_RUNNING=$(pgrep -f "python3 -m http.server" 2>/dev/null || true)
        if [[ -n "$STILL_RUNNING" ]]; then
            echo "$STILL_RUNNING" | xargs kill -9 2>/dev/null || true
            echo "⚡ 잔여 프로세스 강제 종료 완료"
        else
            echo "✅ 잔여 프로세스 정상 종료 완료"
        fi
    fi
else
    echo "✅ 실행 중인 서버 프로세스가 없습니다."
fi

echo "============================================================"
echo "🏁 종료 완료"
echo "============================================================"
