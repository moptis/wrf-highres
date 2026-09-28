# Sourced by every sbatch script. Resolves site.env relative to the repo.
WRFHR_REPO="${WRFHR_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
set -a
# shellcheck disable=SC1090
. "${WRFHR_SITE:-$WRFHR_REPO/site.env}"
set +a
