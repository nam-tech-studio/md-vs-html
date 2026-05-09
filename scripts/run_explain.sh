#!/usr/bin/env bash
# 各 (length, format) 条件で N回 説明生成を実行する。
# `claude -p` をそれぞれの trial dir で起動し、ステートレスなセッションで読解させる。
#
# Usage: bash scripts/run_explain.sh [TRIALS]
#   TRIALS: 各条件あたりの試行回数 (default 5)

set -e

TRIALS=${1:-5}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
PROMPT_FILE="${ROOT}/prompts/explain.txt"
RESULTS_DIR="${ROOT}/results/explanations"
LOG="${ROOT}/results/run_explain.log"

mkdir -p "${RESULTS_DIR}"
> "${LOG}"

LENGTHS=(50 100 250 500)
FORMATS=(md html)

# 並列度: あまりに多いとレート制限に当たる可能性。控えめに 4 並列で開始。
PARALLEL=${PARALLEL:-4}

PROMPT=$(cat "${PROMPT_FILE}")

run_one() {
  local length=$1
  local format=$2
  local trial=$3
  local trial_dir="${ROOT}/trials/${length}_${format}"
  local out="${RESULTS_DIR}/${length}_${format}_trial${trial}.md"

  if [ -f "${out}" ] && [ -s "${out}" ]; then
    echo "[skip] ${out} exists and non-empty" | tee -a "${LOG}"
    return 0
  fi

  local start=$(date +%s)
  echo "[start] ${length}_${format}_trial${trial} at $(date '+%H:%M:%S')" | tee -a "${LOG}"

  # cd して実行 → エージェントは trial_dir のみ見える
  (
    cd "${trial_dir}"
    claude -p "${PROMPT}" \
      --model claude-opus-4-7 \
      --allowedTools "Read,LS,Glob" \
      --permission-mode acceptEdits \
      > "${out}.tmp" 2> "${out}.err"
  ) || { echo "[FAIL] ${length}_${format}_trial${trial}" | tee -a "${LOG}"; return 1; }

  if [ -s "${out}.tmp" ]; then
    mv "${out}.tmp" "${out}"
    rm -f "${out}.err"
  else
    mv "${out}.tmp" "${out}.empty"
    echo "[EMPTY] ${length}_${format}_trial${trial}" | tee -a "${LOG}"
    return 1
  fi

  local end=$(date +%s)
  local secs=$((end-start))
  local lines=$(wc -l < "${out}" | tr -d ' ')
  echo "[done]  ${length}_${format}_trial${trial} ${secs}s ${lines}行" | tee -a "${LOG}"
}

export -f run_one
export ROOT RESULTS_DIR LOG PROMPT

JOBS=()
for length in "${LENGTHS[@]}"; do
  for format in "${FORMATS[@]}"; do
    for trial in $(seq 1 "${TRIALS}"); do
      JOBS+=("${length} ${format} ${trial}")
    done
  done
done

echo "Total jobs: ${#JOBS[@]} | parallel=${PARALLEL}" | tee -a "${LOG}"

# 並列実行 (xargs -P で簡易ジョブプール)
printf "%s\n" "${JOBS[@]}" | xargs -P "${PARALLEL}" -L 1 bash -c 'run_one $0 $1 $2'

echo "All done." | tee -a "${LOG}"
