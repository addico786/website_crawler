#!/usr/bin/env bash
# Interactive launcher for crawl.py.
#
# Asks for the site to crawl, how long to run, and a job name (so
# progress can be resumed later), then starts crawl.py with those
# settings. Run this instead of typing the full command by hand.

set -e

project_dir=$(cd "$(dirname "$0")" && pwd)
python_bin="$project_dir/env/bin/python3"

if [ ! -x "$python_bin" ]; then
  echo "Setup is missing. Run: python3 -m venv env"
  echo "Then run: env/bin/python3 -m pip install -r requirements.txt"
  exit 1
fi

if ! "$python_bin" -c 'import scrapy' 2>/dev/null; then
  echo "Scrapy is not installed yet. Run: env/bin/python3 -m pip install -r requirements.txt"
  exit 1
fi

echo "=== Website Crawler ==="
echo

read -rp "Website to crawl (starting URL): " url
while [ -z "$url" ]; do
  echo "A URL is required."
  read -rp "Website to crawl (starting URL): " url
done

read -rp "How many minutes should it run? (0 = until finished) [120]: " minutes
minutes=${minutes:-120}

read -rp "Job name (used to save/resume progress) [jobs/default]: " job
job=${job:-jobs/default}

read -rp "Delay between requests in seconds (blank = default): " delay
read -rp "Maximum pages to save [1000]: " max_pages
max_pages=${max_pages:-1000}
read -rp "Maximum link depth [8]: " max_depth
max_depth=${max_depth:-8}

cmd=("$python_bin" crawl.py "$url" --minutes "$minutes" --job "$job" --max-pages "$max_pages" --max-depth "$max_depth")
if [ -n "$delay" ]; then
  cmd+=(--delay "$delay")
fi

echo
echo "Starting crawl:"
echo "  ${cmd[*]}"
echo

"${cmd[@]}"
